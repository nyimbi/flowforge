"""``flowforge ai-assist`` — local AI-authoring prompt generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from .._io import load_structured
from ..jtbd_desktop.document import build_ai_authoring_prompt


def register(app: typer.Typer) -> None:
	app.command("ai-assist", help="Generate a review prompt for AI-assisted JTBD authoring.")(ai_assist_cmd)


def ai_assist_cmd(
	jtbd: Path = typer.Argument(..., exists=True, dir_okay=False, help="JTBD bundle to refine."),
	job_id: str | None = typer.Option(None, "--job", help="Optional JTBD id to focus the prompt on."),
	out: Path | None = typer.Option(None, "--out", dir_okay=False, help="Write the prompt to a file."),
) -> None:
	"""Create a deterministic, copyable prompt for external AI assistance."""

	try:
		bundle = load_structured(jtbd)
		selected = _select_jtbd(bundle, job_id)
		prompt = build_ai_authoring_prompt(bundle, selected)
	except Exception as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(2) from exc
	if out is not None:
		out.parent.mkdir(parents=True, exist_ok=True)
		out.write_text(prompt, encoding="utf-8")
		typer.echo(f"wrote AI authoring prompt: {out}")
	else:
		typer.echo(prompt)


def _select_jtbd(bundle: dict[str, Any], job_id: str | None) -> dict[str, Any] | None:
	if job_id is None:
		return None
	for item in bundle.get("jtbds", []) or []:
		if isinstance(item, dict) and item.get("id") == job_id:
			return item
	raise ValueError(f"JTBD id not found: {job_id}")
