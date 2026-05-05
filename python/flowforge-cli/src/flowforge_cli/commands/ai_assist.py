"""``flowforge ai-assist`` — optional LLM refinement pass.

Skeleton stub.
"""

from __future__ import annotations

from pathlib import Path

import typer


def register(app: typer.Typer) -> None:
	app.command("ai-assist", help="Optional LLM refinement pass on a JTBD bundle (skeleton).")(ai_assist_cmd)


def ai_assist_cmd(
	jtbd: Path = typer.Argument(..., help="JTBD bundle to refine."),
) -> None:
	raise NotImplementedError(f"flowforge ai-assist {jtbd!s} is not yet implemented.")
