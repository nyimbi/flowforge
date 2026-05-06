"""``flowforge jtbd migrate`` — show replaced_by chain diff and optionally apply.

Resolves the full ``replaced_by`` chain for a deprecated JTBD, displays the
data-capture shape diff, and optionally migrates a concrete data record to the
replacement JTBD's shape.

Examples::

    # Show diff only (no record):
    flowforge jtbd migrate --bundle jtbd-bundle.json --from claim_intake

    # Diff and transform a data record (print to stdout):
    flowforge jtbd migrate --bundle jtbd-bundle.json \\
        --from claim_intake --record data.json

    # Diff and write migrated record to a file:
    flowforge jtbd migrate --bundle jtbd-bundle.json \\
        --from claim_intake --record data.json --out migrated.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .._io import load_structured, write_json
from flowforge_jtbd.migrate import (
	MigrationError,
	apply_to_record,
	build_migration,
	format_diff_text,
)


def register(app: typer.Typer) -> None:
	app.command(
		"migrate",
		help="Show replaced_by chain diff; optionally apply migration to a data record.",
	)(jtbd_migrate_cmd)


def jtbd_migrate_cmd(
	bundle: Annotated[
		Path,
		typer.Option(
			"--bundle",
			exists=True,
			dir_okay=False,
			help="JTBD bundle JSON/YAML.",
		),
	],
	from_id: Annotated[
		str,
		typer.Option("--from", help="Id of the deprecated JTBD to migrate from."),
	],
	record: Annotated[
		Path | None,
		typer.Option(
			"--record",
			exists=True,
			dir_okay=False,
			help="Data record JSON to transform (optional).",
		),
	] = None,
	out: Annotated[
		Path | None,
		typer.Option("--out", help="Write migrated record here (default: stdout)."),
	] = None,
	max_depth: Annotated[
		int,
		typer.Option("--max-depth", help="Maximum replaced_by chain depth."),
	] = 32,
) -> None:
	"""Resolve the replaced_by chain from FROM and display the data-shape diff."""

	assert bundle is not None
	assert from_id, "--from <jtbd_id> is required"

	data = load_structured(bundle)

	try:
		diff = build_migration(data, from_id, max_depth=max_depth)
	except MigrationError as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(1) from exc

	typer.echo(format_diff_text(diff))

	if len(diff.chain) == 1:
		typer.echo("(JTBD is not deprecated — no migration needed)")
		return

	if record is None:
		return

	rec_data = load_structured(record)
	result = apply_to_record(diff, rec_data)

	if result.dropped:
		typer.echo(
			f"\nwarning: dropped fields with data: {', '.join(result.dropped)}",
			err=True,
		)

	if out is not None:
		write_json(out, result.record)
		typer.echo(f"\nmigrated record → {out}")
	else:
		typer.echo("\nmigrated record:")
		typer.echo(json.dumps(result.record, indent=2, sort_keys=True))
