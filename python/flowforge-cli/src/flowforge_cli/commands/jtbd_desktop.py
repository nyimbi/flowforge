"""``flowforge jtbd desktop`` - launch the optional JTBD desktop editor."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
	app.command(
		"desktop",
		help="Open the PyQt JTBD desktop editor for visual bundle authoring.",
	)(jtbd_desktop_cmd)


def jtbd_desktop_cmd(
	bundle: Annotated[
		Path | None,
		typer.Option(
			"--bundle",
			"-b",
			exists=False,
			dir_okay=False,
			help="JTBD bundle JSON/YAML to open. A new bundle is created if omitted.",
		),
	] = None,
	theme: Annotated[
		Path | None,
		typer.Option(
			"--theme",
			exists=False,
			dir_okay=False,
			help="Optional JSON theme file for host-app skinning.",
		),
	] = None,
) -> None:
	"""Launch the optional desktop editor."""

	if bundle is not None and not bundle.exists():
		typer.echo(f"error: bundle not found: {bundle}", err=True)
		raise typer.Exit(1)
	if theme is not None and not theme.exists():
		typer.echo(f"error: theme not found: {theme}", err=True)
		raise typer.Exit(1)

	try:
		from ..jtbd_desktop.app import run_desktop_editor
	except (RuntimeError, ValueError, OSError) as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(1) from exc

	try:
		code = run_desktop_editor(bundle=bundle, theme=theme)
	except RuntimeError as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(1) from exc
	raise typer.Exit(code)
