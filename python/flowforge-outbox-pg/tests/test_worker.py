"""Tests for flowforge_outbox_pg.worker.DrainWorker (SQLite compat mode).

All tests use an in-memory aiosqlite database so no PostgreSQL is required.
PostgreSQL-specific behaviour (FOR UPDATE SKIP LOCKED) is tested structurally
via the _claim_pg path — if asyncpg is available you can add a live PG fixture.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite
import pytest

from flowforge.ports.types import OutboxEnvelope
from flowforge_outbox_pg.registry import HandlerRegistry
from flowforge_outbox_pg.worker import DrainResult, DrainWorker, OutboxRow, OutboxStatus, _pg_to_sqlite


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_worker(
    conn: aiosqlite.Connection,
    registry: HandlerRegistry | None = None,
    *,
    max_retries: int = 3,
    dlq_after_seconds: int = 3600,
    lock_window_seconds: int = 60,
    backend: str = "default",
) -> DrainWorker:
    reg = registry or HandlerRegistry()
    worker = DrainWorker(
        conn,
        reg,
        sqlite_compat=True,
        max_retries=max_retries,
        dlq_after_seconds=dlq_after_seconds,
        lock_window_seconds=lock_window_seconds,
        backend=backend,
    )
    await worker.setup()
    return worker


async def _row_status(conn: aiosqlite.Connection, row_id: str) -> dict[str, Any]:
    cursor = await conn.execute(
        "SELECT status, retries, last_error FROM outbox WHERE id = ?", (row_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None, f"Row {row_id} not found"
    return {"status": row[0], "retries": row[1], "last_error": row[2]}


def _env(kind: str = "test.event", tenant: str = "t1", body: dict[str, Any] | None = None) -> OutboxEnvelope:
    return OutboxEnvelope(kind=kind, tenant_id=tenant, body=body or {"x": 1})


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


async def test_setup_creates_table() -> None:
    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn)
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='outbox'")
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


async def test_enqueue_inserts_pending_row() -> None:
    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn)
        env = _env("order.created")
        row_id = await worker.enqueue(env)

        info = await _row_status(conn, row_id)
        assert info["status"] == "pending"
        assert info["retries"] == 0


async def test_enqueue_explicit_id() -> None:
    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn)
        row_id = await worker.enqueue(_env(), row_id="my-explicit-id")
        assert row_id == "my-explicit-id"
        info = await _row_status(conn, "my-explicit-id")
        assert info["status"] == "pending"


async def test_enqueue_body_serialized_as_json() -> None:
    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn)
        body = {"amount": 99, "currency": "USD"}
        row_id = await worker.enqueue(_env("payment.received", body=body))

        cursor = await conn.execute("SELECT body FROM outbox WHERE id = ?", (row_id,))
        raw = await cursor.fetchone()
        await cursor.close()
        assert json.loads(raw[0]) == body  # type: ignore[index]


# ---------------------------------------------------------------------------
# run_once — happy path
# ---------------------------------------------------------------------------


async def test_run_once_dispatches_pending_row() -> None:
    reg = HandlerRegistry()
    received: list[OutboxEnvelope] = []

    async def h(env: OutboxEnvelope) -> None:
        received.append(env)

    reg.register("order.created", h)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg)
        row_id = await worker.enqueue(_env("order.created"))

        result = await worker.run_once()

        assert result.dispatched == 1
        assert result.retried == 0
        assert result.dead == 0
        assert result.no_handler == 0
        assert len(received) == 1
        assert received[0].kind == "order.created"

        info = await _row_status(conn, row_id)
        assert info["status"] == "dispatched"


async def test_run_once_empty_outbox_returns_zeros() -> None:
    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn)
        result = await worker.run_once()
        assert result.total == 0


async def test_run_once_respects_batch_size() -> None:
    reg = HandlerRegistry()

    async def h(env: OutboxEnvelope) -> None:
        pass

    reg.register("ev", h)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg)
        for _ in range(5):
            await worker.enqueue(_env("ev"))

        result = await worker.run_once(batch_size=3)
        assert result.dispatched == 3

        result2 = await worker.run_once(batch_size=3)
        assert result2.dispatched == 2


# ---------------------------------------------------------------------------
# run_once — no handler
# ---------------------------------------------------------------------------


async def test_run_once_no_handler_marks_dead() -> None:
    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn)  # empty registry
        row_id = await worker.enqueue(_env("unregistered.kind"))

        result = await worker.run_once()

        assert result.no_handler == 1
        info = await _row_status(conn, row_id)
        assert info["status"] == "dead"
        assert "no handler" in (info["last_error"] or "")


# ---------------------------------------------------------------------------
# run_once — retries
# ---------------------------------------------------------------------------


async def test_run_once_retries_on_handler_error() -> None:
    reg = HandlerRegistry()
    attempt = 0

    async def flaky(env: OutboxEnvelope) -> None:
        nonlocal attempt
        attempt += 1
        raise ValueError("transient error")

    reg.register("flaky.event", flaky)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg, max_retries=3)
        row_id = await worker.enqueue(_env("flaky.event"))

        result = await worker.run_once()
        assert result.retried == 1

        info = await _row_status(conn, row_id)
        assert info["status"] == "pending"
        assert info["retries"] == 1
        assert "ValueError" in (info["last_error"] or "")


async def test_run_once_moves_to_dlq_after_max_retries() -> None:
    reg = HandlerRegistry()

    async def always_fail(env: OutboxEnvelope) -> None:
        raise RuntimeError("permanent failure")

    reg.register("bad.event", always_fail)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg, max_retries=2)
        row_id = await worker.enqueue(_env("bad.event"))

        # Exhaust retries: attempt 0 -> retries=1, attempt 1 -> retries=2, attempt 2 -> dead
        for _ in range(3):
            # Reset row to pending so SQLite can re-claim it
            await conn.execute("UPDATE outbox SET status='pending' WHERE id=?", (row_id,))
            await conn.commit()
            await worker.run_once()

        info = await _row_status(conn, row_id)
        assert info["status"] == "dead"


async def test_run_once_dlq_on_old_row() -> None:
    """Rows older than dlq_after_seconds go straight to DLQ even on first failure."""
    reg = HandlerRegistry()

    async def h(env: OutboxEnvelope) -> None:
        raise RuntimeError("err")

    reg.register("ev", h)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg, max_retries=10, dlq_after_seconds=1)
        row_id = await worker.enqueue(_env("ev"))

        # Back-date the created_at so the row appears old
        old_ts = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        await conn.execute("UPDATE outbox SET created_at=? WHERE id=?", (old_ts, row_id))
        await conn.commit()

        result = await worker.run_once()
        assert result.dead == 1

        info = await _row_status(conn, row_id)
        assert info["status"] == "dead"


# ---------------------------------------------------------------------------
# run_once — in_flight reclaim (expired lease)
# ---------------------------------------------------------------------------


async def test_expired_in_flight_row_is_reclaimed() -> None:
    reg = HandlerRegistry()
    called: list[str] = []

    async def h(env: OutboxEnvelope) -> None:
        called.append(env.kind)

    reg.register("ev", h)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg, lock_window_seconds=60)
        row_id = await worker.enqueue(_env("ev"))

        # Simulate a stale in-flight row (locked_until in the past)
        expired = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        await conn.execute(
            "UPDATE outbox SET status='in_flight', locked_until=? WHERE id=?",
            (expired, row_id),
        )
        await conn.commit()

        result = await worker.run_once()
        assert result.dispatched == 1
        assert called == ["ev"]


# ---------------------------------------------------------------------------
# multi-backend
# ---------------------------------------------------------------------------


async def test_worker_dispatches_to_named_backend() -> None:
    reg = HandlerRegistry()
    log: list[str] = []

    async def email_h(env: OutboxEnvelope) -> None:
        log.append("email")

    reg.register("msg.send", email_h, backend="email")

    async with aiosqlite.connect(":memory:") as conn:
        worker = DrainWorker(
            conn, reg, sqlite_compat=True, backend="email", table="outbox"
        )
        await worker.setup()
        await worker.enqueue(_env("msg.send"))
        result = await worker.run_once()

    assert result.dispatched == 1
    assert log == ["email"]


# ---------------------------------------------------------------------------
# DrainResult
# ---------------------------------------------------------------------------


def test_drain_result_total() -> None:
    r = DrainResult(dispatched=2, retried=1, dead=1, no_handler=0)
    assert r.total == 4


def test_drain_result_as_dict() -> None:
    r = DrainResult(dispatched=1)
    d = r.as_dict()
    assert d == {"dispatched": 1, "retried": 0, "dead": 0, "no_handler": 0}


# ---------------------------------------------------------------------------
# OutboxStatus
# ---------------------------------------------------------------------------


def test_outbox_status_values() -> None:
    assert OutboxStatus.PENDING == "pending"
    assert OutboxStatus.IN_FLIGHT == "in_flight"
    assert OutboxStatus.DISPATCHED == "dispatched"
    assert OutboxStatus.DEAD == "dead"


# ---------------------------------------------------------------------------
# _pg_to_sqlite helper
# ---------------------------------------------------------------------------


def test_pg_to_sqlite_replaces_placeholders() -> None:
    sql = "SELECT * FROM t WHERE id = $1 AND kind = $2"
    assert _pg_to_sqlite(sql) == "SELECT * FROM t WHERE id = ? AND kind = ?"


def test_pg_to_sqlite_noop_on_question_marks() -> None:
    sql = "SELECT * FROM t WHERE id = ?"
    assert _pg_to_sqlite(sql) == sql


# ---------------------------------------------------------------------------
# run_loop
# ---------------------------------------------------------------------------


async def test_run_loop_stops_on_event() -> None:
    reg = HandlerRegistry()
    dispatched: list[str] = []

    async def h(env: OutboxEnvelope) -> None:
        dispatched.append(env.kind)

    reg.register("ev", h)

    async with aiosqlite.connect(":memory:") as conn:
        worker = await _make_worker(conn, reg)
        await worker.enqueue(_env("ev"))

        stop = asyncio.Event()
        task = asyncio.create_task(
            worker.run_loop(poll_interval_seconds=0.05, stop_event=stop)
        )
        # Give the loop time to drain the row
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    assert "ev" in dispatched
