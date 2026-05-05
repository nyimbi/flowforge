# flowforge-sqlalchemy

Async SQLAlchemy 2.x storage adapter for the flowforge engine.

This package wires the engine's snapshot store, saga ledger, signal
correlator, and RLS binder onto durable Postgres (or SQLite, for tests
and replay) tables. The engine itself stays storage-agnostic; this
adapter is what hosts plug in at startup.

## What you get

- **ORM models** for the ten engine-managed tables:
  `workflow_definitions`, `workflow_definition_versions`,
  `workflow_instances`, `workflow_instance_tokens`, `workflow_events`,
  `workflow_saga_steps`, `workflow_instance_quarantine`,
  `business_calendars`, `pending_signals`,
  `workflow_instance_snapshots`.
- **`SqlAlchemySnapshotStore`** — implements
  `flowforge.engine.snapshots.SnapshotStore` against
  `workflow_instance_snapshots`.
- **`SagaQueries`** — read/write helpers over `workflow_saga_steps`,
  including LIFO compensation iteration.
- **`PgRlsBinder`** — implements `flowforge.ports.rls.RlsBinder`. Issues
  `set_config('app.tenant_id', ...)` and `set_config('app.elevated', ...)`
  on PostgreSQL; no-op on SQLite.
- **Alembic bundle** (`r1_initial`) — creates every table with a
  dialect-aware `JSONB`/`JSON` column type. Hosts include
  `flowforge_sqlalchemy.alembic_bundle.VERSIONS_DIR` in their
  `version_locations`.

## Install

```bash
uv add flowforge-sqlalchemy
# or with the test extras:
uv add 'flowforge-sqlalchemy[test]'
```

For PostgreSQL drivers + testcontainers (optional):

```bash
uv add 'flowforge-sqlalchemy[postgres]'
```

## Wiring example

```python
from flowforge import config
from flowforge_sqlalchemy import (
    PgRlsBinder, SagaQueries, SqlAlchemySnapshotStore,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine("postgresql+asyncpg://...", future=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

config.rls = PgRlsBinder()
snapshot_store = SqlAlchemySnapshotStore(session_factory, tenant_id="acme")
saga = SagaQueries(session_factory, tenant_id="acme")
```

The engine's `fire()` reads/writes the snapshot store you wire here;
nothing else in `flowforge-core` changes.

## Alembic

To run the bundled migration from a host repo:

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

Then:

```bash
alembic upgrade r1_initial
```

The migration is dialect-aware. SQLite drops back to generic `JSON`
storage automatically.

## Testing

The default test suite uses `aiosqlite`:

```bash
uv run --package flowforge-sqlalchemy pytest -vxs tests/
```

To exercise the migration against PostgreSQL via testcontainers:

```bash
export FLOWFORGE_TEST_PG_URL="postgresql://flowforge:flowforge@localhost:55432/flowforge"
uv run --package flowforge-sqlalchemy pytest -vxs tests/
```

## Versioning

Schema changes go through Alembic. The package follows the framework
versioning policy in `docs/workflow-framework-portability.md` §9.1 — any
breaking model change implies a major version bump.
