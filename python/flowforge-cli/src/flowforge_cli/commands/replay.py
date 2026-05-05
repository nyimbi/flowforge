"""``flowforge replay`` — replay a recorded event for determinism checks.

Skeleton stub.
"""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
	app.command("replay", help="Replay a workflow event and assert deterministic outcome (skeleton).")(replay_cmd)


def replay_cmd(
	event: str = typer.Option(..., "--event", help="Event UUID to replay."),
) -> None:
	raise NotImplementedError(f"flowforge replay --event {event} is not yet implemented.")
