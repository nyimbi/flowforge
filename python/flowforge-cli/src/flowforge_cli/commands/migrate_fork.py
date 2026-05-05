"""``flowforge migrate-fork`` — copy an upstream definition into a tenant fork.

Used by operators to materialise a per-tenant workflow definition from a
shared upstream. The fork is annotated with ``metadata.forked_from`` so
the catalog can show provenance.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .._io import load_structured, write_json


def register(app: typer.Typer) -> None:
	app.command("migrate-fork", help="Fork an operator-shared workflow definition into a tenant copy.")(migrate_fork_cmd)


def migrate_fork_cmd(
	upstream: Path = typer.Argument(..., exists=True, dir_okay=False, help="Upstream definition.json."),
	tenant: str = typer.Option(..., "--to", help="Destination tenant id."),
	out: Path | None = typer.Option(
		None,
		"--out",
		help="Destination path (default: workflows/<tenant>/<key>/definition.json).",
	),
) -> None:
	"""Fork *upstream* under tenant *tenant*."""

	assert upstream is not None
	assert tenant, "--to <tenant> is required"

	wf = load_structured(upstream)
	key = wf.get("key", upstream.parent.name)
	wf.setdefault("metadata", {})
	wf["metadata"]["forked_from"] = {"key": key, "version": wf.get("version", "?")}
	wf["metadata"]["tenant_id"] = tenant

	dst = out or Path("workflows") / tenant / key / "definition.json"
	write_json(dst, wf)
	typer.echo(f"forked {key}@{wf.get('version', '?')} → {dst} (tenant={tenant})")
