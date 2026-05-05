# flowforge-audit-pg

PostgreSQL-backed `AuditSink` adapter for the flowforge framework.

## What it does

- Stores audit events in an append-only `ff_audit_events` table.
- Maintains a **sha256 hash chain** (`prev_sha256` / `row_sha256`) so tampering is detectable.
- Installs a **DELETE-blocking trigger** on PostgreSQL (via `create_tables()`).
- Provides a **GDPR-aware redaction path** that tombstones sensitive payload fields while preserving the chain columns so operators can document what was redacted and why.
- Falls back to **SQLite** (via `aiosqlite`) for local dev and CI — same chain logic, no trigger.

## Installation

```
pip install flowforge-audit-pg
# For Postgres support:
pip install "flowforge-audit-pg[postgres]"
```

## Quick start

```python
from sqlalchemy.ext.asyncio import create_async_engine
from flowforge_audit_pg import PgAuditSink, create_tables
from flowforge.ports.types import AuditEvent

engine = create_async_engine("postgresql+asyncpg://user:pw@localhost/mydb")

async def setup():
    async with engine.begin() as conn:
        await create_tables(conn)   # creates table + installs trigger

sink = PgAuditSink(engine)

# Record an event
event_id = await sink.record(AuditEvent(
    kind="workflow.started",
    subject_kind="workflow",
    subject_id="wf-123",
    tenant_id="tenant-a",
    actor_user_id="user-42",
    payload={"step": "initial"},
))

# Verify the chain
verdict = await sink.verify_chain()
assert verdict.ok

# GDPR redaction
count = await sink.redact(["payload.name", "payload.email"], reason="erasure request #7")
```

## Hash chain algorithm

Each row stores:

```
row_sha256 = sha256( (prev_sha256 or "") + canonical_json(row_data) )
```

`canonical_json` encodes with sorted keys, no whitespace, ISO-8601 datetimes, UUIDs as strings — byte-stable across Python runtimes.

## GDPR redaction

`redact(paths, reason)` replaces matching JSON paths with `"__REDACTED__"` and writes the reason into `payload["__redaction_reason__"]`. The `prev_sha256` / `row_sha256` columns are left intact, so `verify_chain()` will flag redacted rows — this is intentional: auditors cross-reference the redaction log against chain breaks.

## Running tests

```
pip install -e ".[test]"
pytest
# Against Postgres (optional):
DATABASE_URL=postgresql+asyncpg://... pytest
```
