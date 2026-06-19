"""Workflow replay debugger.

Reconstructs the step-by-step history of a workflow instance by feeding
a sequence of audit events through the workflow definition.  Useful for
debugging, incident investigation, and building ops dashboards.

Usage::

    from flowforge.engine.replay import replay_from_events, ReplayResult

    events = await audit_sink.query_events(subject_id=instance_id)
    result = replay_from_events(wd, events, instance_id=instance_id)
    for step in result.steps:
        print(f"{step.from_state} --[{step.event}]--> {step.to_state}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..dsl.workflow_def import WorkflowDef
from ..ports.types import AuditEvent

_log = logging.getLogger(__name__)

# Audit event kind pattern: "wf.<def_key>.transitioned"
_TRANSITION_SUFFIX = ".transitioned"


@dataclass
class ReplayStep:
	"""One step in a replayed workflow instance."""

	seq: int
	event: str
	from_state: str
	to_state: str
	timestamp: datetime
	actor_id: str | None = None
	payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayResult:
	"""Complete replay of a workflow instance."""

	instance_id: str
	def_key: str
	steps: list[ReplayStep]
	initial_state: str
	final_state: str
	is_consistent: bool
	errors: list[str] = field(default_factory=list)

	@property
	def state_at(self) -> dict[int, str]:
		"""Map seq → state after that step."""
		result: dict[int, str] = {}
		state = self.initial_state
		for step in self.steps:
			state = step.to_state
			result[step.seq] = state
		return result

	def state_after_step(self, seq: int) -> str:
		"""Return the instance state immediately after step *seq*."""
		state = self.initial_state
		for step in self.steps:
			state = step.to_state
			if step.seq >= seq:
				break
		return state


def replay_from_events(
	wd: WorkflowDef,
	events: list[AuditEvent],
	*,
	instance_id: str | None = None,
) -> ReplayResult:
	"""Reconstruct instance history from a list of audit events.

	Events are sorted by ``occurred_at`` before processing.  Only
	``.transitioned`` events are replayed; other event kinds are
	silently skipped.

	Args:
		wd: The workflow definition the instance was running under.
		events: Audit events — typically retrieved from ``PgAuditSink``
		        filtered by ``subject_id``.
		instance_id: Used in the result; inferred from the first event
		             if not supplied.

	Returns:
		A :class:`ReplayResult` with ``is_consistent=True`` when every
		step's ``from_state`` matches the expected state after the
		previous step, and all states are valid in *wd*.
	"""
	# Sort events chronologically
	sorted_events = sorted(events, key=lambda e: e.occurred_at)

	# Infer instance_id
	iid = instance_id
	if iid is None and sorted_events:
		iid = sorted_events[0].subject_id
	iid = iid or "unknown"

	valid_state_names = {s.name for s in wd.states}
	steps: list[ReplayStep] = []
	errors: list[str] = []
	seq = 0

	# Determine initial state from WD
	current_state = wd.initial_state

	def_key_prefix = f"wf.{wd.key}."

	for ev in sorted_events:
		# Only process transition events for this workflow
		if not ev.kind.startswith(def_key_prefix):
			continue
		if not ev.kind.endswith(_TRANSITION_SUFFIX):
			continue

		payload = ev.payload or {}
		from_state = payload.get("from_state", "")
		to_state = payload.get("to_state", "")
		event_name = payload.get("event", ev.kind)
		actor_id = payload.get("actor_id") or getattr(ev, "actor_id", None)

		if not from_state or not to_state:
			errors.append(
				f"step {seq}: transition event {ev.kind!r} missing from_state/to_state in payload"
			)
			continue

		# Consistency check
		if from_state != current_state:
			errors.append(
				f"step {seq}: expected from_state={current_state!r} but event has {from_state!r}"
			)
		if from_state not in valid_state_names:
			errors.append(f"step {seq}: from_state={from_state!r} not in workflow definition")
		if to_state not in valid_state_names:
			errors.append(f"step {seq}: to_state={to_state!r} not in workflow definition")

		steps.append(ReplayStep(
			seq=seq,
			event=event_name,
			from_state=from_state,
			to_state=to_state,
			timestamp=ev.occurred_at,
			actor_id=actor_id,
			payload=payload,
		))
		current_state = to_state
		seq += 1

	return ReplayResult(
		instance_id=iid,
		def_key=wd.key,
		steps=steps,
		initial_state=wd.initial_state,
		final_state=current_state,
		is_consistent=len(errors) == 0,
		errors=errors,
	)


def replay_summary(result: ReplayResult) -> str:
	"""Return a compact human-readable replay summary."""
	lines = [
		f"Instance: {result.instance_id}  def: {result.def_key}",
		f"Initial: {result.initial_state}  Final: {result.final_state}",
		f"Steps: {len(result.steps)}  Consistent: {result.is_consistent}",
	]
	for step in result.steps:
		ts = step.timestamp.strftime("%Y-%m-%dT%H:%M:%S")
		actor = f" [{step.actor_id}]" if step.actor_id else ""
		lines.append(f"  {step.seq:3d}  {ts}{actor}  {step.from_state} --[{step.event}]--> {step.to_state}")
	if result.errors:
		lines.append("Errors:")
		for err in result.errors:
			lines.append(f"  ! {err}")
	return "\n".join(lines)


__all__ = ["ReplayStep", "ReplayResult", "replay_from_events", "replay_summary"]
