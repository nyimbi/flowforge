# flowforge-sqlalchemy

Async SQLAlchemy 2.x storage adapter for the flowforge engine — snapshot store, transactional fire commits, saga ledger, RLS binder, durable outbox table, and Alembic migration bundle.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-sqlalchemy
# or with test extras (aiosqlite):
uv pip install 'flowforge-sqlalchemy[test]'
# with PostgreSQL driver:
uv pip install 'flowforge-sqlalchemy[postgres]'
```

## What it does

`flowforge-sqlalchemy` provides the durable storage layer for the flowforge engine. The engine itself is storage-agnostic — it reads and writes through the `SnapshotStore` ABC and `SagaQueriesProtocol`. This package supplies concrete async SQLAlchemy 2.x implementations backed by PostgreSQL (production) or SQLite (tests and replay).

Eleven ORM models cover every engine-managed table. `SqlAlchemySnapshotStore` persists one snapshot row per workflow instance, updating it in-place on each fire. For critical paths, `SqlAlchemySnapshotStore.fire_and_commit(...)` calls the core engine with `dispatch_ports=False` and writes the workflow event, snapshot CAS update, instance row state, audit-chain rows, and pending outbox rows in one SQLAlchemy transaction. `SagaQueries` provides append, list, and mark operations over the saga ledger with LIFO ordering for compensation. `PgRlsBinder` issues `SELECT set_config(:k, :v, true)` GUC calls to activate row-level security policies without any SQL string interpolation.

The bundled Alembic migration (`r1_initial`) creates all eleven tables in a single up/downgrade pair. Column types are dialect-aware: `JSONB` on PostgreSQL, plain `JSON` on SQLite. Hosts include the bundle's `VERSIONS_DIR` alongside their own Alembic versions directory.

## Quick start

```python
from flowforge import config
from flowforge_audit_pg import PgAuditSink
from flowforge_sqlalchemy import (
	PgRlsBinder,
	SagaQueries,
	SqlAlchemySnapshotStore,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb", future=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

config.rls = PgRlsBinder()
snapshot_store = SqlAlchemySnapshotStore(
	session_factory,
	tenant_id="acme",
	audit_sink=PgAuditSink(engine),
)
saga = SagaQueries(session_factory, tenant_id="acme")

# FastAPI and other hosts should prefer snapshot_store.fire_and_commit(...)
# for critical fire paths so event log, snapshot, audit, and outbox enqueue
# commit or roll back together.
```

### SnapshotConflict retry policy

`SnapshotConflict` means another process committed a newer snapshot for the
same `(tenant_id, instance_id)` before this caller did. Treat it as an
optimistic-concurrency conflict, not as a transport failure.

Recommended host policy:

1. Require an idempotency key on externally initiated fire requests.
2. On `SnapshotConflict`, discard the stale in-memory `Instance`; do not call
   `compare_and_put(...)` or `fire_and_commit(...)` again with the same object.
3. Re-read the latest snapshot for the tenant/instance, re-run guard
   evaluation and `fire_and_commit(...)` from that fresh snapshot, and reuse the
   same idempotency key.
4. Keep the retry budget small, usually 2 or 3 attempts with jittered backoff.
5. If the retry budget is exhausted, surface an HTTP `409 Conflict` (or the
   host framework's equivalent) with a safe retry-after hint instead of hiding
   the conflict behind a generic `500`.

FastAPI hosts using `flowforge-fastapi` already prefer a store-level
`fire_and_commit(...)` method when present, so the store owns the transactional
boundary. Custom hosts should follow the same shape: reload after conflict,
retry the entire fire operation, and let idempotency collapse duplicated client
submissions.

### Alembic wiring

```python
# alembic/env.py
from flowforge_sqlalchemy import metadata as flowforge_metadata
from flowforge_sqlalchemy.alembic_bundle import VERSIONS_DIR

config.set_main_option(
	"version_locations",
	f"{config.get_main_option('script_location')}/versions {VERSIONS_DIR}",
)
target_metadata = [host_metadata, flowforge_metadata]
```

```bash
alembic upgrade r1_initial
```

## Public API

- `SqlAlchemySnapshotStore(session_factory, *, tenant_id, audit_sink=None)` — async `SnapshotStore`; `get(instance_id)` / `put(instance)` over `workflow_instance_snapshots`; `compare_and_put(instance, expected_seq=...)` for optimistic locking; `fire_and_commit(...)` for transactional event/snapshot/audit/outbox commits.
- `SagaQueries(session_factory, *, tenant_id)` — `append(instance_id, *, kind, args, status)`, `list_for_instance(instance_id)`, `mark(instance_id, idx, status)`, `list_pending_for_compensation(instance_id)`.
- `PgRlsBinder()` — `RlsBinder` implementation; issues GUC calls per session inside a transaction; no-op on SQLite.
- `Base` — SQLAlchemy declarative base shared by all ORM models.
- `metadata` — `MetaData` instance; pass to Alembic `target_metadata`.
- ORM models (all in `flowforge_sqlalchemy.models`): `WorkflowDefinition`, `WorkflowDefinitionVersion`, `WorkflowInstance`, `WorkflowInstanceToken`, `WorkflowEvent`, `WorkflowSagaStep`, `WorkflowInstanceQuarantine`, `BusinessCalendar`, `PendingSignal`, `WorkflowInstanceSnapshot`, `OutboxMessage`.
- `flowforge_sqlalchemy.alembic_bundle.VERSIONS_DIR` — path to the bundled Alembic versions directory.

## Configuration

| Env var | Description |
|---|---|
| `FLOWFORGE_TEST_PG_URL` | When set, the test suite runs the full migration against a live PostgreSQL instance (e.g. via testcontainers). Default tests use aiosqlite. |

No env vars are required in production; pass the engine URL directly to `create_async_engine`.

## Audit-2026 hardening

- **E-39 (SA-01)** — `SqlAlchemySnapshotStore.put` assigns snapshot row ids via `uuid7str()`, producing time-ordered UUIDs that pair well with the B-tree index on `(tenant_id, instance_id)`.
- **E-40 (SA-02)** — `SagaQueries.list_pending_for_compensation` returns rows in LIFO order (`idx DESC`) matching the engine's compensation semantics; `mark` validates status against the allowed set before any SQL is emitted.
- **Audit-2026 UoW** — `fire_and_commit(...)` is the critical-system path for SQLAlchemy hosts. Direct core `fire(..., dispatch_ports=True)` remains useful for tests and custom hosts, but it is not a durable all-or-nothing boundary unless those ports are transactional enqueue adapters.

## Compatibility

- Python 3.11+
- Pydantic v2
- SQLAlchemy 2.x (async)
- PostgreSQL 14+ (production) or SQLite (tests)
- `flowforge` (core)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core) — ports, DSL, two-phase fire engine
- [`flowforge-tenancy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-tenancy) — tenant resolver implementations that call `PgRlsBinder`
- [`flowforge-fastapi`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-fastapi) — HTTP/WebSocket adapter that uses this snapshot store
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md) for the security hardening rationale
