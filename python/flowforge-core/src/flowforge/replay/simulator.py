"""Deterministic simulator.

Walks a workflow definition with a sequence of (event, payload) tuples
and returns a result. Used by the JTBD generator's tests, the
``flowforge simulate`` CLI, and host parity suites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

from ..dsl import WorkflowDef
from ..engine.fire import FireResult, fire, new_instance
from ..ports.types import AuditEvent, OutboxEnvelope, Principal

if TYPE_CHECKING:
	from .fault import FaultSpec


@dataclass
class SimulationResult:
	terminal_state: str
	created_entities: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
	history: list[str] = field(default_factory=list)
	audit_events: list[AuditEvent] = field(default_factory=list)
	outbox_envelopes: list[OutboxEnvelope] = field(default_factory=list)
	fire_results: list[FireResult] = field(default_factory=list)


async def simulate(
	wd: WorkflowDef,
	*,
	initial_context: dict[str, Any] | None = None,
	events: Iterable[tuple[str, dict[str, Any]]] | None = None,
	tenant_id: str = "sim-tenant",
	principal: Principal | None = None,
	faults: "list[FaultSpec] | None" = None,
) -> SimulationResult:
	"""Run *events* against a fresh instance of *wd*.

	*faults* is an optional list of :class:`~flowforge.replay.fault.FaultSpec`
	objects. When provided a :class:`~flowforge.replay.fault.FaultInjector` is
	constructed and used in place of the bare :func:`~flowforge.engine.fire.fire`
	call so fault injection is applied before each guard evaluation.
	"""

	if faults:
		from .fault import FaultInjector
		injector = FaultInjector(list(faults))
		fault_result = await injector.simulate(
			wd,
			initial_context=initial_context,
			events=events,
			tenant_id=tenant_id,
			principal=principal,
		)
		# Re-wrap as SimulationResult for API compatibility.
		result = SimulationResult(
			terminal_state=fault_result.terminal_state,
			created_entities=fault_result.created_entities,
			history=fault_result.history,
			audit_events=fault_result.audit_events,
			outbox_envelopes=fault_result.outbox_envelopes,
			fire_results=fault_result.fire_results,
		)
		return result

	instance = new_instance(wd, initial_context=initial_context)
	result = SimulationResult(terminal_state=instance.state)

	principal = principal or Principal(user_id="sim-user", roles=("simulator",), is_system=True)
	for event_name, payload in (events or ()):
		fr = await fire(
			wd,
			instance,
			event_name,
			payload=payload,
			principal=principal,
			tenant_id=tenant_id,
		)
		result.fire_results.append(fr)
		result.audit_events.extend(fr.audit_events)
		result.outbox_envelopes.extend(fr.outbox_envelopes)
		if fr.terminal:
			break

	result.terminal_state = instance.state
	result.created_entities = list(instance.created_entities)
	result.history = list(instance.history)
	return result
