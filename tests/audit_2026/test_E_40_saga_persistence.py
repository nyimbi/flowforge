"""E-40 — saga ledger persistence + minimal compensation worker.

Audit findings (audit-fix-plan §4.2 C-09, SA-02; §7 E-40):
- C-09 (P1): saga persisted across restart; compensation worker replays
  pending entries from the durable ledger; integration asserts each
  compensation runs exactly once.
- SA-02 (P2): SagaQueries helpers cover the compensation worker's
  contract — append, list_for_instance, list_pending_for_compensation,
  mark, all roundtrip cleanly.

The full reverse-execution saga is out of scope per critic CR-8; the
deliverable is the schema (already in `flowforge_sqlalchemy.models`)
plus a minimal worker that:
  * resumes after crash by reading pending rows in idx-DESC order
  * invokes a per-kind handler exactly once
  * marks each row `compensated` (success) or `failed` (handler raised)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


def _drive(coro: Any) -> Any:
	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		return loop.run_until_complete(coro)
	finally:
		loop.close()


async def _new_engine() -> tuple[Any, Any]:
	"""Build an in-memory SQLite engine with the saga table created."""

	from flowforge_sqlalchemy.base import Base
	from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

	# Force a fresh in-memory DB per call so tests cannot share state.
	# We need a shared cache so multiple sessions see the same DB.
	url = "sqlite+aiosqlite:///:memory:"
	engine = create_async_engine(url, future=True)
	async with engine.begin() as conn:
		# create_all only creates tables that don't yet exist.
		# Disable FK checks for the saga FK to workflow_instances since
		# we're testing the saga table in isolation.
		await conn.run_sync(Base.metadata.create_all)
	sf = async_sessionmaker(engine, expire_on_commit=False)
	return engine, sf


# ---------------------------------------------------------------------------
# SA-02 — SagaQueries roundtrip
# ---------------------------------------------------------------------------


def test_SA_02_saga_queries_append_list_mark_roundtrip() -> None:
	"""append → list_for_instance → mark → list_pending_for_compensation
	all roundtrip; idx is auto-monotonic; LIFO pending iteration."""

	from flowforge_sqlalchemy.saga_queries import SagaQueries

	async def _go() -> None:
		engine, sf = await _new_engine()
		try:
			q = SagaQueries(sf, tenant_id="t")

			row1 = await q.append("inst-1", kind="release_lock", args={"k": "v"})
			row2 = await q.append("inst-1", kind="refund", args={"amount": 50})
			row3 = await q.append("inst-1", kind="notify_revoke", args={})
			assert row1 and row2 and row3 and row1 != row2 != row3

			rows = await q.list_for_instance("inst-1")
			assert [r.kind for r in rows] == ["release_lock", "refund", "notify_revoke"]
			assert [r.idx for r in rows] == [0, 1, 2]
			assert all(r.status == "pending" for r in rows)

			# LIFO order for compensation.
			pending = await q.list_pending_for_compensation("inst-1")
			assert [r.kind for r in pending] == ["notify_revoke", "refund", "release_lock"]

			# Mark idx=1 done.
			ok = await q.mark("inst-1", 1, "done")
			assert ok is True
			pending = await q.list_pending_for_compensation("inst-1")
			assert [r.kind for r in pending] == ["notify_revoke", "release_lock"]

			# Mark unknown idx is a no-op miss, not a raise.
			ok = await q.mark("inst-1", 999, "done")
			assert ok is False
		finally:
			await engine.dispose()

	_drive(_go())


def test_SA_02_saga_queries_invalid_status_rejected() -> None:
	"""mark() rejects an unknown status string."""

	from flowforge_sqlalchemy.saga_queries import SagaQueries

	async def _go() -> None:
		engine, sf = await _new_engine()
		try:
			q = SagaQueries(sf, tenant_id="t")
			await q.append("inst", kind="x")
			with pytest.raises(AssertionError):
				await q.mark("inst", 0, "made-up")
		finally:
			await engine.dispose()

	_drive(_go())


# ---------------------------------------------------------------------------
# C-09 — CompensationWorker replays exactly once
# ---------------------------------------------------------------------------


def test_C_09_compensation_worker_runs_handler_per_pending_row() -> None:
	"""Worker iterates pending rows in idx-DESC order, calls the handler
	per kind once, marks each row `compensated`."""

	from flowforge.engine.saga import CompensationWorker
	from flowforge_sqlalchemy.saga_queries import SagaQueries

	calls: list[tuple[str, dict[str, Any]]] = []

	async def release_lock(args: dict[str, Any]) -> None:
		calls.append(("release_lock", args))

	async def refund(args: dict[str, Any]) -> None:
		calls.append(("refund", args))

	async def _go() -> None:
		engine, sf = await _new_engine()
		try:
			queries = SagaQueries(sf, tenant_id="t")
			await queries.append("inst", kind="release_lock", args={"k": "x"})
			await queries.append("inst", kind="refund", args={"amount": 50})

			worker = CompensationWorker()
			worker.register("release_lock", release_lock)
			worker.register("refund", refund)

			report = await worker.replay_pending("inst", queries)
			assert report.compensated == 2
			assert report.failed == 0
			# LIFO: refund runs before release_lock.
			assert [c[0] for c in calls] == ["refund", "release_lock"]
			# All pending rows are now `compensated`.
			rows = await queries.list_for_instance("inst")
			assert [r.status for r in rows] == ["compensated", "compensated"]
		finally:
			await engine.dispose()

	_drive(_go())


def test_C_09_compensation_runs_exactly_once_across_restart() -> None:
	"""Saga durability: rows persist across worker restart; replay does
	not double-invoke handlers because `compensated` rows are filtered out
	on the second call."""

	from flowforge.engine.saga import CompensationWorker
	from flowforge_sqlalchemy.saga_queries import SagaQueries

	calls: list[str] = []

	async def hndlr(args: dict[str, Any]) -> None:
		calls.append("hit")

	async def _go() -> None:
		engine, sf = await _new_engine()
		try:
			queries = SagaQueries(sf, tenant_id="t")
			await queries.append("inst", kind="undo")
			await queries.append("inst", kind="undo")

			# First run.
			worker_a = CompensationWorker()
			worker_a.register("undo", hndlr)
			report_a = await worker_a.replay_pending("inst", queries)
			assert report_a.compensated == 2

			# Simulate restart: brand new worker instance, same DB.
			worker_b = CompensationWorker()
			worker_b.register("undo", hndlr)
			report_b = await worker_b.replay_pending("inst", queries)
			assert report_b.compensated == 0
			assert report_b.failed == 0

			# Handler ran exactly twice (once per row), not four times.
			assert len(calls) == 2
		finally:
			await engine.dispose()

	_drive(_go())


def test_C_09_compensation_failure_marks_row_failed_and_continues() -> None:
	"""A handler raise marks the row `failed`; subsequent rows still get
	their handlers invoked (failure is per-row, not abort-the-batch)."""

	from flowforge.engine.saga import CompensationWorker
	from flowforge_sqlalchemy.saga_queries import SagaQueries

	calls: list[str] = []

	async def good(args: dict[str, Any]) -> None:
		calls.append("good")

	async def bad(args: dict[str, Any]) -> None:
		calls.append("bad")
		raise RuntimeError("simulated handler failure")

	async def _go() -> None:
		engine, sf = await _new_engine()
		try:
			queries = SagaQueries(sf, tenant_id="t")
			# idx 0: good; idx 1: bad. LIFO so bad runs first.
			await queries.append("inst", kind="good")
			await queries.append("inst", kind="bad")

			worker = CompensationWorker()
			worker.register("good", good)
			worker.register("bad", bad)

			report = await worker.replay_pending("inst", queries)
			assert report.compensated == 1
			assert report.failed == 1
			# Both handlers were invoked even though bad raised.
			assert calls == ["bad", "good"]
			rows = await queries.list_for_instance("inst")
			# idx 0 (good) compensated; idx 1 (bad) failed.
			assert rows[0].status == "compensated"
			assert rows[1].status == "failed"
		finally:
			await engine.dispose()

	_drive(_go())


def test_C_09_compensation_skips_unregistered_kind() -> None:
	"""A row whose `kind` has no registered handler is left as pending
	with a count in the report (so the operator can intervene)."""

	from flowforge.engine.saga import CompensationWorker
	from flowforge_sqlalchemy.saga_queries import SagaQueries

	async def _go() -> None:
		engine, sf = await _new_engine()
		try:
			queries = SagaQueries(sf, tenant_id="t")
			await queries.append("inst", kind="known")
			await queries.append("inst", kind="unknown_kind")

			async def known_h(args: dict[str, Any]) -> None:
				pass

			worker = CompensationWorker()
			worker.register("known", known_h)
			report = await worker.replay_pending("inst", queries)

			assert report.compensated == 1
			assert report.failed == 0
			assert report.skipped == 1
			# unknown_kind row is still pending so a future deploy that
			# registers the handler can pick it up.
			rows = await queries.list_for_instance("inst")
			# LIFO: idx 1 (unknown) attempted first, skipped, stays pending.
			assert rows[1].status == "pending"
			assert rows[0].status == "compensated"
		finally:
			await engine.dispose()

	_drive(_go())
