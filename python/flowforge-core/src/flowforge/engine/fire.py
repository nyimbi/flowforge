"""Two-phase fire algorithm.

Phase 1 (plan): for the given (instance, event), enumerate candidate
transitions whose ``from_state`` matches, run their guards in priority
order, return the highest-priority match plus a planned-effect list.

Phase 2 (commit): apply effects to the in-memory instance, append to the
saga ledger when ``compensate`` effects fire, and collect audit events
plus outbox envelopes for ``notify`` / signal effects.

The direct engine path does NOT do durable storage. With the default
``dispatch_ports=True`` it also calls :mod:`flowforge.config` audit and
outbox ports after in-memory mutation; hosts must treat that immediate
port-dispatch path as non-atomic unless the configured ports are
transactional enqueue adapters. Critical SQLAlchemy hosts should use
``SqlAlchemySnapshotStore.fire_and_commit(...)``, which invokes
``fire(..., dispatch_ports=False)`` and persists state, event log, audit
rows, and outbox rows in one database transaction.

E-32 / audit-fix-plan §4.1 (C-01, C-04): fire is per-instance serialised
and rolls back the Instance snapshot if outbox or audit dispatch raises.
See :class:`ConcurrentFireRejected` and :class:`OutboxDispatchError` for
the direct-dispatch failure surfaces.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger(__name__)

from .. import config
from .._uuid7 import uuid7str
from ..dsl import Effect, Transition, WorkflowDef
from .tokens import Token, TokenSet
from ..expr import EvaluationError, evaluate
from ..ports.metrics import FIRE_DURATION_HISTOGRAM
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
	the optional namespace prefix).

	Audit-fix-plan §4.2 C-08 acceptance criterion. ``"context"`` alone or
	``""`` would previously have written the entire instance context as a
	single root replacement; now they raise.
	"""

	def __init__(self, target: str) -> None:
		super().__init__(
			f"invalid set target {target!r}: needs a non-empty dotted path "
			"(optionally prefixed with 'context.')"
		)
		self.target = target


class OutboxDispatchError(RuntimeError):
	"""Outbox dispatch failed during a fire; the Instance has been rolled
	back to its pre-fire snapshot.

	The original transport-layer exception is chained as ``__cause__``.

	If the transition audit row was already recorded before the outbox
	failure, the engine attempts to append a rollback audit row so the
	audit chain reflects the restored state instead of claiming an
	unqualified transition.

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
	tokens: TokenSet = field(default_factory=TokenSet)


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


def _match_transitions_for_token(wd: WorkflowDef, token: "Token", event: str) -> list[Transition]:
	"""Match transitions from the token's current state (E-80)."""
	candidates = [t for t in wd.transitions if t.from_state == token.state and t.event == event]
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
			result = evaluate(g.expr, ctx, strict_ops=True)
		except EvaluationError as exc:
			raise GuardEvaluationError(transition.id, g.expr) from exc
		if not bool(result):
			return False
	return True


def _apply_effect(effect: Effect, instance: Instance, ctx: dict[str, Any]) -> tuple[list[AuditEvent], list[OutboxEnvelope]]:
	audits: list[AuditEvent] = []
	outboxes: list[OutboxEnvelope] = []

	if effect.kind == "create_entity":
		values = {
			k: evaluate(v, ctx, strict_ops=True)
			for k, v in (effect.values or {}).items()
		}
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
		val = evaluate(effect.expr, ctx, strict_ops=True)
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
				subject_id=(
					str(evaluate(effect.target, ctx, strict_ops=True))
					if effect.target
					else "?"
				),
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
	dispatch_ports: bool = True,
	token_id: str | None = None,  # E-80: if set, advance this token instead of primary state
) -> FireResult:
	"""Plan + commit *event* against *instance* per *wd*.

	The engine builds an evaluator-context that puts the workflow's
	``context`` under the ``context`` key so DSL ``var`` expressions like
	``{"var": "context.intake.loss_amount"}`` resolve.

	``jtbd_id`` and ``jtbd_version`` are propagated into every audit event
	and outbox envelope produced during this fire (E-10). Tracing consumers
	use these to group events by originating JTBD spec. Pass ``None`` for
	workflows not originating from a JTBD bundle (backwards-compatible).

	When ``dispatch_ports`` is ``False``, the returned
	:class:`FireResult` still contains the audit events and outbox
	envelopes, but the engine does not call ``config.audit`` or
	``config.outbox``. Durable adapters use this mode to persist state,
	event log, audit rows, and transactional outbox rows in one database
	transaction.

	``token_id`` (E-80): when set, advance the named parallel-region token
	instead of the primary instance state. Requires ``FLOWFORGE_FORKS_ENABLED=1``.
	Raises :class:`~flowforge.engine._fork.TokenAlreadyConsumedError` if the
	token is not found. Raises :class:`~flowforge.engine._fork.RegionStillForkedError`
	on a primary fire when live tokens occupy the current state.
	"""

	# E-32 / C-04: per-instance serialisation. The check-and-add is a
	# single synchronous step, so two coroutines cannot both pass the
	# gate. The gate intentionally precedes the terminal fast path because
	# an in-flight fire mutates instance.state before audit/outbox dispatch;
	# a second caller must not bypass the gate by observing that temporary
	# terminal state.
	if instance.id in _FIRING_INSTANCES:
		from .. import config as _cfg_m
		_c = _cfg_m.current()
		if _c.metrics is not None:
			try:
				_c.metrics.emit("flowforge_engine_fire_rejected_concurrent_total", 1.0, {})
			except Exception as _exc:
				_log.debug("metrics emit failed (fire_rejected_concurrent): %s", _exc)
		raise ConcurrentFireRejected(instance.id)
	_FIRING_INSTANCES.add(instance.id)
	try:
		# Terminal fast-path only applies to primary-state fires. A per-token
		# fire (token_id is not None) must reach _fire_locked so the token is
		# correctly advanced and consumed even when the primary state has already
		# reached a terminal — otherwise the token is stranded in the live set
		# and all_branches_joined() never fires (code-review finding C4).
		if token_id is None and (
			instance.state.startswith("terminal_") or _is_terminal(wd, instance.state)
		):
			return FireResult(instance, None, [], instance.state, terminal=True)

		_t0 = time.monotonic()
		_cfg = config.current()
		_span_attrs: dict[str, Any] = {
			"flowforge.tenant_id": tenant_id,
			"flowforge.event": event,
			"flowforge.state": instance.state,
			"flowforge.principal_user_id": principal.user_id if principal else "",
		}
		if jtbd_id:
			_span_attrs["flowforge.jtbd_id"] = jtbd_id
		try:
			if _cfg.tracing is not None:
				async with _cfg.tracing.start_span("flowforge.fire", attributes=_span_attrs) as _span:
					result = await _fire_locked(
						wd, instance, event,
						payload=payload, principal=principal, tenant_id=tenant_id,
						jtbd_id=jtbd_id, jtbd_version=jtbd_version,
						dispatch_ports=dispatch_ports, token_id=token_id,
					)
					_span.set_attribute("flowforge.state", result.new_state or "")
			else:
				result = await _fire_locked(
					wd, instance, event,
					payload=payload, principal=principal, tenant_id=tenant_id,
					jtbd_id=jtbd_id, jtbd_version=jtbd_version,
					dispatch_ports=dispatch_ports, token_id=token_id,
				)
			return result
		finally:
			_dur = time.monotonic() - _t0
			_m = config.current().metrics
			if _m is not None and hasattr(_m, "record_histogram"):
				try:
					_m.record_histogram(
						FIRE_DURATION_HISTOGRAM, _dur,
						{"event": event, "tenant_id": tenant_id},
					)
				except Exception as _exc:
					_log.debug("metrics record_histogram failed (fire_duration): %s", _exc)
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
	dispatch_ports: bool,
	token_id: str | None = None,
) -> FireResult:
	"""Body of :func:`fire` after the per-instance gate has been claimed.

	Split out so the gate's `try / finally` is tight and the
	rollback-on-failure path is unambiguously distinct from the gate's
	cleanup.
	"""

	# -----------------------------------------------------------------------
	# E-80: Per-token advance path.
	# When token_id is set, advance that parallel-branch token instead of the
	# primary instance state. Both the global feature flag AND the presence of
	# the token in the live set are required.
	# -----------------------------------------------------------------------
	if token_id is not None:
		from ._fork import consume_token, TokenAlreadyConsumedError, _has_token
		from .fork_config import forks_enabled
		if not forks_enabled():
			raise ValueError(
				"token_id requires parallel-fork support to be enabled. "
				"Set FLOWFORGE_FORKS_ENABLED=0 only to disable; "
				"forks are on by default in v0.3.0+."
			)
		if not _has_token(instance.tokens, token_id):
			_cfg = config.current()
			if _cfg.metrics is not None:
				try:
					_cfg.metrics.emit("flowforge_token_unknown_advance_total", 1.0, {})
				except Exception as _exc:
					_log.debug("metrics emit failed (token_unknown_advance): %s", _exc)
			raise TokenAlreadyConsumedError(f"token {token_id!r} not found or already consumed")

		_token = next(t for t in instance.tokens.list() if t.id == token_id)

		candidates_tok = _match_transitions_for_token(wd, _token, event)
		chosen_t: Transition | None = None
		eval_ctx_tok = {
			"context": instance.context,
			"__tenant_id__": tenant_id,
			"__actor__": principal.user_id if principal else None,
			"event": {"name": event, "payload": payload or {}},
		}
		for t in candidates_tok:
			if _guards_pass(t, eval_ctx_tok):
				chosen_t = t
				break

		if chosen_t is None:
			return FireResult(instance, None, [], instance.state, terminal=False)

		pre_snapshot = _snapshot_instance(instance)
		_from_state = _token.state
		_token.state = chosen_t.to_state

		audits: list[AuditEvent] = [
			AuditEvent(
				kind=f"wf.{wd.key}.token_advanced",
				subject_kind=wd.subject_kind,
				subject_id=instance.id,
				tenant_id=tenant_id,
				actor_user_id=principal.user_id if principal else None,
				payload={
					"token_id": token_id,
					"from_state": _from_state,
					"to_state": _token.state,
					"event": event,
				},
			)
		]

		outboxes: list[OutboxEnvelope] = []
		for effect in chosen_t.effects:
			a, o = _apply_effect(effect, instance, eval_ctx_tok)
			audits.extend(a)
			outboxes.extend(o)

		instance.history.append(f"token:{token_id}:({chosen_t.id}:{event})->{chosen_t.to_state}")

		# -----------------------------------------------------------------------
		# E-81: join barrier collapse.
		# If the token just landed on a parallel_join state, attempt to drain
		# the region. When ALL tokens have been consumed the instance's primary
		# state collapses to the join state and then advances synthetically
		# through the join's single outgoing transition.
		# -----------------------------------------------------------------------
		from ._fork import consume_token, all_branches_joined
		_new_token_state_def = next(
			(s for s in wd.states if s.name == _token.state), None
		)
		if _new_token_state_def is not None and _new_token_state_def.kind == "parallel_join":
			# Capture outstanding count BEFORE consuming this token so that
			# the metrics in the else-branch reflect the pre-consume count
			# (code-review finding C8: count_in_region is off-by-one after consume).
			_outstanding_before = instance.tokens.count_in_region(_token.region)

			# Consume this token — removes it from the live set.
			consume_token(instance.tokens, token_id)

			if all_branches_joined(instance.tokens, _token.region):
				# All branches drained — collapse primary state to the join.
				instance.state = _new_token_state_def.name

				# Synthetic advance: pick the highest-priority outgoing
				# transition from the join state.
				_join_outgoing = [
					t for t in wd.transitions if t.from_state == instance.state
				]
				if _join_outgoing:
					_join_outgoing.sort(key=lambda t: -t.priority)
					_join_transition = _join_outgoing[0]
					instance.state = _join_transition.to_state
					instance.history.append(
						f"join_collapsed:({_join_transition.id})->{_join_transition.to_state}"
					)
					# Apply effects declared on the join→post-join transition
					# (code-review finding C3: effects were silently skipped).
					for _jfx in _join_transition.effects:
						_ja, _jo = _apply_effect(_jfx, instance, eval_ctx_tok)
						audits.extend(_ja)
						outboxes.extend(_jo)
					audits.append(
						AuditEvent(
							kind=f"wf.{wd.key}.join_collapsed",
							subject_kind=wd.subject_kind,
							subject_id=instance.id,
							tenant_id=tenant_id,
							actor_user_id=principal.user_id if principal else None,
							payload={
								"join_state": _new_token_state_def.name,
								"final_state": instance.state,
								"region": _token.region,
							},
						)
					)
			else:
				# Tokens still outstanding — emit observability counters using
				# the pre-consume count so the value reflects tokens outstanding
				# *before* this fire (code-review finding C8).
				_cfg2 = config.current()
				if _cfg2.metrics is not None:
					try:
						_cfg2.metrics.emit(
							"flowforge_fork_join_timeout_total",
							float(_outstanding_before),
							{},
						)
					except Exception as _exc:
						_log.debug("metrics emit failed (fork_join_timeout): %s", _exc)
					try:
						_cfg2.metrics.emit(
							"flowforge_fork_orphan_tokens_total",
							float(_outstanding_before),
							{},
						)
					except Exception as _exc:
						_log.debug("metrics emit failed (fork_orphan_tokens): %s", _exc)

		# Take a post-mutation snapshot (after consume_token + join collapse) for
		# the dispatch-failure rollback. Using the pre-mutation pre_snapshot here
		# would restore a consumed token, allowing double-consume on retry
		# (code-review finding C5). With the post-mutation snapshot:
		#   - dispatch failure: token stays consumed, state stays at updated value
		#   - caller retry: _has_token returns False → TokenAlreadyConsumedError
		_post_mutation_snapshot = _snapshot_instance(instance)

		cfg = config.current()
		if dispatch_ports and cfg.audit is not None:
			try:
				for evt in audits:
					await cfg.audit.record(evt)
			except Exception:
				_restore_instance(instance, _post_mutation_snapshot)
				raise
		if dispatch_ports and cfg.outbox is not None:
			for env in outboxes:
				try:
					await cfg.outbox.dispatch(env)
				except Exception as e:
					_restore_instance(instance, _post_mutation_snapshot)
					# Mirror the primary-fire path: record a rollback audit row
					# so the audit chain reflects the restored state
					# (code-review finding C6).
					if cfg.audit is not None:
						await _record_rollback_audit(
							cfg.audit,
							wd=wd,
							instance=instance,
							tenant_id=tenant_id,
							principal=principal,
							transition_id=chosen_t.id,
							from_state=_from_state,
							to_state=chosen_t.to_state,
							event=event,
							envelope_kind=env.kind,
							jtbd_id=None,
							jtbd_version=None,
						)
					raise OutboxDispatchError(instance.id, env.kind) from e

		terminal = _is_terminal(wd, instance.state)
		return FireResult(
			instance=instance,
			matched_transition_id=chosen_t.id,
			planned_effects=list(chosen_t.effects),
			new_state=instance.state,
			terminal=terminal,
			audit_events=audits,
			outbox_envelopes=outboxes,
		)

	# -----------------------------------------------------------------------
	# E-80: primary-state fire blocked while tokens occupy the current state.
	# -----------------------------------------------------------------------
	from ._fork import RegionStillForkedError
	# Block primary fire when ANY tokens are live — not just tokens whose
	# region matches the current primary state. After a join collapse,
	# instance.state is the post-join state, but outstanding branch tokens
	# still carry region=<fork-state-name>; count_in_region(instance.state)
	# would return 0 and silently allow an incorrect primary advance
	# (code-review finding C7).
	if instance.tokens.list():
		raise RegionStillForkedError(
			f"instance {instance.id!r}: primary fire blocked — "
			f"live parallel-region tokens exist; use fire(..., token_id=...) to advance branches"
		)

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

	# E-79: parallel_fork dispatch (layered feature flag).
	# Both the global env-var AND the per-workflow manifest declaration must be
	# true — neither alone is sufficient. This keeps existing workflows safe when
	# the operator flips FLOWFORGE_FORKS_ENABLED=1 in v0.3.0.
	from .fork_config import forks_enabled, workflow_declares_fork
	from ._fork import make_fork_tokens
	_new_state_def = next((s for s in wd.states if s.name == instance.state), None)
	if (
		_new_state_def is not None
		and _new_state_def.kind == "parallel_fork"
		and forks_enabled()
		and workflow_declares_fork(wd.metadata)
	):
		# _ForkBranch protocol requires a `.to` attribute; Transition uses
		# `.to_state`.  Wrap with a lightweight adapter rather than mutating
		# the DSL model.
		class _BranchAdapter:
			__slots__ = ("to",)
			def __init__(self, to_state: str) -> None:
				self.to = to_state

		_outgoing = [t for t in wd.transitions if t.from_state == instance.state]
		_fork_tokens = make_fork_tokens(
			region=instance.state,
			branches=[_BranchAdapter(t.to_state) for t in _outgoing],
		)
		for _tok in _fork_tokens:
			instance.tokens.add(_tok)
		audits.insert(
			0,
			AuditEvent(
				kind=f"wf.{wd.key}.fork_dispatched",
				subject_kind=wd.subject_kind,
				subject_id=instance.id,
				tenant_id=tenant_id,
				actor_user_id=principal.user_id if principal else None,
				payload={
					"fork_state": instance.state,
					"token_ids": [t.id for t in _fork_tokens],
					"branch_count": len(_fork_tokens),
				},
			),
		)

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

	# Direct port dispatch is intentionally retained for tests, demos, and
	# custom hosts. It is not a durable transaction boundary. Critical
	# SQLAlchemy hosts use SqlAlchemySnapshotStore.fire_and_commit(), which
	# calls fire(..., dispatch_ports=False) and writes audit/outbox rows in
	# the same database transaction as the snapshot/event log.
	cfg = config.current()
	if dispatch_ports and cfg.audit is not None:
		try:
			for evt in audits:
				await cfg.audit.record(evt)
		except Exception:
			_restore_instance(instance, pre_snapshot)
			raise

	if dispatch_ports and cfg.outbox is not None:
		for env in outboxes:
			try:
				await cfg.outbox.dispatch(env)
			except Exception as e:
				_restore_instance(instance, pre_snapshot)
				if cfg.audit is not None:
					await _record_rollback_audit(
						cfg.audit,
						wd=wd,
						instance=instance,
						tenant_id=tenant_id,
						principal=principal,
						transition_id=chosen.id,
						from_state=prev_state,
						to_state=chosen.to_state,
						event=event,
						envelope_kind=env.kind,
						jtbd_id=jtbd_id,
						jtbd_version=jtbd_version,
					)
				raise OutboxDispatchError(instance.id, env.kind) from e

	# FEAT-02: When entering a manual_review state, surface a task in the
	# TaskTrackerPort so operator dashboards see pending human work.
	if _new_state_def is not None and _new_state_def.kind == "manual_review":
		_task_cfg = config.current()
		if _task_cfg.tasks is not None:
			try:
				await _task_cfg.tasks.create_task(
					kind="manual_review",
					ref=f"{wd.key}:{instance.id}",
					note=(
						f"State {instance.state!r} via event {event!r}. "
						+ (f"Actor: {principal.user_id!r}." if principal else "Actor: system.")
					),
				)
			except Exception as _exc:
				_log.warning(
					"TaskTrackerPort.create_task() failed for instance %r state %r: %s",
					instance.id, instance.state, _exc,
				)

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
		"tokens": [(t.id, t.region, t.state, dict(t.context)) for t in instance.tokens.list()],
	}


def _restore_instance(instance: Instance, snapshot: dict[str, Any]) -> None:
	"""Restore Instance to *snapshot*. Mutates in place."""

	instance.state = snapshot["state"]
	instance.context = snapshot["context"]
	instance.created_entities = snapshot["created_entities"]
	instance.saga = snapshot["saga"]
	instance.history = snapshot["history"]
	ts = TokenSet()
	for (tid, region, state, ctx) in snapshot.get("tokens", []):
		ts.add(Token(id=tid, region=region, state=state, context=ctx))
	instance.tokens = ts


async def _record_rollback_audit(
	audit_sink: Any,
	*,
	wd: WorkflowDef,
	instance: Instance,
	tenant_id: str,
	principal: Principal | None,
	transition_id: str,
	from_state: str,
	to_state: str,
	event: str,
	envelope_kind: str,
	jtbd_id: str | None,
	jtbd_version: str | None,
) -> None:
	payload: dict[str, Any] = {
		"transition_id": transition_id,
		"from_state": from_state,
		"to_state": to_state,
		"restored_state": instance.state,
		"event": event,
		"failed_envelope_kind": envelope_kind,
	}
	if jtbd_id is not None:
		payload["jtbd_id"] = jtbd_id
	if jtbd_version is not None:
		payload["jtbd_version"] = jtbd_version
	try:
		await audit_sink.record(
			AuditEvent(
				kind=f"wf.{wd.key}.transition_rolled_back",
				subject_kind=wd.subject_kind,
				subject_id=instance.id,
				tenant_id=tenant_id,
				actor_user_id=principal.user_id if principal else None,
				payload=payload,
			)
		)
	except Exception:
		# Preserve the original outbox failure surface. Transactional hosts
		# use dispatch_ports=False and persist rollback-free rows atomically.
		return


def _is_terminal(wd: WorkflowDef, state_name: str) -> bool:
	for s in wd.states:
		if s.name == state_name:
			return s.kind in ("terminal_success", "terminal_fail")
	return False


def make_context(tenant_id: str, principal: Principal, *, elevated: bool = False) -> ExecutionContext:
	"""Convenience builder mirrored by host adapters."""
	return ExecutionContext(tenant_id=tenant_id, principal=principal, elevated=elevated)
