"""``flowforge jtbd fork`` — create a tenant-scoped copy of an upstream JTBD library.

Per evolution.md §3.2 and jtbd-editor-arch.md §1.3.

Fork semantics
--------------
* Loads an upstream JTBD bundle (JSON or YAML file).
* Stamps each JTBD with ``forked_from`` provenance (upstream package, version,
  file path) so pull-from-upstream can compute a diff later.
* Sets ``tenant_id`` on the bundle's project block.
* Writes the forked bundle to ``--out`` (default: ``<cwd>/<tenant>_fork/jtbd_bundle.json``).

Required permission: ``jtbd.fork``  (see JTBD_FORK_PERMISSION constant below).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import typer

from .._io import load_structured, write_json

#: SpiceDB / RBAC permission name for forking.  Seeds via
#: ``register_permission(JTBD_FORK_PERMISSION, "Fork upstream JTBD libraries")``.
JTBD_FORK_PERMISSION = "jtbd.fork"


def register(app: typer.Typer) -> None:
	app.command("fork", help="Fork an upstream JTBD library into a tenant-scoped copy.")(jtbd_fork_cmd)


def jtbd_fork_cmd(
	upstream: Path = typer.Argument(
		...,
		exists=True,
		dir_okay=False,
		help="Path to the upstream JTBD bundle file (JSON or YAML).",
	),
	tenant: str = typer.Option(..., "--tenant", help="Destination tenant id."),
	out: Path | None = typer.Option(
		None,
		"--out",
		help="Output path for the forked bundle (default: <cwd>/<tenant>_fork/jtbd_bundle.json).",
	),
) -> None:
	"""Fork *upstream* JTBD library into a tenant-scoped copy.

	Each JTBD in the bundle gets a ``forked_from`` provenance block so
	``flowforge jtbd pull-upstream`` can produce a unified diff later.
	The required RBAC permission is ``jtbd.fork``.
	"""

	assert upstream is not None, "upstream bundle file is required"
	assert tenant, "--tenant <id> is required"

	bundle = load_structured(upstream)

	# Compute a content hash of the upstream bundle for provenance tracking.
	upstream_bytes = json.dumps(bundle, sort_keys=True).encode()
	spec_hash = "sha256:" + hashlib.sha256(upstream_bytes).hexdigest()

	upstream_version = (bundle.get("project") or {}).get("version", "unknown")
	upstream_name = (bundle.get("project") or {}).get("name") or upstream.stem

	forked = _fork_bundle(bundle, tenant=tenant, upstream_name=upstream_name,
						   upstream_version=upstream_version, spec_hash=spec_hash,
						   upstream_path=str(upstream))

	dst = out or Path.cwd() / f"{tenant}_fork" / "jtbd_bundle.json"
	write_json(dst, forked)

	forked_ids = [j["id"] for j in forked.get("jtbds", [])]
	typer.echo(
		f"forked {upstream_name}@{upstream_version} → {dst} "
		f"(tenant={tenant}, {len(forked_ids)} jtbds)"
	)
	for jid in forked_ids:
		typer.echo(f"  + {jid}")
	typer.echo(f"spec_hash: {spec_hash}")
	typer.echo(f"permission required: {JTBD_FORK_PERMISSION}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fork_bundle(
	bundle: dict[str, Any],
	*,
	tenant: str,
	upstream_name: str,
	upstream_version: str,
	spec_hash: str,
	upstream_path: str,
) -> dict[str, Any]:
	"""Return a deep copy of *bundle* with tenant provenance added."""

	forked = copy.deepcopy(bundle)

	# Stamp the project block.
	project: dict[str, Any] = forked.setdefault("project", {})
	project["tenant_id"] = tenant
	project.setdefault("version", upstream_version)

	# Provenance for the whole library fork.
	forked.setdefault("fork_metadata", {}).update({
		"tenant_id": tenant,
		"forked_from": {
			"name": upstream_name,
			"version": upstream_version,
			"spec_hash": spec_hash,
			"source_path": upstream_path,
		},
		"pull_upstream_enabled": True,
	})

	# Stamp each JTBD spec with its upstream provenance.
	for jtbd in forked.get("jtbds", []):
		jtbd.setdefault("fork_provenance", {}).update({
			"tenant_id": tenant,
			"parent_library": upstream_name,
			"parent_version": upstream_version,
			"parent_spec_hash": spec_hash,
		})

	return forked
