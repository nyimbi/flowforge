"""Two-phase fire algorithm.

Phase 1 (plan): for the given (instance, event), enumerate candidate
transitions whose ``from_state`` matches, run their guards in priority
order, return the highest-priority match plus a planned-effect list.

Phase 2 (commit): apply effects to the in-memory instance, append to the
saga ledger when ``compensate`` effects fire, record audit events through
:mod:`flowforge.config` ports, push outbox envelopes for ``notify`` /
signal effects.

The engine does NOT do storage — it operates on the snapshot store
abstraction. Hosts wire ``InMemorySnapshotStore`` (default) or a
``flowforge-sqlalchemy`` impl.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from .. import config
from ..dsl import Effect, Transition, WorkflowDef
from ..expr import EvaluationError, evaluate
from ..ports.types import (
	AuditEvent,
	ExecutionContext,
	OutboxEnvelope,
	Principal,
)


@dataclass
class Instance:
	"""In-memory state of one workflow instance."""

	id: str
	def_key: str
	def_version: str
	state: str
	context: dict[str, Any] = field(default_factory=dict)
	created_entities: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
	saga: list[dict[str, Any]] = field(default_factory=list)
	history: list[str] = field(default_factory=list)


@dataclass
class FireResult:
	instance: Instance
	matched_transition_id: str | None
	planned_effects: list[Effect]
	new_state: str
	terminal: bool
	audit_events: list[AuditEvent] = field(default_factory=list)
	outbox_envelopes: list[OutboxEnvelope] = field(default_factory=list)


def new_instance(
	wd: WorkflowDef,
	*,
	instance_id: str | None = None,
	initial_context: dict[str, Any] | None = None,
) -> Instance:
	"""Create a fresh Instance pinned to *wd*."""

	return Instance(
		id=instance_id or str(uuid.uuid4()),
		def_key=wd.key,
		def_version=wd.version,
		state=wd.initial_state,
		context=dict(initial_context or {}),
	)


def _match_transitions(wd: WorkflowDef, instance: Instance, event: str) -> list[Transition]:
	candidates = [t for t in wd.transitions if t.from_state == instance.state and t.event == event]
	# Highest priority first; on ties the validator already complains.
	candidates.sort(key=lambda t: -t.priority)
	return candidates


def _guards_pass(transition: Transition, ctx: dict[str, Any]) -> bool:
	for g in transition.guards:
		try:
			if not bool(evaluate(g.expr, ctx)):
				return False
		except EvaluationError:
			return False
	return True


def _apply_effect(effect: Effect, instance: Instance, ctx: dict[str, Any]) -> tuple[list[AuditEvent], list[OutboxEnvelope]]:
	audits: list[AuditEvent] = []
	outboxes: list[OutboxEnvelope] = []

	if effect.kind == "create_entity":
		values = {k: evaluate(v, ctx) for k, v in (effect.values or {}).items()}
		row = {**values, "id": str(uuid.uuid4()), "status": values.get("status", "draft")}
		instance.created_entities.append((effect.entity or "<unknown>", row))
		audits.append(
			AuditEvent(
				kind=f"wf.{instance.def_key}.entity_created",
				subject_kind=effect.entity or "unknown",
				subject_id=row["id"],
				tenant_id=ctx.get("__tenant_id__", ""),
				actor_user_id=ctx.get("__actor__"),
				payload={"values": values},
			)
		)
	elif effect.kind == "set":
		target = effect.target or ""
		val = evaluate(effect.expr, ctx)
		_set_dotted(instance.context, target, val)
	elif effect.kind == "notify":
		notify_body: dict[str, Any] = {
			"template": effect.template,
			"instance_id": instance.id,
		}
		# Propagate JTBD provenance for observability dashboards (E-10).
		if ctx.get("__jtbd_id__") is not None:
			notify_body["jtbd_id"] = ctx["__jtbd_id__"]
		if ctx.get("__jtbd_version__") is not None:
			notify_body["jtbd_version"] = ctx["__jtbd_version__"]
		outboxes.append(
			OutboxEnvelope(
				kind="wf.notify",
				tenant_id=ctx.get("__tenant_id__", ""),
				body=notify_body,
				correlation_id=instance.id,
			)
		)
	elif effect.kind == "audit":
		audits.append(
			AuditEvent(
				kind=str(effect.template or f"wf.{instance.def_key}.audit"),
				subject_kind=instance.def_key,
				subject_id=instance.id,
				tenant_id=ctx.get("__tenant_id__", ""),
				actor_user_id=ctx.get("__actor__"),
				payload={"context_snapshot": _json_safe(instance.context)},
			)
		)
	elif effect.kind == "compensate":
		instance.saga.append({"kind": effect.compensation_kind, "args": effect.values or {}})
	elif effect.kind == "emit_signal":
		outboxes.append(
			OutboxEnvelope(
				kind="wf.signal",
				tenant_id=ctx.get("__tenant_id__", ""),
				body={"signal": effect.signal, "instance_id": instance.id},
			)
		)
	elif effect.kind == "update_entity":
		# Engine does not own entity storage — host EntityAdapter handles
		# the actual update. Audit the intent only.
		audits.append(
			AuditEvent(
				kind=f"wf.{instance.def_key}.entity_update_requested",
				subject_kind=effect.entity or "unknown",
				subject_id=str(evaluate(effect.target, ctx)) if effect.target else "?",
				tenant_id=ctx.get("__tenant_id__", ""),
				actor_user_id=ctx.get("__actor__"),
				payload={"values": effect.values or {}},
			)
		)
	# `start_subworkflow`, `http_call` are framework-stable but not exercised
	# by unit-level fire; subworkflow.py wraps it.
	return audits, outboxes


def _set_dotted(target: dict[str, Any], path: str, value: Any) -> None:
	parts = [p for p in path.split(".") if p]
	# Strip leading "context." — that's the engine namespace.
	if parts and parts[0] == "context":
		parts = parts[1:]
	cur = target
	for p in parts[:-1]:
		nxt = cur.get(p)
		if not isinstance(nxt, dict):
			nxt = {}
			cur[p] = nxt
		cur = nxt
	if parts:
		cur[parts[-1]] = value


def _json_safe(obj: Any) -> Any:
	try:
		json.dumps(obj)
		return obj
	except TypeError:
		return repr(obj)


async def fire(
	wd: WorkflowDef,
	instance: Instance,
	event: str,
	*,
	payload: dict[str, Any] | None = None,
	principal: Principal | None = None,
	tenant_id: str = "default",
	jtbd_id: str | None = None,
	jtbd_version: str | None = None,
) -> FireResult:
	"""Plan + commit *event* against *instance* per *wd*.

	The engine builds an evaluator-context that puts the workflow's
	``context`` under the ``context`` key so DSL ``var`` expressions like
	``{"var": "context.intake.loss_amount"}`` resolve.

	``jtbd_id`` and ``jtbd_version`` are propagated into every audit event
	and outbox envelope produced during this fire (E-10). Tracing consumers
	use these to group events by originating JTBD spec. Pass ``None`` for
	workflows not originating from a JTBD bundle (backwards-compatible).
	"""

	if instance.state.startswith("terminal_") or _is_terminal(wd, instance.state):
		return FireResult(instance, None, [], instance.state, terminal=True)

	candidates = _match_transitions(wd, instance, event)
	chosen: Transition | None = None
	eval_ctx = {
		"context": instance.context,
		"__tenant_id__": tenant_id,
		"__actor__": principal.user_id if principal else None,
		"__jtbd_id__": jtbd_id,
		"__jtbd_version__": jtbd_version,
		"event": {"name": event, "payload": payload or {}},
	}
	for t in candidates:
		if _guards_pass(t, eval_ctx):
			chosen = t
			break

	if chosen is None:
		return FireResult(instance, None, [], instance.state, terminal=False)

	# Phase 2: commit
	audits: list[AuditEvent] = []
	outboxes: list[OutboxEnvelope] = []
	for effect in chosen.effects:
		a, o = _apply_effect(effect, instance, eval_ctx)
		audits.extend(a)
		outboxes.extend(o)

	prev_state = instance.state
	instance.state = chosen.to_state
	instance.history.append(f"{prev_state}-({chosen.id}:{event})->{chosen.to_state}")

	# Always audit the transition itself.  jtbd_id / jtbd_version are
	# included when present so dashboards can GROUP BY jtbd_id (E-10).
	transition_payload: dict[str, Any] = {
		"transition_id": chosen.id,
		"from_state": prev_state,
		"to_state": chosen.to_state,
		"event": event,
	}
	if jtbd_id is not None:
		transition_payload["jtbd_id"] = jtbd_id
	if jtbd_version is not None:
		transition_payload["jtbd_version"] = jtbd_version

	audits.insert(
		0,
		AuditEvent(
			kind=f"wf.{wd.key}.transitioned",
			subject_kind=wd.subject_kind,
			subject_id=instance.id,
			tenant_id=tenant_id,
			actor_user_id=principal.user_id if principal else None,
			payload=transition_payload,
		),
	)

	# Push to live ports if available.
	if config.audit is not None:
		for evt in audits:
			await config.audit.record(evt)
	if config.outbox is not None:
		for env in outboxes:
			# noqa: best-effort dispatch — replay reconstructs without it
			try:
				await config.outbox.dispatch(env)
			except Exception:
				pass

	terminal = _is_terminal(wd, instance.state)
	return FireResult(
		instance=instance,
		matched_transition_id=chosen.id,
		planned_effects=list(chosen.effects),
		new_state=instance.state,
		terminal=terminal,
		audit_events=audits,
		outbox_envelopes=outboxes,
	)


def _is_terminal(wd: WorkflowDef, state_name: str) -> bool:
	for s in wd.states:
		if s.name == state_name:
			return s.kind in ("terminal_success", "terminal_fail")
	return False


def make_context(tenant_id: str, principal: Principal, *, elevated: bool = False) -> ExecutionContext:
	"""Convenience builder mirrored by host adapters."""
	return ExecutionContext(tenant_id=tenant_id, principal=principal, elevated=elevated)
