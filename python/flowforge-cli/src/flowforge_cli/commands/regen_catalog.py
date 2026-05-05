"""``flowforge regen-catalog`` — rewrite ``workflows/catalog.json``.

Loads every ``definition.json`` under the workflows root and runs
:func:`flowforge.compiler.catalog.build_catalog`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from flowforge.compiler.catalog import build_catalog
from flowforge.dsl import WorkflowDef

from .._io import discover_workflow_defs, load_structured, write_json


def register(app: typer.Typer) -> None:
	app.command("regen-catalog", help="Regenerate workflows/catalog.json from on-disk definitions.")(regen_catalog_cmd)


def regen_catalog_cmd(
	root: Path = typer.Option(Path("workflows"), "--root", help="Workflows root (default: ./workflows)."),
	out: Path | None = typer.Option(
		None,
		"--out",
		help="Catalog output path (default: <root>/catalog.json).",
	),
) -> None:
	"""Walk *root*, build a catalog, write it to disk."""

	assert root is not None
	paths = discover_workflow_defs(root)
	if not paths:
		typer.echo(f"no definitions found under {root}")
		raise typer.Exit(code=1)

	defs: list[WorkflowDef] = []
	for path in paths:
		raw = load_structured(path)
		defs.append(WorkflowDef.model_validate(raw))

	catalog = build_catalog(defs)
	dst = out or (root / "catalog.json")
	write_json(dst, catalog)

	subjects = catalog.get("subjects", {})
	typer.echo(f"regenerated {dst} ({len(defs)} defs, {len(subjects)} subject kinds)")
