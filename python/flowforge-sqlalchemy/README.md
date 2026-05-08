# flowforge-sqlalchemy

Async SQLAlchemy 2.x storage adapter for the flowforge engine — snapshot store, saga ledger, RLS binder, and Alembic migration bundle.

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

Ten ORM models cover every engine-managed table. `SqlAlchemySnapshotStore` persists one snapshot row per workflow instance, updating it in-place on each fire. `SagaQueries` provides append, list, and mark operations over the saga ledger with LIFO ordering for compensation. `PgRlsBinder` issues `SELECT set_config(:k, :v, true)` GUC calls to activate row-level security policies without any SQL string interpolation.

The bundled Alembic migration (`r1_initial`) creates all ten tables in a single up/downgrade pair. Column types are dialect-aware: `JSONB` on PostgreSQL, plain `JSON` on SQLite. Hosts include the bundle's `VERSIONS_DIR` alongside their own Alembic versions directory.

## Quick start

```python
from flowforge import config
from flowforge_sqlalchemy import (
	PgRlsBinder,
	SagaQueries,
	SqlAlchemySnapshotStore,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/mydb", future=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

config.rls = PgRlsBinder()
snapshot_store = SqlAlchemySnapshotStore(session_factory, tenant_id="acme")
saga = SagaQueries(session_factory, tenant_id="acme")

# snapshot_store and saga are passed to the engine wherever SnapshotStore
# and SagaQueriesProtocol are expected.
```

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

- `SqlAlchemySnapshotStore(session_factory, *, tenant_id)` — async `SnapshotStore`; `get(instance_id)` / `put(instance)` over `workflow_instance_snapshots`.
- `SagaQueries(session_factory, *, tenant_id)` — `append(instance_id, *, kind, args, status)`, `list_for_instance(instance_id)`, `mark(instance_id, idx, status)`, `list_pending_for_compensation(instance_id)`.
- `PgRlsBinder()` — `RlsBinder` implementation; issues GUC calls per session inside a transaction; no-op on SQLite.
- `Base` — SQLAlchemy declarative base shared by all ORM models.
- `metadata` — `MetaData` instance; pass to Alembic `target_metadata`.
- ORM models (all in `flowforge_sqlalchemy.models`): `WorkflowDefinition`, `WorkflowDefinitionVersion`, `WorkflowInstance`, `WorkflowInstanceToken`, `WorkflowEvent`, `WorkflowSagaStep`, `WorkflowInstanceQuarantine`, `BusinessCalendar`, `PendingSignal`, `WorkflowInstanceSnapshot`.
- `flowforge_sqlalchemy.alembic_bundle.VERSIONS_DIR` — path to the bundled Alembic versions directory.

## Configuration

| Env var | Description |
|---|---|
| `FLOWFORGE_TEST_PG_URL` | When set, the test suite runs the full migration against a live PostgreSQL instance (e.g. via testcontainers). Default tests use aiosqlite. |

No env vars are required in production; pass the engine URL directly to `create_async_engine`.

## Audit-2026 hardening

- **E-39 (SA-01)** — `SqlAlchemySnapshotStore.put` assigns snapshot row ids via `uuid7str()`, producing time-ordered UUIDs that pair well with the B-tree index on `(tenant_id, instance_id)`.
- **E-40 (SA-02)** — `SagaQueries.list_pending_for_compensation` returns rows in LIFO order (`idx DESC`) matching the engine's compensation semantics; `mark` validates status against the allowed set before any SQL is emitted.

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
