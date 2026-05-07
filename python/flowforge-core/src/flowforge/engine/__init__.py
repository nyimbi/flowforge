"""Engine: two-phase fire + saga + signals + sub-workflows + timers + snapshots.

Public entry points:

* :func:`fire` — accepts an event, plans transitions, commits effects.
* :func:`new_instance` — creates a fresh workflow instance.
* :class:`Instance` — in-memory representation of one running workflow.
"""

from .fire import Instance, FireResult, fire, new_instance
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

__all__ = [
	"CompensationHandler",
	"CompensationReport",
	"CompensationWorker",
	"FireResult",
	"InMemorySnapshotStore",
	"Instance",
	"SagaLedger",
	"SagaQueriesProtocol",
	"SagaStep",
	"SignalCorrelator",
	"fire",
	"new_instance",
]
