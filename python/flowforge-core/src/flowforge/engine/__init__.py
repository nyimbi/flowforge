"""Engine: two-phase fire + saga + signals + sub-workflows + timers + snapshots.

Public entry points:

* :func:`fire` — accepts an event, plans transitions, commits effects.
* :func:`new_instance` — creates a fresh workflow instance.
* :func:`receive_signal` — advance an instance blocked in a ``signal_wait`` state.
* :class:`Instance` — in-memory representation of one running workflow.
* :func:`check_sla_breaches` — fire ``sla_breach`` events on overdue instances.
* :func:`is_sla_breached` — check a single candidate without firing.
* :func:`migrate_instance` — migrate an instance between definition versions.
"""

from typing import Any

from .fire import Instance, FireResult, fire, new_instance
from ..dsl import WorkflowDef
from .saga import (
	CompensationHandler,
	CompensationReport,
	CompensationWorker,
	SagaLedger,
	SagaQueriesProtocol,
	SagaStep,
)
from .signals import SignalCorrelator
from .snapshots import InMemorySnapshotStore
from .sla_scheduler import SlaCandidate, SlaBreachResult, check_sla_breaches, is_sla_breached
from .migration import MigrationReport, StateMigrationError, migrate_instance, validate_migration_mapping


async def receive_signal(
	wd: WorkflowDef,
	instance: Instance,
	signal_name: str,
	payload: dict[str, Any] | None = None,
	*,
	principal: Any = None,
	tenant_id: str = "default",
	jtbd_id: str | None = None,
	jtbd_version: str | None = None,
	dispatch_ports: bool = True,
) -> FireResult:
	"""Advance an instance blocked in a ``signal_wait`` state.

	Validates that the instance is currently in a ``signal_wait`` state,
	then delegates to :func:`fire` using *signal_name* as the event.
	Callers typically store the instance + workflow def in their own
	persistence layer and look them up by correlation key before calling
	this function.

	Raises:
		ValueError: if the instance is not in a ``signal_wait`` state.
	"""
	state_def = next((s for s in wd.states if s.name == instance.state), None)
	if state_def is None or state_def.kind != "signal_wait":
		raise ValueError(
			f"receive_signal: instance {instance.id!r} is in state {instance.state!r} "
			f"(kind={state_def.kind if state_def else 'unknown'}), expected signal_wait"
		)
	return await fire(
		wd, instance, signal_name,
		payload=payload,
		principal=principal,
		tenant_id=tenant_id,
		jtbd_id=jtbd_id,
		jtbd_version=jtbd_version,
		dispatch_ports=dispatch_ports,
	)


__all__ = [
	"CompensationHandler",
	"CompensationReport",
	"CompensationWorker",
	"FireResult",
	"InMemorySnapshotStore",
	"Instance",
	"MigrationReport",
	"SagaLedger",
	"SagaQueriesProtocol",
	"SagaStep",
	"SignalCorrelator",
	"SlaBreachResult",
	"SlaCandidate",
	"StateMigrationError",
	"check_sla_breaches",
	"fire",
	"is_sla_breached",
	"migrate_instance",
	"new_instance",
	"receive_signal",
	"validate_migration_mapping",
]
