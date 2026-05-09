"""Saga compensation handlers for File an insurance claim (FNOL).

Stub registrations for the compensation kinds the JTBD synthesiser
emits on ``compensate`` transitions. Production hosts replace each
handler with real reversal logic (e.g. soft-delete the entity, send a
cancellation email, retract an external reservation).

The synthesiser pairs forward effects with compensation kinds:

* ``create_entity`` → ``compensate_delete``
* ``notify``        → ``notify_cancellation``

Compensations replay in **LIFO** order via
:meth:`flowforge.engine.saga.CompensationWorker.replay_pending`, so the
most-recently appended saga step compensates first.
"""

from __future__ import annotations

from typing import Any

from flowforge.engine.saga import CompensationWorker


async def _compensate_delete(args: dict[str, Any]) -> None:
	"""Reverse a ``create_entity`` saga step.

	*args* carries the original effect payload; production handlers read
	the entity id and soft- or hard-delete the row. Stub returns ``None``
	so :class:`CompensationWorker` records a successful compensation.
	"""

	assert isinstance(args, dict)
	return None


async def _notify_cancellation(args: dict[str, Any]) -> None:
	"""Reverse a forward ``notify`` saga step.

	Production handlers dispatch a cancellation message through the
	configured :class:`NotificationPort`; stub returns ``None``.
	"""

	assert isinstance(args, dict)
	return None


COMPENSATION_HANDLERS: dict[str, Any] = {
	"compensate_delete": _compensate_delete,
	"notify_cancellation": _notify_cancellation,
}


def register_compensations(worker: CompensationWorker) -> None:
	"""Register the claim_intake compensation handlers on *worker*.

	Idempotent — re-registering the same kind overwrites the prior
	handler so hot-swap deployments can update behaviour without
	restart.
	"""

	assert worker is not None, "worker is required"
	for kind, handler in COMPENSATION_HANDLERS.items():
		worker.register(kind, handler)
