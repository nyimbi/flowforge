"""``flowforge migrate-fork`` — copy an upstream definition into a tenant fork.

Used by operators to materialise a per-tenant workflow definition from a
shared upstream. The fork is annotated with ``metadata.forked_from`` so
the catalog can show provenance.
"""

from __future__ import annotations

from pathlib import Path
import re

import typer

from .._io import load_structured, write_json


_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_path_segment(label: str, value: object) -> str:
	text = str(value)
	if (
		not text
		or text in {".", ".."}
		or not _SAFE_PATH_SEGMENT.fullmatch(text)
	):
		raise typer.BadParameter(
			f"{label} must contain only letters, digits, dot, underscore, or hyphen"
		)
	return text


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
	tenant_id = _safe_path_segment("tenant id", tenant)
	workflow_key = _safe_path_segment("workflow key", key)
	wf.setdefault("metadata", {})
	wf["metadata"]["forked_from"] = {"key": key, "version": wf.get("version", "?")}
	wf["metadata"]["tenant_id"] = tenant

	if out is None:
		root = Path("workflows").resolve()
		dst = (root / tenant_id / workflow_key / "definition.json").resolve()
		try:
			dst.relative_to(root)
		except ValueError as exc:  # pragma: no cover - defensive belt after segment validation
			raise typer.BadParameter("default destination escaped workflows root") from exc
	else:
		dst = out
	write_json(dst, wf)
	typer.echo(f"forked {key}@{wf.get('version', '?')} → {dst} (tenant={tenant})")
