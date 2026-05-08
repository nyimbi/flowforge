# flowforge-audit-pg

PostgreSQL-backed audit sink with a sha256 hash chain for tamper detection.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-audit-pg
# Postgres async driver:
uv pip install "flowforge-audit-pg[postgres]"
```

## What it does

Records `AuditEvent` objects into an append-only `ff_audit_events` table. Each row stores `prev_sha256` (the previous row's hash) and `row_sha256 = sha256((prev_sha256 or "") + canonical_json(row_data))`. The canonical JSON uses sorted keys, no whitespace, ISO-8601 datetimes, and UUIDs as strings — byte-stable across Python runtimes. Any row modified outside the API breaks the chain, which `verify_chain()` detects.

On PostgreSQL a DDL trigger blocks `DELETE` entirely. Concurrent inserts for the same tenant are serialised via `pg_advisory_xact_lock(hashtext(tenant_id))` plus a `UNIQUE(tenant_id, ordinal)` constraint, so the per-tenant chain never forks. On SQLite (used in CI) the same logic runs with an in-process `asyncio.Lock` instead of the advisory lock.

GDPR redaction replaces payload fields with `"__REDACTED__"` and records the reason in `payload["__redaction_reason__"]`. The `prev_sha256` / `row_sha256` columns are left intact, so `verify_chain()` flags redacted rows — auditors cross-reference the redaction log against the chain break.

## Quick start

```python
from sqlalchemy.ext.asyncio import create_async_engine
from flowforge_audit_pg import PgAuditSink, create_tables
from flowforge.ports.types import AuditEvent

engine = create_async_engine("postgresql+asyncpg://user:pw@localhost/mydb")

async def main():
	async with engine.begin() as conn:
		await create_tables(conn)   # table + DELETE-blocking trigger

	sink = PgAuditSink(engine)

	event_id = await sink.record(AuditEvent(
		kind="workflow.started",
		subject_kind="workflow",
		subject_id="wf-123",
		tenant_id="tenant-a",
		actor_user_id="user-42",
		payload={"step": "initial"},
	))

	verdict = await sink.verify_chain()
	assert verdict.ok

	# GDPR path: tombstone fields, preserve chain columns
	count = await sink.redact(
		["payload.name", "payload.email"],
		reason="erasure request #7",
	)
```

## Public API

- `PgAuditSink(engine)` — main sink; implements the flowforge `AuditSink` protocol
- `create_tables(conn)` — creates `ff_audit_events` and installs the DELETE trigger (PG) or noop guard (SQLite)
- `ff_audit_events` — SQLAlchemy `Table` object for use in Alembic migrations
- `AuditRow` — dataclass representing one database row (used by `verify_chain_in_memory`)
- `canonical_json(data)` — deterministic JSON serialiser; byte-stable across releases
- `compute_row_sha(prev_sha, row_data)` — compute one chain link
- `redact_payload(payload, paths)` — apply `TOMBSTONE` markers to dotted paths
- `verify_chain_in_memory(rows)` — offline chain check on a pre-fetched list of `AuditRow`
- `TOMBSTONE` — the sentinel string `"__REDACTED__"`

## Configuration

| Name | Default | Notes |
|---|---|---|
| `VERIFY_CHUNK_SIZE` | `10_000` | Module-level tunable; override in tests to exercise chunk boundaries |
| `DATABASE_URL` | — | Passed to `create_async_engine`; prefix `postgresql+asyncpg://` for PG, `sqlite+aiosqlite://` for SQLite |

## Audit-2026 hardening

- **AU-01** (E-37): per-tenant serialisation via `pg_advisory_xact_lock` on PG and `asyncio.Lock` on SQLite; `UNIQUE(tenant_id, ordinal)` constraint catches regressions at the schema layer
- **AU-02** (E-37): `verify_chain()` streams rows in `VERIFY_CHUNK_SIZE` batches via keyset pagination on `(occurred_at, event_id)`; peak memory is bounded by chunk size, not row count
- **AU-03** (E-37): canonical golden-bytes fixture in `framework/tests/audit_2026/fixtures/canonical_golden.bin`; the `_golden` module regenerates or verifies it — drift in `canonical_json` is a SOX/HIPAA P1 regression
- **AU-04** (E-60): `_looks_like_datetime` uses `datetime.fromisoformat` rather than a regex, so UUID-shaped event IDs that happen to start with `YYYY-MM-DD` are not silently treated as timestamps

## Compatibility

- Python 3.11+
- `sqlalchemy[asyncio]` >= 2.0
- `asyncpg` (optional, Postgres); `aiosqlite` (optional, SQLite / tests)
- `uuid6` (optional; falls back to `uuid4`)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge-core`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-outbox-pg`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-outbox-pg)
- [`flowforge-sqlalchemy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-sqlalchemy)
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
