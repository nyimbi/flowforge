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

E-32 / audit-fix-plan §4.1 (C-01, C-04): fire is per-instance serialised
and rolls back the Instance snapshot if outbox or audit dispatch raises.
The outbox-dispatch-then-audit-record order is deliberate: outbox is the
failure-prone phase, so an outbox raise leaves the audit log free of an
orphan transition row. See :class:`ConcurrentFireRejected` and
:class:`OutboxDispatchError` for the failure surfaces.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from .. import config
from .._uuid7 import uuid7str
from ..dsl import Effect, Transition, WorkflowDef
from ..expr import EvaluationError, evaluate
from ..ports.types import (
	AuditEvent,
	ExecutionContext,
	OutboxEnvelope,
	Principal,
)


# ---------------------------------------------------------------------------
# E-32 / C-04: per-instance serialisation gate.
# ---------------------------------------------------------------------------
#
# A plain ``set`` is sufficient to serialise concurrent ``fire()`` calls
# against the same ``instance.id`` because the asyncio event loop is
# single-threaded: the check + add cannot interleave with another
# coroutine until we ``await`` something. We add the id BEFORE the first
# await of the function. Losing concurrent fires raise
# :class:`ConcurrentFireRejected` immediately, satisfying the C-04
# acceptance criterion ("exactly 1 transition; others raise").
_FIRING_INSTANCES: set[str] = set()


class ConcurrentFireRejected(RuntimeError):
	"""A second ``fire()`` was attempted while one is already in flight
	for the same ``instance.id``.

	Audit-fix-plan §4.1 C-04 acceptance criterion.
	"""

	def __init__(self, instance_id: str) -> None:
		super().__init__(
			f"fire(instance_id={instance_id!r}) rejected: another fire is in flight",
		)
		self.instance_id = instance_id


class GuardEvaluationError(RuntimeError):
	"""A transition guard expression failed to evaluate.

	Audit-fix-plan §4.2 C-03 acceptance criterion. Replaces the previous
	``except EvaluationError: return False`` swallow which masked DSL
	authoring bugs as silent no-match results.
	"""

	def __init__(self, transition_id: str, expr: Any) -> None:
		super().__init__(
			f"guard evaluation failed for transition {transition_id!r}: expr={expr!r}",
		)
		self.transition_id = transition_id
		self.expr = expr


class InvalidTargetError(ValueError):
	"""A `set` effect target is malformed (empty or no dotted path beyond
	the namespace prefix).

	Audit-fix-plan §4.2 C-08 acceptance criterion. ``"context"`` alone or
	``""`` would previously have written the entire instance context as a
	single root replacement; now they raise.
	"""

	def __init__(self, target: str) -> None:
		super().__init__(f"invalid set target {target!r}: needs a dotted path under 'context.'")
		self.target = target


class OutboxDispatchError(RuntimeError):
	"""Outbox dispatch failed during a fire; the Instance has been rolled
	back to its pre-fire snapshot and no audit row was written.

	The original transport-layer exception is chained as ``__cause__``.

	Audit-fix-plan §4.1 C-01 acceptance criterion.
	"""

	def __init__(self, instance_id: str, envelope_kind: str | None = None) -> None:
		msg = f"outbox dispatch failed during fire(instance_id={instance_id!r})"
		if envelope_kind:
			msg += f"; envelope.kind={envelope_kind!r}"
		super().__init__(msg)
		self.instance_id = instance_id
		self.envelope_kind = envelope_kind


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

	# E-39 / C-02: UUID7 ids are time-ordered → audit chain + B-tree
	# friendly. ``uuid7str`` is the project-wide convention (CLAUDE.md).
	return Instance(
		id=instance_id or uuid7str(),
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
	"""Evaluate every guard against *ctx*; return True iff all are truthy.

	E-39 / C-03: a guard whose expression *fails to evaluate* (unknown op,
	bad shape, inner exception) raises :class:`GuardEvaluationError` so
	authoring bugs surface instead of silently shadowing as no-match.
	A guard that successfully evaluates to a falsy value still returns
	False — that is the legitimate "guard didn't match" path.
	"""

	for g in transition.guards:
		try:
			result = evaluate(g.expr, ctx)
		except EvaluationError as exc:
			raise GuardEvaluationError(transition.id, g.expr) from exc
		if not bool(result):
			return False
	return True


def _apply_effect(effect: Effect, instance: Instance, ctx: dict[str, Any]) -> tuple[list[AuditEvent], list[OutboxEnvelope]]:
	audits: list[AuditEvent] = []
	outboxes: list[OutboxEnvelope] = []

	if effect.kind == "create_entity":
		values = {k: evaluate(v, ctx) for k, v in (effect.values or {}).items()}
		# E-39 / C-02: time-ordered ids for entity rows.
		row = {**values, "id": uuid7str(), "status": values.get("status", "draft")}
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
	"""Write *value* into *target* at the dotted *path*.

	E-39 / C-08: a path like ``""`` or ``"context"`` (no dotted suffix
	beyond the namespace) is invalid — those would previously have either
	silently no-op'd or written to the root. They now raise
	:class:`InvalidTargetError` so authoring bugs surface.
	"""

	parts = [p for p in path.split(".") if p]
	# Strip leading "context." — that's the engine namespace.
	if parts and parts[0] == "context":
		parts = parts[1:]
	if not parts:
		raise InvalidTargetError(path)
	cur = target
	for p in parts[:-1]:
		nxt = cur.get(p)
		if not isinstance(nxt, dict):
			nxt = {}
			cur[p] = nxt
		cur = nxt
	cur[parts[-1]] = value


# E-39 / C-05: explicit non-JSON marker keeps replay deterministic and
# distinguishes "I gave up serialising this" from "the user really meant
# the string repr".
_NON_JSON_MARKER = "__non_json__"


def _json_safe(obj: Any) -> Any:
	"""Return *obj* unchanged when JSON-serialisable; replace
	non-serialisable values (recursively) with an explicit marker
	``{"__non_json__": "<repr(obj)>"}``.

	E-39 / C-05 acceptance criterion: marker, not bare repr.
	"""

	try:
		json.dumps(obj)
		return obj
	except TypeError:
		# obj is itself non-serialisable — replace at this node.
		if isinstance(obj, dict):
			return {k: _json_safe(v) for k, v in obj.items()}
		if isinstance(obj, list):
			return [_json_safe(v) for v in obj]
		if isinstance(obj, tuple):
			return [_json_safe(v) for v in obj]
		return {_NON_JSON_MARKER: repr(obj)}


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

	# E-32 / C-04: per-instance serialisation. The check-and-add is a
	# single synchronous step, so two coroutines cannot both pass the
	# gate. The first awaitable in this function comes after the gate.
	if instance.id in _FIRING_INSTANCES:
		raise ConcurrentFireRejected(instance.id)
	_FIRING_INSTANCES.add(instance.id)
	try:
		return await _fire_locked(
			wd,
			instance,
			event,
			payload=payload,
			principal=principal,
			tenant_id=tenant_id,
			jtbd_id=jtbd_id,
			jtbd_version=jtbd_version,
		)
	finally:
		_FIRING_INSTANCES.discard(instance.id)


async def _fire_locked(
	wd: WorkflowDef,
	instance: Instance,
	event: str,
	*,
	payload: dict[str, Any] | None,
	principal: Principal | None,
	tenant_id: str,
	jtbd_id: str | None,
	jtbd_version: str | None,
) -> FireResult:
	"""Body of :func:`fire` after the per-instance gate has been claimed.

	Split out so the gate's `try / finally` is tight and the
	rollback-on-failure path is unambiguously distinct from the gate's
	cleanup.
	"""

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

	# E-32 / C-01: capture pre-mutation snapshot. Rollback restores all
	# Instance dataclass fields that fire() may have mutated.
	pre_snapshot = _snapshot_instance(instance)

	# Phase 2 (plan effects): build audit + outbox lists in memory; do
	# NOT yet dispatch.
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

	# E-32 / C-01: dispatch order is outbox → audit. Outbox is the
	# failure-prone phase (network, broker); raising here leaves the
	# audit sink untouched, so "audit row absent" is naturally true on
	# rollback. Audit raises (rare) also rollback Instance state — the
	# already-dispatched outbox envelopes are tolerated as orphans
	# (documented; recovered by the outbox worker idempotency contract).
	if config.outbox is not None:
		for env in outboxes:
			try:
				await config.outbox.dispatch(env)
			except Exception as e:
				_restore_instance(instance, pre_snapshot)
				raise OutboxDispatchError(instance.id, env.kind) from e

	if config.audit is not None:
		try:
			for evt in audits:
				await config.audit.record(evt)
		except Exception:
			_restore_instance(instance, pre_snapshot)
			raise

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


def _snapshot_instance(instance: Instance) -> dict[str, Any]:
	"""Capture a deep copy of every Instance field fire() may mutate.

	Used by the C-01 rollback-on-dispatch-failure path.
	"""

	return {
		"state": instance.state,
		"context": copy.deepcopy(instance.context),
		"created_entities": list(instance.created_entities),
		"saga": copy.deepcopy(instance.saga),
		"history": list(instance.history),
	}


def _restore_instance(instance: Instance, snapshot: dict[str, Any]) -> None:
	"""Restore Instance to *snapshot*. Mutates in place."""

	instance.state = snapshot["state"]
	instance.context = snapshot["context"]
	instance.created_entities = snapshot["created_entities"]
	instance.saga = snapshot["saga"]
	instance.history = snapshot["history"]


def _is_terminal(wd: WorkflowDef, state_name: str) -> bool:
	for s in wd.states:
		if s.name == state_name:
			return s.kind in ("terminal_success", "terminal_fail")
	return False


def make_context(tenant_id: str, principal: Principal, *, elevated: bool = False) -> ExecutionContext:
	"""Convenience builder mirrored by host adapters."""
	return ExecutionContext(tenant_id=tenant_id, principal=principal, elevated=elevated)
