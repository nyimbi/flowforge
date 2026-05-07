"""PostgreSQL-backed AuditSink implementing the flowforge AuditSink Protocol.

Design goals
------------
* Append-only table ``ff_audit_events`` with a DELETE-blocking PG trigger
  installed via an Alembic-compatible migration helper.
* sha256 hash chain: each row stores ``prev_sha256`` (the previous row's
  ``row_sha256``) and ``row_sha256 = sha256(prev_sha256 + canonical_json)``.
* GDPR redaction via tombstone marker — the chain is preserved because the
  sha256 columns are not rewritten.
* SQLite fallback for tests (DELETE-blocking trigger replaced by a Python
  guard; chain logic is identical).

Audit 2026 (E-37) hardenings:
* AU-01 — concurrent record race: per-tenant serialisation point. PG uses
  ``pg_advisory_xact_lock(hashtext(tenant_norm))`` inside the insert tx;
  SQLite uses an in-process ``asyncio.Lock`` keyed by tenant_id. A
  ``UNIQUE(tenant_id, ordinal)`` constraint catches regressions at the
  schema layer.
* AU-02 — verify_chain streams the rows in ``VERIFY_CHUNK_SIZE`` batches
  via keyset pagination, so peak memory is bounded by chunk size.
* AU-03 — canonical golden bytes fixture is shipped under
  ``framework/tests/audit_2026/fixtures/canonical_golden.bin`` and the
  ``_golden`` helper module is the loader/regenerator.

Usage::

    from flowforge_audit_pg import PgAuditSink
    from flowforge_audit_pg.sink import create_tables

    async with engine.begin() as conn:
        await create_tables(conn)

    sink = PgAuditSink(engine)
    event_id = await sink.record(audit_event)
    verdict  = await sink.verify_chain()
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any

try:
	from uuid6 import uuid7

	def _new_id() -> str:
		return str(uuid7())

except ImportError:
	import uuid

	def _new_id() -> str:  # type: ignore[misc]
		return str(uuid.uuid4())


import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

from flowforge.ports.audit import Verdict
from flowforge.ports.types import AuditEvent

from .hash_chain import (
	AuditRow,
	canonical_json,
	compute_row_sha,
	redact_payload,
)


# ---------------------------------------------------------------------------
# Tunables (E-37 AU-02)
# ---------------------------------------------------------------------------

#: Chunk size used by ``verify_chain()``. Tunable in tests / large-tenant
#: deployments. 10K is the audit-fix-plan reference (memory <256MB at 10M
#: rows); tests override to a small value to exercise chunk boundaries.
VERIFY_CHUNK_SIZE: int = 10_000

#: Sentinel tenant key for rows whose ``tenant_id`` is NULL — the advisory
#: lock and per-tenant ordinal must still serialise these rows.
_NONE_TENANT_KEY: str = "__none__"


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_METADATA = sa.MetaData()

ff_audit_events = sa.Table(
	"ff_audit_events",
	_METADATA,
	sa.Column("event_id", sa.String, primary_key=True),
	sa.Column("tenant_id", sa.String, nullable=True, index=True),
	sa.Column("actor_user_id", sa.String, nullable=True),
	sa.Column("kind", sa.String, nullable=False),
	sa.Column("subject_kind", sa.String, nullable=False),
	sa.Column("subject_id", sa.String, nullable=False),
	sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
	sa.Column("payload", sa.JSON, nullable=False, default=dict),
	sa.Column("prev_sha256", sa.String(64), nullable=True),
	sa.Column("row_sha256", sa.String(64), nullable=True),
	# E-37 AU-01: per-tenant monotonic ordinal. NULL ⇒ legacy row pre-AU-01;
	# the UNIQUE constraint ignores NULL ordinals so old data still loads.
	sa.Column("ordinal", sa.BigInteger, nullable=True),
	sa.UniqueConstraint("tenant_id", "ordinal", name="uq_ff_audit_tenant_ordinal"),
)

# PG trigger that blocks DELETE on ff_audit_events.
_PG_TRIGGER_FUNC = """
CREATE OR REPLACE FUNCTION ff_audit_no_delete()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ff_audit_events is append-only: DELETE is forbidden';
END;
$$;
"""

_PG_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'ff_audit_no_delete_tg'
    ) THEN
        CREATE TRIGGER ff_audit_no_delete_tg
        BEFORE DELETE ON ff_audit_events
        FOR EACH ROW EXECUTE FUNCTION ff_audit_no_delete();
    END IF;
END;
$$;
"""


def _is_postgres(conn: AsyncConnection) -> bool:
	return "postgresql" in str(conn.engine.url)


async def create_tables(conn: AsyncConnection) -> None:
	"""Create ``ff_audit_events`` and install the DELETE-blocking trigger (PG only)."""
	await conn.run_sync(_METADATA.create_all)
	if _is_postgres(conn):
		await conn.execute(text(_PG_TRIGGER_FUNC))
		await conn.execute(text(_PG_TRIGGER))


# ---------------------------------------------------------------------------
# Sink implementation
# ---------------------------------------------------------------------------

class PgAuditSink:
	"""PostgreSQL (or SQLite for tests) AuditSink with sha256 hash chain.

	Parameters
	----------
	engine:
	    An async SQLAlchemy engine.  Must point at a database where
	    :func:`create_tables` has already been called.
	"""

	def __init__(self, engine: AsyncEngine) -> None:
		self._engine = engine
		# E-37 AU-01: per-tenant serialisation. PG uses an advisory xact lock;
		# SQLite uses an in-process asyncio.Lock keyed by tenant. We keep the
		# locks per-sink so test fixtures don't leak state across tests.
		self._tenant_locks: dict[str, asyncio.Lock] = {}
		self._tenant_locks_guard = asyncio.Lock()

	# ------------------------------------------------------------------
	# AuditSink protocol
	# ------------------------------------------------------------------

	async def record(self, event: AuditEvent) -> str:
		"""Append *event* and return the assigned event_id."""
		event_id = _new_id()
		occurred_at = event.occurred_at
		if occurred_at.tzinfo is None:
			occurred_at = occurred_at.replace(tzinfo=timezone.utc)

		row_data: dict[str, Any] = {
			"tenant_id": event.tenant_id,
			"actor_user_id": event.actor_user_id,
			"kind": event.kind,
			"subject_kind": event.subject_kind,
			"subject_id": event.subject_id,
			"occurred_at": occurred_at,
			"payload": event.payload,
		}

		tenant_key = event.tenant_id or _NONE_TENANT_KEY
		py_lock = await self._py_lock_for(tenant_key)

		# AU-01: serialise the read+insert pair per tenant. On PG the advisory
		# lock is the authoritative gate; on SQLite (tests) the asyncio.Lock
		# is, since SQLite has no advisory locks.
		async with py_lock:
			async with self._engine.begin() as conn:
				if _is_postgres(conn):
					await conn.execute(
						text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
						{"k": tenant_key},
					)
				prev_sha = await self._chain_head(conn, event.tenant_id)
				next_ordinal = await self._next_ordinal(conn, event.tenant_id)
				row_sha = compute_row_sha(prev_sha, row_data)
				await conn.execute(
					ff_audit_events.insert().values(
						event_id=event_id,
						prev_sha256=prev_sha,
						row_sha256=row_sha,
						ordinal=next_ordinal,
						**row_data,
					)
				)
		return event_id

	async def verify_chain(self, since: str | None = None) -> Verdict:
		"""Walk the hash chain and return a :class:`~flowforge.ports.audit.Verdict`.

		AU-02: rows are streamed in ``VERIFY_CHUNK_SIZE`` chunks via keyset
		pagination on ``(occurred_at, event_id)`` so peak memory is bounded
		by the chunk, not by total row count.
		"""
		since_dt: datetime | None = None
		async with self._engine.connect() as conn:
			if since is not None:
				if _looks_like_datetime(since):
					since_dt = datetime.fromisoformat(since)
				else:
					sub = sa.select(ff_audit_events.c.occurred_at).where(
						ff_audit_events.c.event_id == since
					)
					result = await conn.execute(sub)
					row = result.fetchone()
					if row is not None:
						since_dt = row[0]
						if since_dt is not None and since_dt.tzinfo is None:
							since_dt = since_dt.replace(tzinfo=timezone.utc)

			prev_sha: str | None = None
			checked = 0
			cursor_dt: datetime | None = since_dt
			cursor_id: str | None = None

			while True:
				stmt = sa.select(ff_audit_events)
				if cursor_dt is not None and cursor_id is not None:
					# keyset: strictly after (cursor_dt, cursor_id)
					stmt = stmt.where(
						sa.or_(
							ff_audit_events.c.occurred_at > cursor_dt,
							sa.and_(
								ff_audit_events.c.occurred_at == cursor_dt,
								ff_audit_events.c.event_id > cursor_id,
							),
						)
					)
				elif cursor_dt is not None:
					stmt = stmt.where(ff_audit_events.c.occurred_at >= cursor_dt)

				stmt = (
					stmt.order_by(
						ff_audit_events.c.occurred_at.asc(),
						ff_audit_events.c.event_id.asc(),
					)
					.limit(VERIFY_CHUNK_SIZE)
				)
				rows_raw = (await conn.execute(stmt)).fetchall()
				if not rows_raw:
					break

				for raw in rows_raw:
					row = _row_from_db(raw)
					if row.row_sha256 is None:
						# Legacy pre-chain row; skip without advancing prev_sha.
						checked += 1
						cursor_dt = row.occurred_at
						cursor_id = row.event_id
						continue
					canonical = canonical_json(_row_to_canonical_dict(row))
					expected = hashlib.sha256(
						((prev_sha or "") + canonical).encode()
					).hexdigest()
					if row.row_sha256 != expected:
						return Verdict.supported_bad(row.event_id, checked + 1)
					prev_sha = row.row_sha256
					checked += 1
					cursor_dt = row.occurred_at
					cursor_id = row.event_id

				# If the chunk wasn't full we've consumed everything.
				if len(rows_raw) < VERIFY_CHUNK_SIZE:
					break

		return Verdict.supported_ok(checked)

	async def redact(self, paths: list[str], reason: str) -> int:
		"""Tombstone *paths* across all rows that contain them; return count.

		The sha256 chain columns are left intact so chain verification
		continues to pass.  The payload is updated with ``__REDACTED__``
		markers at each dotted path.
		"""
		count = 0
		async with self._engine.begin() as conn:
			result = await conn.execute(
				sa.select(ff_audit_events.c.event_id, ff_audit_events.c.payload)
			)
			rows = result.fetchall()
			for event_id, payload in rows:
				if payload is None:
					payload = {}
				new_payload = redact_payload(payload, paths)
				new_payload["__redaction_reason__"] = reason
				if new_payload != payload:
					await conn.execute(
						ff_audit_events.update()
						.where(ff_audit_events.c.event_id == event_id)
						.values(payload=new_payload)
					)
					count += 1
		return count

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	async def _py_lock_for(self, tenant_key: str) -> asyncio.Lock:
		"""Per-tenant in-process lock (used by SQLite path; harmless on PG)."""
		async with self._tenant_locks_guard:
			lock = self._tenant_locks.get(tenant_key)
			if lock is None:
				lock = asyncio.Lock()
				self._tenant_locks[tenant_key] = lock
			return lock

	async def _chain_head(
		self, conn: AsyncConnection, tenant_id: str | None
	) -> str | None:
		"""Return the row_sha256 of the most recent row for *tenant_id*.

		Ordering is by ordinal DESC because occurred_at can collide on
		microsecond boundaries under concurrency. Pre-AU-01 rows have
		``ordinal=NULL`` and only fall back to the occurred_at ordering.
		"""
		stmt = (
			sa.select(ff_audit_events.c.row_sha256)
			.where(ff_audit_events.c.row_sha256.is_not(None))
			.order_by(
				ff_audit_events.c.ordinal.desc().nulls_last(),
				ff_audit_events.c.occurred_at.desc(),
			)
			.limit(1)
		)
		if tenant_id is not None:
			stmt = stmt.where(ff_audit_events.c.tenant_id == tenant_id)
		else:
			stmt = stmt.where(ff_audit_events.c.tenant_id.is_(None))
		result = await conn.execute(stmt)
		row = result.fetchone()
		return row[0] if row else None

	async def _next_ordinal(
		self, conn: AsyncConnection, tenant_id: str | None
	) -> int:
		"""Compute the next per-tenant ordinal under the held advisory lock."""
		stmt = sa.select(sa.func.max(ff_audit_events.c.ordinal))
		if tenant_id is not None:
			stmt = stmt.where(ff_audit_events.c.tenant_id == tenant_id)
		else:
			stmt = stmt.where(ff_audit_events.c.tenant_id.is_(None))
		result = await conn.execute(stmt)
		row = result.fetchone()
		current = (row[0] if row else None) or 0
		return int(current) + 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_dt(dt: datetime) -> datetime:
	"""Ensure datetime is UTC-aware (SQLite drops tzinfo on round-trip)."""
	if dt is None:
		return dt
	if dt.tzinfo is None:
		return dt.replace(tzinfo=timezone.utc)
	return dt


def _row_from_db(row: Any) -> AuditRow:
	return AuditRow(
		event_id=row.event_id,
		tenant_id=row.tenant_id,
		actor_user_id=row.actor_user_id,
		kind=row.kind,
		subject_kind=row.subject_kind,
		subject_id=row.subject_id,
		occurred_at=_normalise_dt(row.occurred_at),
		payload=row.payload or {},
		prev_sha256=row.prev_sha256,
		row_sha256=row.row_sha256,
	)


def _row_to_canonical_dict(row: AuditRow) -> dict[str, Any]:
	return {
		"tenant_id": row.tenant_id,
		"actor_user_id": row.actor_user_id,
		"kind": row.kind,
		"subject_kind": row.subject_kind,
		"subject_id": row.subject_id,
		"occurred_at": row.occurred_at,
		"payload": row.payload,
	}


def _looks_like_datetime(s: str) -> bool:
	"""Return True iff *s* is parseable as an ISO-8601 datetime.

	E-60 / AU-04 (audit-fix-plan §4.3): the legacy implementation used
	a ``^\\d{4}-\\d{2}-\\d{2}`` regex that also accepted UUID-shaped
	event-ids whose first 10 chars happened to satisfy the 4-2-2 digit
	pattern (e.g. ``"2024-12-31-abcd-..."``). The fromisoformat-backed
	gate rejects those — only strings the standard library can parse
	as a real datetime now produce a True.

	Postgres' default ``timestamp with time zone`` text form uses a
	space separator instead of ``'T'`` (``"2026-05-06 12:34:56+00"``);
	we accept both by swapping the space for a ``T`` before delegating.
	"""

	if not s or not isinstance(s, str):
		return False
	candidate = s.replace(" ", "T", 1) if " " in s and "T" not in s else s
	# Strip a trailing 'Z' (UTC marker) — fromisoformat on Python 3.11
	# rejects the literal Z but accepts +00:00.
	if candidate.endswith("Z"):
		candidate = candidate[:-1] + "+00:00"
	try:
		datetime.fromisoformat(candidate)
	except (ValueError, TypeError):
		return False
	return True
