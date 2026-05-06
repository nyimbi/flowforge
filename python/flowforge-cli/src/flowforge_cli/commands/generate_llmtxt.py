"""``flowforge generate-llmtxt`` — render llm.txt from a JTBD bundle.

Per ``framework/docs/flowforge-evolution.md`` §13 (E-29). Standalone
companion to the ``flowforge new --emit-llmtxt`` flag — re-run after
every meaningful bundle edit so the agent quickstart stays current.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .._io import load_structured
from ..llmtxt import write_llmtxt


def register(app: typer.Typer) -> None:
	app.command(
		"generate-llmtxt",
		help="Render llm.txt for an existing project from its JTBD bundle.",
	)(generate_llmtxt_cmd)


def generate_llmtxt_cmd(
	bundle: Path = typer.Option(
		Path("workflows/jtbd_bundle.json"),
		"--bundle",
		"-b",
		exists=False,
		dir_okay=False,
		help="JTBD bundle to render from. JSON or YAML.",
	),
	out: Path = typer.Option(
		Path("llm.txt"),
		"--out",
		"-o",
		help="Where to write the rendered llm.txt.",
	),
	bundle_label: str | None = typer.Option(
		None,
		"--bundle-label",
		help=(
			"Path label embedded in the rendered text "
			"(default: --bundle's value)."
		),
	),
	force: bool = typer.Option(
		False,
		"--force",
		help="Overwrite an existing llm.txt without prompting.",
	),
) -> None:
	"""Render llm.txt for an existing project."""
	if not bundle.exists():
		typer.echo(f"error: bundle not found: {bundle}", err=True)
		raise typer.Exit(1)
	if out.exists() and not force:
		typer.echo(
			f"error: {out} already exists; pass --force to overwrite.",
			err=True,
		)
		raise typer.Exit(1)

	raw = load_structured(bundle)
	written = write_llmtxt(
		raw,
		out_path=out,
		bundle_path=bundle_label or str(bundle),
	)
	typer.echo(f"wrote {written} ({len(raw.get('jtbds') or [])} JTBDs)")
