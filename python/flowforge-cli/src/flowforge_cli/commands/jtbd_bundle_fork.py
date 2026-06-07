"""``flowforge jtbd bundle-fork`` — fork a JTBD bundle with provenance tracking (E-1).

Creates a forked bundle copy with a new ``bundle_id`` and stamps each JTBD spec
with ``parent_version_id`` pointing back to the source bundle, per the E-1
fork-lineage contract.

Usage::

    flowforge jtbd bundle-fork source.json my-fork [--out ./forks/]

The forked bundle is written to ``<out>/my-fork/jtbd-bundle.json`` (or
``<cwd>/my-fork/jtbd-bundle.json`` when --out is omitted).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .._io import load_structured, write_json


def register(app: typer.Typer) -> None:
	app.command(
		"bundle-fork",
		help="Fork a JTBD bundle with E-1 parent_version_id provenance.",
	)(jtbd_bundle_fork_cmd)


# ---------------------------------------------------------------------------
# Core fork logic (importable for tests)
# ---------------------------------------------------------------------------


def fork_bundle(
	source: dict[str, Any],
	target_name: str,
	*,
	source_path: str = "",
) -> dict[str, Any]:
	"""Return a deep-copied *source* bundle stamped with fork provenance.

	Each JTBD in the returned bundle gains a ``parent_version_id`` field
	(set to the source bundle's ``project.name`` + ``@`` + ``project.version``
	so the chain is traceable) and the top-level ``project.name`` is
	replaced with *target_name*.
	"""
	assert target_name, "target_name must be non-empty"

	forked = copy.deepcopy(source)

	project: dict[str, Any] = forked.setdefault("project", {})
	source_name: str = project.get("name") or "unknown"
	source_version: str = project.get("version") or "1.0.0"
	parent_version_id = f"{source_name}@{source_version}"

	# Update project identity.
	project["name"] = target_name

	# Fork provenance at the bundle level.
	forked["fork_provenance"] = {
		"parent_bundle": source_name,
		"parent_version": source_version,
		"parent_version_id": parent_version_id,
		"source_path": source_path,
	}

	# Stamp each JTBD spec.
	for jtbd in forked.get("jtbds", []) or []:
		jtbd["parent_version_id"] = parent_version_id

	return forked


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def jtbd_bundle_fork_cmd(
	source_bundle: Annotated[
		Path,
		typer.Argument(help="Source JTBD bundle JSON file to fork from."),
	],
	target_name: Annotated[
		str,
		typer.Argument(help="Name for the forked bundle (used as project.name)."),
	],
	out: Annotated[
		Path | None,
		typer.Option("--out", help="Output directory (default: cwd/<target_name>/)."),
	] = None,
) -> None:
	"""Fork SOURCE_BUNDLE into a new bundle named TARGET_NAME.

	Each JTBD in the forked bundle is stamped with ``parent_version_id``
	pointing to the source bundle so the lineage is traceable.
	"""
	assert source_bundle is not None, "source_bundle is required"
	assert target_name, "target_name is required"

	if not source_bundle.exists():
		typer.echo(f"error: source bundle not found: {source_bundle}", err=True)
		raise typer.Exit(1)

	raw = load_structured(source_bundle)
	forked = fork_bundle(raw, target_name, source_path=str(source_bundle))

	dst_dir = out or (Path.cwd() / target_name)
	dst = dst_dir / "jtbd-bundle.json"
	write_json(dst, forked)

	jtbd_ids = [j.get("id") or j.get("jtbd_id") for j in forked.get("jtbds", [])]
	parent_vid = forked.get("fork_provenance", {}).get("parent_version_id", "?")

	typer.echo(f"forked: {source_bundle} → {dst}")
	typer.echo(f"  target_name     : {target_name}")
	typer.echo(f"  parent_version_id: {parent_vid}")
	typer.echo(f"  jtbds           : {len(jtbd_ids)}")
	for jid in jtbd_ids:
		typer.echo(f"    + {jid}")
