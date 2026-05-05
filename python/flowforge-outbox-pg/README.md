# flowforge-outbox-pg

Transactional outbox adapter for flowforge.

Provides two things: a handler registry and a drain worker. The registry maps
`(backend, kind)` pairs to async handler functions. The worker polls the
outbox table, claims rows atomically, calls handlers, and manages retries and
DLQ transitions.

## How it works

On PostgreSQL the worker issues:

```sql
UPDATE outbox
SET status = 'in_flight', locked_until = <now + lock_window>
WHERE id IN (
    SELECT id FROM outbox
    WHERE status = 'pending'
       OR (status = 'in_flight' AND locked_until < <now>)
    ORDER BY created_at ASC
    LIMIT <batch_size>
    FOR UPDATE SKIP LOCKED
)
RETURNING id, kind, tenant_id, body, retries, created_at
```

`FOR UPDATE SKIP LOCKED` lets multiple workers run in parallel without
stepping on each other. Each claimed row gets a short lease. A crashed
worker's rows are reclaimed when their `locked_until` expires.

## Table schema

```sql
CREATE TABLE outbox (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    tenant_id      TEXT NOT NULL DEFAULT '',
    body           TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL DEFAULT 'pending',
    retries        INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL,
    locked_until   TIMESTAMPTZ,
    last_error     TEXT,
    correlation_id TEXT,
    dedupe_key     TEXT
);
```

For SQLite (tests), `DrainWorker.setup()` creates an equivalent table in
`:memory:`.

## Lifecycle

```
pending -> in_flight -> dispatched   (success)
pending -> in_flight -> pending      (retry, retries < max_retries)
pending -> in_flight -> dead         (max retries exceeded or row too old)
pending -> in_flight -> dead         (no handler registered for kind)
```

## Quick start

```python
import aiosqlite
from flowforge.ports.types import OutboxEnvelope
from flowforge_outbox_pg import HandlerRegistry, DrainWorker

reg = HandlerRegistry()

@reg.handler("order.created")
async def handle_order(env: OutboxEnvelope) -> None:
    print("order created:", env.body)

async with aiosqlite.connect(":memory:") as conn:
    worker = DrainWorker(conn, reg, sqlite_compat=True)
    await worker.setup()

    env = OutboxEnvelope(kind="order.created", tenant_id="t1", body={"id": 42})
    await worker.enqueue(env)

    result = await worker.run_once()
    print(result.as_dict())  # {'dispatched': 1, 'retried': 0, 'dead': 0, 'no_handler': 0}
```

For PostgreSQL pass an asyncpg connection and omit `sqlite_compat`:

```python
import asyncpg
conn = await asyncpg.connect(dsn)
worker = DrainWorker(conn, reg, table="ums.outbox")
```

## Multi-backend

```python
reg.register("email.send", send_email, backend="email")
reg.register("sms.send",   send_sms,   backend="sms")

email_worker = DrainWorker(conn, reg, backend="email")
sms_worker   = DrainWorker(conn, reg, backend="sms")
```

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `batch_size` | 32 | Max rows per drain tick |
| `max_retries` | 5 | Retry limit before DLQ |
| `dlq_after_seconds` | 3600 | Age limit before DLQ |
| `lock_window_seconds` | 60 | In-flight lease duration |
| `table` | `"outbox"` | SQL table name |
| `sqlite_compat` | `False` | Use SQLite-safe claim (tests) |

## Testing

```
cd framework/python/flowforge-outbox-pg
uv run pytest -vxs
```

Tests run entirely against in-memory SQLite — no PostgreSQL required.
