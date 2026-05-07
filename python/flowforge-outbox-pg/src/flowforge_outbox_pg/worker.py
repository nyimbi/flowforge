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
Pass ``sqlite_compat=True`` to ``DrainWorker``. **The SQLite code path is
test-only** — single-writer semantics with no connection pool tolerance
(see audit-2026 E-42 / OB-02). Production deployments MUST run on
PostgreSQL with ``pool_size > 1`` if multiple drain workers are desired.

Audit-2026 hardening (E-42, findings OB-01..OB-04)
--------------------------------------------------
* OB-01: ``table`` is validated at constructor against
  ``^[a-zA-Z_][a-zA-Z_0-9.]*$``. Raw ``f"... {self._table} ..."`` is safe
  only because of this whitelist; the security ratchet
  ``scripts/ci/ratchets/no_string_interp_sql.sh`` documents the exception.
* OB-02: ``DrainWorker(..., sqlite_compat=True, pool_size>1)`` raises
  ``RuntimeError``. SQLite is single-writer.
* OB-03: ``reconnect_factory`` callback fires on connection-lost
  exceptions inside ``run_loop``; the worker swaps in a fresh connection
  and resumes draining. ``self.reconnects`` exposes the count for metrics.
* OB-04: ``last_error`` is truncated by UTF-8 byte budget, never
  mid-codepoint. See :func:`_truncate_utf8`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from flowforge.ports.types import OutboxEnvelope

from .registry import DispatchError, HandlerRegistry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# audit-2026 E-42 / OB-01: table-name whitelist for safe identifier interpolation
# ---------------------------------------------------------------------------

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9.]*$")


def _validate_table_name(table: str) -> str:
	"""Whitelist-validate a SQL table identifier (audit-2026 OB-01).

	Outbox SQL interpolates the table name directly because asyncpg/aiosqlite
	don't bind identifiers as parameters. The regex enforces the standard
	identifier shape (``schema.table`` accepted via ``.``) so injection
	payloads like ``"x; DROP TABLE foo"`` raise :class:`ValueError` at
	construction rather than reaching the database.
	"""

	if not isinstance(table, str) or not _TABLE_NAME_RE.match(table):
		raise ValueError(
			f"invalid outbox table name {table!r}: must match ^[a-zA-Z_][a-zA-Z_0-9.]*$"
		)
	return table


# ---------------------------------------------------------------------------
# audit-2026 E-42 / OB-04: UTF-8 safe error-string truncation
# ---------------------------------------------------------------------------


def _truncate_utf8(s: str, max_bytes: int = 2000) -> str:
	"""Truncate *s* to at most *max_bytes* UTF-8 bytes — never mid-codepoint.

	A naive ``s[:max_bytes]`` cuts at codepoint count, not byte count, so
	emoji / CJK strings overflow byte-bounded columns. Encoding with
	``errors='replace'`` then decoding with ``errors='ignore'`` discards
	any partial trailing bytes left behind by the byte-level slice.
	"""

	if not isinstance(s, str):
		s = str(s)
	encoded = s.encode("utf-8", errors="replace")
	if len(encoded) <= max_bytes:
		return s
	return encoded[:max_bytes].decode("utf-8", errors="ignore")


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
        pool_size: int = 1,
        reconnect_factory: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        # audit-2026 OB-01: whitelist the table name before it ever reaches SQL.
        self._table = _validate_table_name(table)
        # audit-2026 OB-02: SQLite path is test-only; reject pool_size > 1.
        if sqlite_compat and pool_size > 1:
            raise RuntimeError(
                f"sqlite_compat=True is single-writer; refusing pool_size={pool_size} "
                "(SQLite cannot serialise concurrent writers safely — use PostgreSQL)"
            )
        if pool_size < 1:
            raise ValueError(f"pool_size must be >= 1, got {pool_size}")
        self._conn = conn
        self._registry = registry
        self._backend = backend
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._dlq_after_seconds = dlq_after_seconds
        self._lock_window_seconds = lock_window_seconds
        self._sqlite_compat = sqlite_compat
        self._pool_size = pool_size
        self._reconnect_factory = reconnect_factory
        # audit-2026 OB-03: metric counter — increments each time the worker
        # swaps in a fresh connection from `reconnect_factory`. Read-only for
        # callers (e.g. exposed via Prometheus collector).
        self.reconnects: int = 0

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
            except Exception as exc:  # noqa: BLE001
                # audit-2026 OB-03: connection-loss recovery. If a
                # reconnect_factory is registered and the failure looks like
                # a connection-level issue, swap in a fresh connection and
                # resume the loop. Other failures fall through to log+sleep.
                if self._reconnect_factory is not None and _is_connection_lost(exc):
                    log.warning(
                        "outbox connection lost (%s) — reconnecting",
                        type(exc).__name__,
                    )
                    try:
                        new_conn = await self._reconnect_factory()
                    except Exception:  # noqa: BLE001
                        log.exception("outbox reconnect failed")
                    else:
                        self._conn = new_conn
                        self.reconnects += 1
                        log.info("outbox reconnected (count=%d)", self.reconnects)
                else:
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
        # audit-2026 OB-04: byte-budget UTF-8 truncation; never mid-codepoint.
        await self._exec(sql, retries, _truncate_utf8(last_error, 2000), row_id)

    async def _mark_dead(self, row_id: str, *, last_error: str) -> None:
        sql = (
            f"UPDATE {self._table}"
            " SET status = 'dead', locked_until = NULL, last_error = ?"
            " WHERE id = ?"
        )
        # audit-2026 OB-04: byte-budget UTF-8 truncation; never mid-codepoint.
        await self._exec(sql, _truncate_utf8(last_error, 2000), row_id)

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


# ---------------------------------------------------------------------------
# audit-2026 E-42 / OB-03: connection-lost detection for run_loop reconnect
# ---------------------------------------------------------------------------

# Pattern-match against type names so we don't import the asyncpg / aiosqlite
# packages just to inspect their exception trees. This keeps the worker
# usable in environments where the unused driver isn't installed.
_RECONNECT_TYPE_NAMES = frozenset(
    {
        # asyncpg connection-state errors
        "ConnectionDoesNotExistError",
        "ConnectionFailureError",
        "InterfaceError",
        "PostgresConnectionError",
        # generic socket-level
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "TimeoutError",
        "OSError",
    }
)

# Phrases on the exception message that indicate a recoverable connection
# loss for SQLite / generic DB-API errors. We require the full phrase rather
# than a bare keyword so unrelated messages that happen to contain the word
# "connection" don't trigger reconnect (e.g. "not a connection issue").
_RECONNECT_MESSAGE_HINTS = (
    "connection reset",
    "connection refused",
    "connection closed",
    "connection lost",
    "connection aborted",
    "broken pipe",
    "server closed",
    "server disconnected",
    "database is locked",
    "no connection",
    "lost connection",
    "disconnected",
)


def _is_connection_lost(exc: BaseException) -> bool:
    """Heuristic: does *exc* look like a recoverable connection-loss?

    The driver-specific exception tree is matched by class name to avoid an
    import dependency on asyncpg/aiosqlite. Falls back to a phrase match on
    the exception message for generic DB-API errors. Phrases (not bare words)
    keep the detector from misfiring on unrelated messages.
    """

    if isinstance(exc, OSError):
        return True
    if type(exc).__name__ in _RECONNECT_TYPE_NAMES:
        return True
    msg = str(exc).lower()
    return any(hint in msg for hint in _RECONNECT_MESSAGE_HINTS)


__all__ = [
    "DbConnection",
    "DrainResult",
    "DrainWorker",
    "OutboxRow",
    "OutboxStatus",
]
