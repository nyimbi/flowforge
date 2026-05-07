"""Saga ledger + minimal compensation worker.

Saga steps are recorded onto :class:`flowforge.engine.fire.Instance.saga`
as effects fire. The durable counterpart lives in
:mod:`flowforge_sqlalchemy.saga_queries.SagaQueries`.

E-40 / audit-fix-plan §4.2 C-09: the :class:`CompensationWorker` here is
the minimal worker that replays pending saga rows after a crash. It is
intentionally *not* a full reverse-execution model (out of scope per
critic CR-8); it is a register-handler-per-kind dispatcher with
exactly-once semantics derived from the row status:

  * ``pending`` rows are dispatched in idx-DESC order (LIFO).
  * Handler success → ``compensated``.
  * Handler raise → ``failed``; subsequent rows still get a chance.
  * No registered handler → row stays ``pending`` and counts as
    *skipped* in the report so the operator can intervene later.

Restart-replay is naturally exactly-once: a second
:meth:`CompensationWorker.replay_pending` for the same instance reads
zero ``pending`` rows because the first run wrote ``compensated`` /
``failed`` to the DB.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

CompensationHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class SagaStep:
	kind: str
	args: dict[str, Any] = field(default_factory=dict)
	status: str = "pending"  # pending | done | compensated | failed


class SagaLedger:
	"""In-memory ledger keyed by instance id."""

	def __init__(self) -> None:
		self._rows: dict[str, list[SagaStep]] = {}

	def append(self, instance_id: str, step: SagaStep) -> None:
		self._rows.setdefault(instance_id, []).append(step)

	def list(self, instance_id: str) -> list[SagaStep]:
		return list(self._rows.get(instance_id, ()))

	def mark(self, instance_id: str, idx: int, status: str) -> None:
		rows = self._rows.get(instance_id) or []
		if 0 <= idx < len(rows):
			rows[idx] = SagaStep(kind=rows[idx].kind, args=rows[idx].args, status=status)


# ---------------------------------------------------------------------------
# E-40 — durable saga ledger contract + compensation worker.
# ---------------------------------------------------------------------------


@runtime_checkable
class SagaQueriesProtocol(Protocol):
	"""The subset of ``flowforge_sqlalchemy.saga_queries.SagaQueries`` that
	:class:`CompensationWorker` calls. Hosts may swap in alternative
	storage backends (e.g. an in-memory ledger for tests, a Mongo adapter
	for non-PG hosts) by implementing this protocol — that is the
	SA-02 acceptance contract."""

	async def list_pending_for_compensation(self, instance_id: str) -> list[Any]:
		"""Return pending rows in LIFO order (idx-DESC)."""
		...

	async def mark(self, instance_id: str, idx: int, status: str) -> bool:
		"""Update a row's status. Returns True iff the row was found."""
		...


@dataclass
class CompensationReport:
	"""Outcome counts from one :meth:`CompensationWorker.replay_pending`.

	``compensated + failed + skipped == len(pending_rows_at_start)``.
	"""

	compensated: int = 0
	failed: int = 0
	skipped: int = 0

	@property
	def total(self) -> int:
		return self.compensated + self.failed + self.skipped


class CompensationWorker:
	"""Per-kind compensation handler dispatcher.

	Usage (typical host wire-up)::

	    worker = CompensationWorker()
	    worker.register("release_lock", release_lock_handler)
	    worker.register("refund", refund_handler)
	    queries = SagaQueries(session_factory, tenant_id="acme")
	    report = await worker.replay_pending(instance_id, queries)
	    log.info(
	        "saga replay complete",
	        compensated=report.compensated,
	        failed=report.failed,
	        skipped=report.skipped,
	    )
	"""

	def __init__(self) -> None:
		self._handlers: dict[str, CompensationHandler] = {}

	def register(self, kind: str, handler: CompensationHandler) -> None:
		"""Register *handler* for compensation rows whose ``kind == kind``.

		Re-registering the same kind overwrites the previous handler so
		that hot-swap deployments can update behaviour without restart.
		"""

		assert kind, "kind is required"
		assert handler is not None, "handler is required"
		self._handlers[kind] = handler

	def has_handler(self, kind: str) -> bool:
		return kind in self._handlers

	async def replay_pending(
		self,
		instance_id: str,
		queries: SagaQueriesProtocol,
	) -> CompensationReport:
		"""Replay every pending compensation row for *instance_id*.

		Iteration order is LIFO (idx-DESC) so the most-recently appended
		step compensates first — matching the saga pattern.

		Exactly-once: rows already marked ``compensated`` or ``failed``
		are not in the result of ``list_pending_for_compensation``, so a
		second call after a restart visits zero rows.
		"""

		assert instance_id, "instance_id is required"

		pending = await queries.list_pending_for_compensation(instance_id)
		report = CompensationReport()

		for row in pending:
			handler = self._handlers.get(row.kind)
			if handler is None:
				# No handler — leave row pending so a future deploy that
				# registers the handler can pick it up.
				report.skipped += 1
				continue
			try:
				await handler(dict(row.args or {}))
			except Exception:  # noqa: BLE001 — per-row failure is logged via DB status; raises in tests can be inspected via report.failed
				await queries.mark(instance_id, row.idx, "failed")
				report.failed += 1
				continue
			await queries.mark(instance_id, row.idx, "compensated")
			report.compensated += 1

		return report
