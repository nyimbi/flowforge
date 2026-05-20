"""``flowforge replay`` — replay recorded workflow events for determinism checks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer

from flowforge.dsl import WorkflowDef
from flowforge.replay.reconstruct import reconstruct

from .._io import load_structured


def register(app: typer.Typer) -> None:
	app.command("replay", help="Replay workflow events and print the reconstructed final state.")(replay_cmd)


def replay_cmd(
	def_path: Path | None = typer.Option(
		None,
		"--def",
		exists=True,
		dir_okay=False,
		help="Workflow definition file to replay against.",
	),
	event: list[str] = typer.Option(
		[],
		"--event",
		help="Event name to replay. Repeatable or comma-separated.",
	),
	events_file: Path | None = typer.Option(
		None,
		"--events-file",
		exists=True,
		dir_okay=False,
		help="JSON/YAML file containing events as strings or {event,payload} objects.",
	),
	context_path: Path | None = typer.Option(
		None,
		"--context",
		exists=True,
		dir_okay=False,
		help="Optional initial-context JSON/YAML fixture.",
	),
	instance_id: str | None = typer.Option(None, "--instance-id", help="Optional deterministic instance id."),
) -> None:
	"""Replay events through the deterministic engine reconstructor."""

	if def_path is None:
		typer.echo("error: replay requires --def <workflow-definition>", err=True)
		raise typer.Exit(2)
	try:
		workflow = WorkflowDef.model_validate(load_structured(def_path))
		initial_context = load_structured(context_path) if context_path is not None else None
		replay_events = _load_events(event, events_file)
		instance = asyncio.run(
			reconstruct(
				workflow,
				replay_events,
				initial_context=initial_context,
				instance_id=instance_id,
			)
		)
	except Exception as exc:
		typer.echo(f"error: {exc}", err=True)
		raise typer.Exit(2) from exc

	typer.echo(f"replay events: {len(replay_events)}")
	typer.echo(f"final state: {instance.state}")
	typer.echo(f"history: {', '.join(instance.history) if instance.history else '(empty)'}")


def _load_events(raw_events: list[str], events_file: Path | None) -> list[tuple[str, dict[str, Any]]]:
	events: list[tuple[str, dict[str, Any]]] = []
	for entry in raw_events:
		for name in entry.split(","):
			name = name.strip()
			if name:
				events.append((name, {}))
	if events_file is None:
		return events
	data = load_structured(events_file)
	raw = data.get("events")
	if not isinstance(raw, list):
		raise ValueError("--events-file must contain an events list")
	for idx, item in enumerate(raw):
		if isinstance(item, str):
			events.append((item, {}))
		elif isinstance(item, dict):
			name = item.get("event") or item.get("name")
			if not isinstance(name, str) or not name:
				raise ValueError(f"events[{idx}] must include event/name")
			payload = item.get("payload") or {}
			if not isinstance(payload, dict):
				raise ValueError(f"events[{idx}].payload must be an object")
			events.append((name, payload))
		else:
			raise ValueError(f"events[{idx}] must be a string or object")
	return events
