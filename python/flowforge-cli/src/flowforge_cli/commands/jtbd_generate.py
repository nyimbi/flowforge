"""``flowforge jtbd-generate`` — run the deterministic JTBD generator.

Reads a JTBD bundle, runs the U19 generator pipeline, and writes the
emitted files under ``--out``. The generator itself is the same code
exercised by ``tests/test_jtbd_generators.py``; this command is a thin
disk-writing shim.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .._io import load_structured
from ..jtbd import generate
from ..jtbd.overrides import resolve_sidecar
from ..jtbd.parse import JTBDParseError


def register(app: typer.Typer) -> None:
	app.command(
		"jtbd-generate",
		help="Run the deterministic JTBD generator over a bundle and write artefacts to disk.",
	)(jtbd_generate_cmd)


def jtbd_generate_cmd(
	jtbd: Path = typer.Option(..., "--jtbd", exists=True, dir_okay=False, help="JTBD bundle file."),
	out: Path = typer.Option(Path.cwd(), "--out", help="Output root (default: cwd)."),
	force: bool = typer.Option(False, "--force", help="Allow writing into a non-empty target."),
	overrides_path: Path | None = typer.Option(
		None,
		"--overrides",
		exists=False,
		dir_okay=False,
		help=(
			"Copy-override sidecar (per ADR-002, v0.3.0 W4b item 22). "
			"Defaults to the co-located <bundle>.overrides.json when present; "
			"explicit flag wins over the co-located file."
		),
	),
) -> None:
	"""Generate every artefact from *jtbd* under *out*."""

	assert jtbd is not None
	out = out.resolve()

	bundle = load_structured(jtbd)
	# Per ADR-002 lookup precedence: --overrides flag > co-located
	# <bundle>.overrides.json > none (canonical). ``resolve_sidecar``
	# centralises that contract.
	overrides = resolve_sidecar(jtbd, overrides_path)
	try:
		files = generate(bundle, overrides=overrides)
	except JTBDParseError as exc:
		raise typer.BadParameter(str(exc)) from exc

	if out.exists() and any(out.iterdir()) and not force:
		raise typer.BadParameter(f"target {out} exists and is not empty (use --force).")
	out.mkdir(parents=True, exist_ok=True)

	for f in files:
		dst = out / f.path
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(f.content, encoding="utf-8")
		typer.echo(f"  wrote {f.path}")
	typer.echo("")
	typer.echo(f"jtbd-generate: {len(files)} files written to {out}")
