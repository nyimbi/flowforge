"""``flowforge diff`` — pretty diff of two workflow definition files."""

from __future__ import annotations

from pathlib import Path

import typer

from flowforge.compiler.diff import diff_workflow_dicts

from .._io import load_structured


def register(app: typer.Typer) -> None:
	app.command("diff", help="Pretty diff of two workflow definition versions.")(diff_cmd)


def diff_cmd(
	a: Path = typer.Argument(..., exists=True, dir_okay=False, help="First workflow definition file."),
	b: Path = typer.Argument(..., exists=True, dir_okay=False, help="Second workflow definition file."),
	exit_zero: bool = typer.Option(False, "--exit-zero", help="Exit 0 even when a diff is present."),
) -> None:
	"""Print a structural diff between two workflow definitions."""

	try:
		diff = diff_workflow_dicts(load_structured(a), load_structured(b))
	except Exception as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(2) from exc
	typer.echo(diff.summary())
	if not exit_zero and not diff.is_empty():
		raise typer.Exit(1)
