"""``flowforge validate`` — schema + topology checks per §10.3.

Wraps :func:`flowforge.compiler.validator.validate` and produces the
sample output structure shown in the portability doc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from flowforge.compiler.validator import ValidationReport, validate as _validate

from .._io import discover_workflow_defs, load_structured


def register(app: typer.Typer) -> None:
	app.command("validate", help="Static validator (schema + topology + priorities + lookup-permission).")(validate_cmd)


def validate_cmd(
	def_path: Path | None = typer.Option(
		None,
		"--def",
		exists=False,
		dir_okay=False,
		file_okay=True,
		help="Single workflow definition file. Defaults to scanning ./workflows.",
	),
	root: Path = typer.Option(
		Path("workflows"),
		"--root",
		help="Root directory scanned for definition.json files when --def is omitted.",
	),
) -> None:
	"""Validate one or all workflow definitions under *root*."""

	assert def_path is not None or root is not None
	if def_path is not None:
		paths = [def_path]
	else:
		paths = discover_workflow_defs(root)

	if not paths:
		typer.echo(f"no workflow definitions found under {root}")
		raise typer.Exit(code=1)

	if def_path is None:
		typer.echo(f"checking {len(paths)} definitions in {root}/\n")
	total_errors = 0
	total_warnings = 0
	for path in paths:
		header, report = _check_one(path)
		typer.echo(header)
		_print_report(report)
		typer.echo("")
		total_errors += len(report.errors)
		total_warnings += len(report.warnings)

	summary = f"{total_errors} error{'s' if total_errors != 1 else ''}, {total_warnings} warning{'s' if total_warnings != 1 else ''}."
	if total_errors:
		typer.echo(f"{summary} validation failed.")
		raise typer.Exit(code=1)
	typer.echo(f"{summary} validation ok.")


def _check_one(path: Path) -> tuple[str, ValidationReport]:
	try:
		raw: Any = load_structured(path)
	except Exception as exc:
		report = ValidationReport()
		report.errors.append(f"could not read {path}: {exc}")
		return f"{path}", report

	key = raw.get("key", path.stem) if isinstance(raw, dict) else path.stem
	version = raw.get("version", "?") if isinstance(raw, dict) else "?"
	report = _validate(raw)
	return f"{key}@{version}", report


def _print_report(report: ValidationReport) -> None:
	# Per §10.3 sample, on success we list each check explicitly so users
	# see the same shape regardless of error state.
	if report.ok:
		typer.echo("  ✓ schema valid")
		typer.echo("  ✓ no unreachable states")
		typer.echo("  ✓ no dead-end transitions")
		typer.echo("  ✓ duplicate-priority check")
		typer.echo("  ✓ lookup-permission check")
		typer.echo("  ✓ subworkflow cycle check")
		for warn in report.warnings:
			typer.echo(f"  ⚠ {warn}")
		return

	for err in report.errors:
		typer.echo(f"  ✗ {err}")
	for warn in report.warnings:
		typer.echo(f"  ⚠ {warn}")
