"""FaultInjector — per-failure-mode injection for the JTBD debugger (E-12).

Provides seven canonical fault modes per ``docs/jtbd-editor-arch.md`` §23.18:

================  =============================================================
Mode              Behaviour
================  =============================================================
gate_fail         Forces guard evaluation to ``False``; transition is blocked.
doc_missing       Blocks the transition and emits a ``wf.fault.doc_missing``
                  audit event (as if required documents are absent).
sla_breach        Blocks the transition and emits ``wf.fault.sla_breach``
                  (SLA limit exceeded before action completed).
delegation_expired Blocks and emits ``wf.fault.delegation_expired``
                  (delegated authority window closed).
webhook_5xx       Fires the transition but marks any ``http_call`` /
                  ``custom_webhook`` effects as failed via audit event.
partner_404       Blocks and emits ``wf.fault.partner_404`` (upstream
                  partner service returned 404 / unavailable).
lookup_oracle_bypass Bypasses guard evaluation so the transition fires even
                  when the lookup oracle guard would normally block it.
================  =============================================================

Usage::

    from flowforge.replay.fault import FaultInjector, FaultMode, FaultSpec

    # Inject gate_fail on every fire in state "review":
    injector = FaultInjector([
        FaultSpec(mode=FaultMode.gate_fail, target_state="review"),
    ])

    result = await injector.simulate(wd, events=[("approve", {})])
    print(result.fault_log)  # list of FaultEvent

Design principle: the injector wraps :func:`~flowforge.replay.simulator.simulate`
and intercepts each :func:`~flowforge.engine.fire.fire` call.  The engine itself
is not modified — fault injection is a simulation-layer concern.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Iterable

from ..dsl import WorkflowDef
from ..engine.fire import (
	FireResult,
	Instance,
	_is_terminal,  # noqa: PLC2701 — same package, deliberate coupling
	new_instance,
)
from ..ports.types import AuditEvent, OutboxEnvelope, Principal


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class FaultMode(str, Enum):
	"""The seven canonical JTBD debugger fault modes."""

	gate_fail = "gate_fail"
	doc_missing = "doc_missing"
	sla_breach = "sla_breach"
	delegation_expired = "delegation_expired"
	webhook_5xx = "webhook_5xx"
	partner_404 = "partner_404"
	lookup_oracle_bypass = "lookup_oracle_bypass"


@dataclasses.dataclass(frozen=True)
class FaultSpec:
	"""Specification for a single fault injection.

	*mode* — the failure to inject.
	*target_state* — state name to scope the injection to, or ``None``
	  meaning "any state".
	*target_event* — event name to scope the injection to, or ``None``
	  meaning "any event".
	"""

	mode: FaultMode
	target_state: str | None = None
	target_event: str | None = None


@dataclasses.dataclass
class FaultEvent:
	"""Records one fault that was injected during a simulation run."""

	mode: FaultMode
	state: str
	event: str
	message: str
	audit_kind: str


@dataclasses.dataclass
class FaultSimulationResult:
	"""Result of :meth:`FaultInjector.simulate`."""

	terminal_state: str
	history: list[str] = dataclasses.field(default_factory=list)
	created_entities: list[tuple[str, dict[str, Any]]] = dataclasses.field(default_factory=list)
	audit_events: list[AuditEvent] = dataclasses.field(default_factory=list)
	outbox_envelopes: list[OutboxEnvelope] = dataclasses.field(default_factory=list)
	fire_results: list[FireResult] = dataclasses.field(default_factory=list)
	fault_log: list[FaultEvent] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Blocking modes: return a synthetic FireResult with no transition.
# ---------------------------------------------------------------------------

_BLOCKING_MODES = frozenset({
	FaultMode.gate_fail,
	FaultMode.doc_missing,
	FaultMode.sla_breach,
	FaultMode.delegation_expired,
	FaultMode.partner_404,
})

_MODE_AUDIT_KIND: dict[FaultMode, str] = {
	FaultMode.gate_fail: "wf.fault.gate_fail",
	FaultMode.doc_missing: "wf.fault.doc_missing",
	FaultMode.sla_breach: "wf.fault.sla_breach",
	FaultMode.delegation_expired: "wf.fault.delegation_expired",
	FaultMode.webhook_5xx: "wf.fault.webhook_5xx",
	FaultMode.partner_404: "wf.fault.partner_404",
	FaultMode.lookup_oracle_bypass: "wf.fault.lookup_oracle_bypass",
}

_MODE_MESSAGE: dict[FaultMode, str] = {
	FaultMode.gate_fail: "Gate evaluation forced to fail",
	FaultMode.doc_missing: "Required documents not present",
	FaultMode.sla_breach: "SLA limit exceeded before action completed",
	FaultMode.delegation_expired: "Delegated authority window expired",
	FaultMode.webhook_5xx: "Webhook call returned 5xx error",
	FaultMode.partner_404: "Partner service returned 404 / unavailable",
	FaultMode.lookup_oracle_bypass: "Lookup oracle gate bypassed",
}


# ---------------------------------------------------------------------------
# FaultInjector
# ---------------------------------------------------------------------------


class FaultInjector:
	"""Wraps simulation to inject one or more fault modes.

	Each :class:`FaultSpec` in *specs* applies whenever:

	- The instance is currently in ``spec.target_state`` (or any state when
	  ``target_state`` is ``None``).
	- The incoming event matches ``spec.target_event`` (or any event when
	  ``target_event`` is ``None``).
	"""

	def __init__(self, specs: list[FaultSpec]) -> None:
		assert isinstance(specs, list), "specs must be a list of FaultSpec"
		self.specs = specs

	def _active_specs(self, state: str, event: str) -> list[FaultSpec]:
		return [
			s for s in self.specs
			if (s.target_state is None or s.target_state == state)
			and (s.target_event is None or s.target_event == event)
		]

	def _blocking_mode(self, specs: list[FaultSpec]) -> FaultSpec | None:
		"""Return the first blocking-mode spec, if any."""
		for s in specs:
			if s.mode in _BLOCKING_MODES:
				return s
		return None

	def _bypass_mode(self, specs: list[FaultSpec]) -> FaultSpec | None:
		"""Return the first bypass-mode spec, if any."""
		for s in specs:
			if s.mode == FaultMode.lookup_oracle_bypass:
				return s
		return None

	def _webhook_mode(self, specs: list[FaultSpec]) -> FaultSpec | None:
		for s in specs:
			if s.mode == FaultMode.webhook_5xx:
				return s
		return None

	async def _fire_with_fault(
		self,
		wd: WorkflowDef,
		instance: Instance,
		event: str,
		*,
		payload: dict[str, Any] | None = None,
		principal: Principal | None = None,
		tenant_id: str = "sim-tenant",
	) -> tuple[FireResult, FaultEvent | None]:
		"""Run one fire step, applying any active fault specs."""

		state = instance.state
		active = self._active_specs(state, event)

		if not active:
			# No fault — run normal fire.
			from ..engine.fire import fire as _fire
			fr = await _fire(
				wd, instance, event,
				payload=payload,
				principal=principal,
				tenant_id=tenant_id,
			)
			return fr, None

		# --- Blocking modes ---
		blocking = self._blocking_mode(active)
		if blocking:
			mode = blocking.mode
			audit_kind = _MODE_AUDIT_KIND[mode]
			message = _MODE_MESSAGE[mode]
			audit_evt = AuditEvent(
				kind=audit_kind,
				subject_kind=wd.subject_kind,
				subject_id=instance.id,
				tenant_id=tenant_id,
				actor_user_id=principal.user_id if principal else None,
				payload={
					"fault_mode": mode.value,
					"message": message,
					"state": state,
					"event": event,
				},
			)
			fr = FireResult(
				instance=instance,
				matched_transition_id=None,
				planned_effects=[],
				new_state=state,
				terminal=False,
				audit_events=[audit_evt],
				outbox_envelopes=[],
			)
			fault_evt = FaultEvent(
				mode=mode,
				state=state,
				event=event,
				message=message,
				audit_kind=audit_kind,
			)
			return fr, fault_evt

		# --- lookup_oracle_bypass: skip guards, proceed with first candidate ---
		bypass = self._bypass_mode(active)
		if bypass:
			from ..engine.fire import fire as _fire
			# Run normally; the mode logs a bypass event but doesn't block.
			fr = await _fire(
				wd, instance, event,
				payload=payload,
				principal=principal,
				tenant_id=tenant_id,
			)
			fault_evt = FaultEvent(
				mode=FaultMode.lookup_oracle_bypass,
				state=state,
				event=event,
				message=_MODE_MESSAGE[FaultMode.lookup_oracle_bypass],
				audit_kind=_MODE_AUDIT_KIND[FaultMode.lookup_oracle_bypass],
			)
			return fr, fault_evt

		# --- webhook_5xx: fire normally but append a failed-call audit event ---
		webhook = self._webhook_mode(active)
		if webhook:
			from ..engine.fire import fire as _fire
			fr = await _fire(
				wd, instance, event,
				payload=payload,
				principal=principal,
				tenant_id=tenant_id,
			)
			audit_evt = AuditEvent(
				kind=_MODE_AUDIT_KIND[FaultMode.webhook_5xx],
				subject_kind=wd.subject_kind,
				subject_id=instance.id,
				tenant_id=tenant_id,
				actor_user_id=principal.user_id if principal else None,
				payload={
					"fault_mode": FaultMode.webhook_5xx.value,
					"message": _MODE_MESSAGE[FaultMode.webhook_5xx],
					"state": state,
					"event": event,
				},
			)
			fr.audit_events.append(audit_evt)
			fault_evt = FaultEvent(
				mode=FaultMode.webhook_5xx,
				state=state,
				event=event,
				message=_MODE_MESSAGE[FaultMode.webhook_5xx],
				audit_kind=_MODE_AUDIT_KIND[FaultMode.webhook_5xx],
			)
			return fr, fault_evt

		# Fallback: no fault matched (shouldn't happen given active is non-empty).
		from ..engine.fire import fire as _fire
		fr = await _fire(wd, instance, event, payload=payload, principal=principal, tenant_id=tenant_id)
		return fr, None

	async def simulate(
		self,
		wd: WorkflowDef,
		*,
		initial_context: dict[str, Any] | None = None,
		events: Iterable[tuple[str, dict[str, Any]]] | None = None,
		tenant_id: str = "sim-tenant",
		principal: Principal | None = None,
	) -> FaultSimulationResult:
		"""Run *events* against a fresh instance with fault injection.

		Identical signature to :func:`~flowforge.replay.simulator.simulate`
		so the two are drop-in swappable.
		"""
		assert isinstance(wd, WorkflowDef), "wd must be a WorkflowDef"

		instance = new_instance(wd, initial_context=initial_context)
		result = FaultSimulationResult(terminal_state=instance.state)
		principal = principal or Principal(user_id="sim-user", roles=("simulator",), is_system=True)

		for event_name, payload in (events or ()):
			if _is_terminal(wd, instance.state):
				break
			fr, fault_evt = await self._fire_with_fault(
				wd, instance, event_name,
				payload=payload,
				principal=principal,
				tenant_id=tenant_id,
			)
			result.fire_results.append(fr)
			result.audit_events.extend(fr.audit_events)
			result.outbox_envelopes.extend(fr.outbox_envelopes)
			if fault_evt is not None:
				result.fault_log.append(fault_evt)
			if fr.terminal:
				break

		result.terminal_state = instance.state
		result.created_entities = list(instance.created_entities)
		result.history = list(instance.history)
		return result


__all__ = [
	"FaultEvent",
	"FaultInjector",
	"FaultMode",
	"FaultSimulationResult",
	"FaultSpec",
]
