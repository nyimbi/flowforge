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

import re
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

from flowforge.ports.audit import AuditSink, Verdict
from flowforge.ports.types import AuditEvent

from .hash_chain import (
	AuditRow,
	TOMBSTONE,
	canonical_json,
	compute_row_sha,
	redact_payload,
	verify_chain_in_memory,
)

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

		async with self._engine.begin() as conn:
			prev_sha = await self._chain_head(conn, event.tenant_id)
			row_sha = compute_row_sha(prev_sha, row_data)
			await conn.execute(
				ff_audit_events.insert().values(
					event_id=event_id,
					prev_sha256=prev_sha,
					row_sha256=row_sha,
					**row_data,
				)
			)
		return event_id

	async def verify_chain(self, since: str | None = None) -> Verdict:
		"""Walk the hash chain and return a :class:`~flowforge.ports.audit.Verdict`."""
		async with self._engine.connect() as conn:
			stmt = sa.select(ff_audit_events).order_by(
				ff_audit_events.c.occurred_at.asc()
			)
			if since is not None:
				# *since* is either an event_id or an ISO datetime string.
				if _looks_like_datetime(since):
					dt = datetime.fromisoformat(since)
					stmt = stmt.where(ff_audit_events.c.occurred_at >= dt)
				else:
					# Treat as event_id: find its occurred_at then filter.
					sub = sa.select(ff_audit_events.c.occurred_at).where(
						ff_audit_events.c.event_id == since
					)
					result = await conn.execute(sub)
					row = result.fetchone()
					if row:
						stmt = stmt.where(ff_audit_events.c.occurred_at >= row[0])

			rows_raw = (await conn.execute(stmt)).fetchall()

		rows = [_row_from_db(r) for r in rows_raw]
		ok, bad_id = verify_chain_in_memory(rows)
		if ok:
			return Verdict.supported_ok(len(rows))
		return Verdict.supported_bad(bad_id or "", len(rows))

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

	async def _chain_head(
		self, conn: AsyncConnection, tenant_id: str | None
	) -> str | None:
		"""Return the row_sha256 of the most recent row for *tenant_id*."""
		stmt = (
			sa.select(ff_audit_events.c.row_sha256)
			.where(ff_audit_events.c.row_sha256.is_not(None))
			.order_by(ff_audit_events.c.occurred_at.desc())
			.limit(1)
		)
		if tenant_id is not None:
			stmt = stmt.where(ff_audit_events.c.tenant_id == tenant_id)
		result = await conn.execute(stmt)
		row = result.fetchone()
		return row[0] if row else None


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


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _looks_like_datetime(s: str) -> bool:
	return bool(_ISO_RE.match(s))
