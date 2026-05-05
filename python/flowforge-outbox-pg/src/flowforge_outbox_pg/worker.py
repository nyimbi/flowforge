"""Drain worker — poll outbox table, claim rows, dispatch, retry, DLQ.

Design
------
The outbox table has columns::

    id            TEXT primary key
    kind          TEXT          handler key
    tenant_id     TEXT
    body          TEXT/JSONB    JSON-encoded payload
    status        TEXT          pending | in_flight | dispatched | dead
    retries       INTEGER       attempt count (starts 0)
    created_at    TEXT/TIMESTAMP
    locked_until  TEXT/TIMESTAMP in-flight lease expiry
    last_error    TEXT          last failure message
    correlation_id TEXT
    dedupe_key    TEXT

Claim strategy (PostgreSQL)::

    UPDATE outbox
    SET status='in_flight', locked_until=<now + lock_window>
    WHERE id IN (
        SELECT id FROM outbox
        WHERE status='pending'
           OR (status='in_flight' AND locked_until < <now>)
        ORDER BY created_at ASC
        LIMIT <batch_size>
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, kind, tenant_id, body, retries, created_at

SQLite compat (for tests): a simpler claim without FOR UPDATE SKIP LOCKED.
Pass ``sqlite_compat=True`` to ``DrainWorker``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from flowforge.ports.types import OutboxEnvelope

from .registry import DispatchError, HandlerRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class OutboxStatus(str, Enum):
    """Lifecycle states for an outbox row."""

    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DISPATCHED = "dispatched"
    DEAD = "dead"


@dataclass
class OutboxRow:
    """One outbox table row returned by the claim query."""

    id: str
    kind: str
    tenant_id: str
    body: dict[str, Any]
    retries: int
    created_at: datetime
    correlation_id: str | None = None
    dedupe_key: str | None = None


@dataclass
class DrainResult:
    """Counters returned from a single ``run_once`` invocation."""

    dispatched: int = 0
    retried: int = 0
    dead: int = 0
    no_handler: int = 0

    @property
    def total(self) -> int:
        return self.dispatched + self.retried + self.dead + self.no_handler

    def as_dict(self) -> dict[str, int]:
        return {
            "dispatched": self.dispatched,
            "retried": self.retried,
            "dead": self.dead,
            "no_handler": self.no_handler,
        }


# ---------------------------------------------------------------------------
# DB protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DbConnection(Protocol):
    """Thin protocol accepted by DrainWorker.

    Both asyncpg ``Connection`` and aiosqlite ``Connection`` satisfy this
    after the internal _exec / _fetchall wrappers normalize the call style.
    """

    async def execute(self, sql: str, *args: Any) -> Any: ...


# ---------------------------------------------------------------------------
# DrainWorker
# ---------------------------------------------------------------------------


class DrainWorker:
    """Outbox drain worker.

    Parameters
    ----------
    conn:
        An open database connection.  For PostgreSQL pass an asyncpg
        ``Connection``; for SQLite (test mode) pass an aiosqlite ``Connection``
        and set ``sqlite_compat=True``.
    registry:
        The ``HandlerRegistry`` whose handlers will be called.
    backend:
        The backend name passed to ``registry.dispatch``.
    batch_size:
        Max rows to claim per ``run_once`` call.
    max_retries:
        After this many attempts the row moves to DLQ (status='dead').
    dlq_after_seconds:
        Rows older than this also move to DLQ regardless of retry count.
    lock_window_seconds:
        Lease duration for in-flight rows. A row whose ``locked_until`` is in
        the past is reclaimable by any worker.
    table:
        The SQL table name (schema-qualified for PG, plain for SQLite).
    sqlite_compat:
        When ``True`` the worker uses a simpler claim without
        ``FOR UPDATE SKIP LOCKED``. Set this in tests.
    """

    def __init__(
        self,
        conn: Any,
        registry: HandlerRegistry,
        *,
        backend: str = "default",
        batch_size: int = 32,
        max_retries: int = 5,
        dlq_after_seconds: int = 3600,
        lock_window_seconds: int = 60,
        table: str = "outbox",
        sqlite_compat: bool = False,
    ) -> None:
        self._conn = conn
        self._registry = registry
        self._backend = backend
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._dlq_after_seconds = dlq_after_seconds
        self._lock_window_seconds = lock_window_seconds
        self._table = table
        self._sqlite_compat = sqlite_compat

    # ------------------------------------------------------------------
    # Schema bootstrap (tests)
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Create the outbox table if it doesn't exist.

        In production the table is created by your Alembic migration.
        This method exists so tests can call it on an in-memory SQLite
        database without any migration tooling.
        """
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self._table} (
            id             TEXT PRIMARY KEY,
            kind           TEXT NOT NULL,
            tenant_id      TEXT NOT NULL DEFAULT '',
            body           TEXT NOT NULL DEFAULT '{{}}',
            status         TEXT NOT NULL DEFAULT 'pending',
            retries        INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT NOT NULL,
            locked_until   TEXT,
            last_error     TEXT,
            correlation_id TEXT,
            dedupe_key     TEXT
        )
        """
        await self._exec(ddl)

    # ------------------------------------------------------------------
    # Enqueue helper
    # ------------------------------------------------------------------

    async def enqueue(self, envelope: OutboxEnvelope, row_id: str | None = None) -> str:
        """Insert one row into the outbox table.

        Parameters
        ----------
        envelope:
            The ``OutboxEnvelope`` to persist.
        row_id:
            Optional explicit row id. Defaults to a UUID7 string.

        Returns
        -------
        str
            The ``id`` of the inserted row.
        """
        if row_id is None:
            try:
                from uuid6 import uuid7  # type: ignore[import-untyped]
                row_id = str(uuid7())
            except ImportError:
                import uuid
                row_id = str(uuid.uuid4())

        now_str = datetime.now(UTC).isoformat()
        sql = (
            f"INSERT INTO {self._table}"
            " (id, kind, tenant_id, body, status, retries, created_at, correlation_id, dedupe_key)"
            " VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?)"
        )
        await self._exec(
            sql,
            row_id,
            envelope.kind,
            envelope.tenant_id,
            json.dumps(envelope.body),
            now_str,
            envelope.correlation_id,
            envelope.dedupe_key,
        )
        return row_id

    # ------------------------------------------------------------------
    # Drain
    # ------------------------------------------------------------------

    async def run_once(self, batch_size: int | None = None) -> DrainResult:
        """Claim and process at most *batch_size* pending rows.

        Returns a ``DrainResult`` with per-outcome counters.
        """
        bs = batch_size if batch_size is not None else self._batch_size
        result = DrainResult()

        rows = await self._claim_batch(bs)
        if not rows:
            return result

        for row in rows:
            await self._process_row(row, result)

        return result

    async def run_loop(
        self,
        *,
        poll_interval_seconds: float = 1.0,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Run the drain loop until *stop_event* is set (or forever).

        Intended for use in a background task::

            stop = asyncio.Event()
            task = asyncio.create_task(worker.run_loop(stop_event=stop))
            ...
            stop.set()
            await task
        """
        while stop_event is None or not stop_event.is_set():
            try:
                result = await self.run_once()
                if result.total > 0:
                    log.debug("drain_once result=%s", result.as_dict())
            except Exception:  # noqa: BLE001
                log.exception("drain_once error")
            await asyncio.sleep(poll_interval_seconds)

    # ------------------------------------------------------------------
    # Internal: claim
    # ------------------------------------------------------------------

    async def _claim_batch(self, batch_size: int) -> list[OutboxRow]:
        now = datetime.now(UTC)
        lock_until = now + timedelta(seconds=self._lock_window_seconds)

        if self._sqlite_compat:
            return await self._claim_sqlite(now, lock_until, batch_size)
        return await self._claim_pg(now, lock_until, batch_size)

    async def _claim_sqlite(
        self,
        now: datetime,
        lock_until: datetime,
        batch_size: int,
    ) -> list[OutboxRow]:
        """SQLite-compatible claim (no FOR UPDATE SKIP LOCKED)."""
        now_str = now.isoformat()
        lock_str = lock_until.isoformat()

        select_sql = (
            f"SELECT id FROM {self._table}"
            " WHERE status = 'pending'"
            " OR (status = 'in_flight' AND (locked_until IS NULL OR locked_until < ?))"
            " ORDER BY created_at ASC LIMIT ?"
        )
        candidate_rows = await self._fetchall(select_sql, now_str, batch_size)
        if not candidate_rows:
            return []

        ids = [r[0] for r in candidate_rows]
        placeholders = ",".join("?" * len(ids))
        update_sql = (
            f"UPDATE {self._table} SET status = 'in_flight', locked_until = ?"
            f" WHERE id IN ({placeholders})"
        )
        await self._exec(update_sql, lock_str, *ids)

        fetch_sql = (
            f"SELECT id, kind, tenant_id, body, retries, created_at, correlation_id, dedupe_key"
            f" FROM {self._table} WHERE id IN ({placeholders})"
        )
        raw = await self._fetchall(fetch_sql, *ids)
        return [self._parse_row(r) for r in raw]

    async def _claim_pg(
        self,
        now: datetime,
        lock_until: datetime,
        batch_size: int,
    ) -> list[OutboxRow]:
        """PostgreSQL claim using FOR UPDATE SKIP LOCKED."""
        sql = (
            f"UPDATE {self._table}"
            " SET status = 'in_flight', locked_until = $1"
            " WHERE id IN ("
            f"    SELECT id FROM {self._table}"
            "     WHERE status = 'pending'"
            "        OR (status = 'in_flight' AND (locked_until IS NULL OR locked_until < $2))"
            "     ORDER BY created_at ASC"
            "     LIMIT $3"
            "     FOR UPDATE SKIP LOCKED"
            " )"
            " RETURNING id, kind, tenant_id, body, retries, created_at, correlation_id, dedupe_key"
        )
        raw = await self._conn.fetch(sql, lock_until, now, batch_size)
        return [self._parse_row(r) for r in raw]

    # ------------------------------------------------------------------
    # Internal: process one row
    # ------------------------------------------------------------------

    async def _process_row(self, row: OutboxRow, result: DrainResult) -> None:
        if not self._registry.has_handler(row.kind, self._backend):
            log.warning("no_handler kind=%r backend=%r row_id=%s", row.kind, self._backend, row.id)
            result.no_handler += 1
            await self._mark_dead(row.id, last_error=f"no handler for kind={row.kind!r}")
            return

        envelope = OutboxEnvelope(
            kind=row.kind,
            tenant_id=row.tenant_id,
            body=row.body,
            correlation_id=row.correlation_id,
            dedupe_key=row.dedupe_key,
        )

        try:
            await self._registry.dispatch(envelope, backend=self._backend)
        except DispatchError as exc:
            result.no_handler += 1
            await self._mark_dead(row.id, last_error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            age = (datetime.now(UTC) - _ensure_aware(row.created_at)).total_seconds()
            if row.retries + 1 > self._max_retries or age > self._dlq_after_seconds:
                log.warning(
                    "row_dead id=%s kind=%r retries=%d age=%.0fs err=%s",
                    row.id, row.kind, row.retries, age, last_error,
                )
                result.dead += 1
                await self._mark_dead(row.id, last_error=last_error)
            else:
                log.info(
                    "row_retry id=%s kind=%r attempt=%d err=%s",
                    row.id, row.kind, row.retries + 1, last_error,
                )
                result.retried += 1
                await self._mark_for_retry(row.id, row.retries + 1, last_error=last_error)
            return

        result.dispatched += 1
        await self._mark_dispatched(row.id)

    # ------------------------------------------------------------------
    # Internal: status updates
    # ------------------------------------------------------------------

    async def _mark_dispatched(self, row_id: str) -> None:
        sql = (
            f"UPDATE {self._table}"
            " SET status = 'dispatched', locked_until = NULL, last_error = NULL"
            " WHERE id = ?"
        )
        await self._exec(sql, row_id)

    async def _mark_for_retry(self, row_id: str, retries: int, *, last_error: str) -> None:
        sql = (
            f"UPDATE {self._table}"
            " SET status = 'pending', retries = ?, locked_until = NULL, last_error = ?"
            " WHERE id = ?"
        )
        await self._exec(sql, retries, last_error[:2000], row_id)

    async def _mark_dead(self, row_id: str, *, last_error: str) -> None:
        sql = (
            f"UPDATE {self._table}"
            " SET status = 'dead', locked_until = NULL, last_error = ?"
            " WHERE id = ?"
        )
        await self._exec(sql, last_error[:2000], row_id)

    # ------------------------------------------------------------------
    # Internal: DB helpers
    # ------------------------------------------------------------------

    async def _exec(self, sql: str, *args: Any) -> None:
        """Execute *sql* with positional args.

        In SQLite compat mode we replace $N markers with ? before dispatch.
        """
        if self._sqlite_compat:
            sql = _pg_to_sqlite(sql)
            cursor = await self._conn.execute(sql, args)
            await self._conn.commit()
            await cursor.close()
        else:
            await self._conn.execute(sql, *args)

    async def _fetchall(self, sql: str, *args: Any) -> list[Any]:
        if self._sqlite_compat:
            sql = _pg_to_sqlite(sql)
            cursor = await self._conn.execute(sql, args)
            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        return await self._conn.fetch(sql, *args)

    def _parse_row(self, raw: Any) -> OutboxRow:
        """Parse a DB row (tuple or mapping) into ``OutboxRow``."""
        if isinstance(raw, (tuple, list)):
            row_id, kind, tenant_id, body_raw, retries, created_raw, correlation_id, dedupe_key = raw
        else:
            row_id = raw["id"]
            kind = raw["kind"]
            tenant_id = raw["tenant_id"]
            body_raw = raw["body"]
            retries = raw["retries"]
            created_raw = raw["created_at"]
            correlation_id = raw.get("correlation_id")
            dedupe_key = raw.get("dedupe_key")

        body: dict[str, Any] = body_raw if isinstance(body_raw, dict) else json.loads(body_raw or "{}")
        created_at = _parse_dt(created_raw)

        return OutboxRow(
            id=row_id,
            kind=kind,
            tenant_id=tenant_id,
            body=body,
            retries=int(retries or 0),
            created_at=created_at,
            correlation_id=correlation_id,
            dedupe_key=dedupe_key,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    s = str(value).replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.now(UTC)
    return _ensure_aware(dt)


def _pg_to_sqlite(sql: str) -> str:
    """Replace PostgreSQL $N placeholders with SQLite ``?`` markers."""
    return re.sub(r"\$\d+", "?", sql)


__all__ = [
    "DbConnection",
    "DrainResult",
    "DrainWorker",
    "OutboxRow",
    "OutboxStatus",
]
