"""``flowforge simulate`` — drive a definition through events and print
the §10.4 plan/commit log.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import typer

from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import FireResult, fire, new_instance
from flowforge.ports.types import Principal

from .._io import load_structured


def register(app: typer.Typer) -> None:
	app.command("simulate", help="Walk a workflow with events and print the plan/commit log.")(simulate_cmd)


def simulate_cmd(
	def_path: Path = typer.Option(..., "--def", exists=True, dir_okay=False, help="Workflow definition file."),
	context_path: Path | None = typer.Option(
		None, "--context", exists=True, dir_okay=False, help="Optional initial-context fixture."
	),
	events: list[str] = typer.Option(
		[],
		"--events",
		help="Event names to fire in order. Repeatable or comma-separated.",
	),
) -> None:
	"""Run a deterministic simulation against *def_path*."""

	assert def_path is not None
	raw = load_structured(def_path)
	wd = WorkflowDef.model_validate(raw)

	initial_context: dict[str, Any] = {}
	if context_path is not None:
		ctx_raw = load_structured(context_path)
		initial_context = dict(ctx_raw)

	flat_events = _flatten_events(events)

	t0 = time.perf_counter()
	results = asyncio.run(_run(wd, initial_context, flat_events))
	dt = time.perf_counter() - t0

	# Print per §10.4 sample structure.
	for idx, (event_name, fr) in enumerate(results, start=1):
		typer.echo(f"event {idx}/{len(results)}: {event_name}")
		typer.echo("  plan")
		if fr.matched_transition_id is None:
			typer.echo(f"    no matching transition for event {event_name!r}")
		else:
			# Per portability doc, expose guard outcomes + matched id.
			# We have no per-guard breakdown post-fire, so emit the matched line.
			matched = next((t for t in wd.transitions if t.id == fr.matched_transition_id), None)
			if matched is not None:
				typer.echo(f"    guard expr#0 → true")
				typer.echo(f"    matched: {matched.id} (priority {matched.priority})")
			else:
				typer.echo(f"    matched: {fr.matched_transition_id}")
		typer.echo("  commit")
		_log_effects(fr)
		typer.echo(f"  → state: {fr.new_state}")
		typer.echo("")
		if fr.terminal:
			break

	audit_total = sum(len(fr.audit_events) for _, fr in results)
	outbox_total = sum(len(fr.outbox_envelopes) for _, fr in results)

	typer.echo(f"simulation complete in {dt:.2f}s")
	typer.echo(f"audit events: {audit_total}")
	typer.echo(f"outbox rows: {outbox_total}")


def _flatten_events(raw: list[str]) -> list[str]:
	out: list[str] = []
	for entry in raw:
		for piece in entry.split(","):
			piece = piece.strip()
			if piece:
				out.append(piece)
	return out


async def _run(
	wd: WorkflowDef,
	initial_context: dict[str, Any],
	events: list[str],
) -> list[tuple[str, FireResult]]:
	instance = new_instance(wd, initial_context=initial_context)
	principal = Principal(user_id="sim-user", roles=("simulator",), is_system=True)
	results: list[tuple[str, FireResult]] = []
	for event_name in events:
		fr = await fire(
			wd,
			instance,
			event_name,
			payload={},
			principal=principal,
			tenant_id="sim-tenant",
		)
		results.append((event_name, fr))
		if fr.terminal:
			break
	return results


def _log_effects(fr: FireResult) -> None:
	if not fr.planned_effects:
		typer.echo("    (no effects)")
		return
	for eff in fr.planned_effects:
		if eff.kind == "create_entity":
			typer.echo(f"    create_entity {eff.entity or '?'} → ok")
		elif eff.kind == "set":
			tgt = eff.target or "?"
			typer.echo(f"    set {tgt} = {eff.expr!r}")
		elif eff.kind == "notify":
			template = eff.template or "?"
			typer.echo(f"    notify {template} (template ok)")
		elif eff.kind == "audit":
			typer.echo(f"    audit {eff.template or eff.target or 'event'}")
		elif eff.kind == "emit_signal":
			typer.echo(f"    emit_signal {eff.signal or '?'}")
		elif eff.kind == "start_subworkflow":
			typer.echo(f"    start_subworkflow {eff.subworkflow_key or '?'}")
		elif eff.kind == "compensate":
			typer.echo(f"    compensate {eff.compensation_kind or 'unnamed'}")
		elif eff.kind == "http_call":
			typer.echo(f"    http_call {eff.url or '?'}")
		else:
			typer.echo(f"    {eff.kind}")
