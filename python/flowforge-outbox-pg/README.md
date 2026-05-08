# flowforge-outbox-pg

Transactional outbox drain worker for PostgreSQL (and SQLite in tests).

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-outbox-pg
```

## What it does

Implements the transactional outbox pattern: messages written to an `outbox` table in the same database transaction as business data are picked up by `DrainWorker` and dispatched to registered handlers. This decouples the act of persisting intent from the act of delivering it, so a crashed process never silently drops a message.

On PostgreSQL the worker claims rows with `FOR UPDATE SKIP LOCKED`, which lets multiple workers drain in parallel without coordination overhead. Each claimed row gets a short lease (`locked_until`). A worker that crashes without committing leaves rows with an expired `locked_until`; any other worker reclaims them on the next tick.

`HandlerRegistry` maps `(backend, kind)` pairs to async handler functions. Multiple messaging backends — `dramatiq`, `temporal`, `inline` — can coexist in one process without namespace collisions. A row with no registered handler moves immediately to `dead` rather than retrying.

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
	print(result.as_dict())
	# {'dispatched': 1, 'retried': 0, 'dead': 0, 'no_handler': 0}
```

For PostgreSQL pass an asyncpg connection and omit `sqlite_compat`:

```python
import asyncpg
conn = await asyncpg.connect(dsn)
worker = DrainWorker(conn, reg, table="ums.outbox")
```

Long-running loop with graceful stop:

```python
stop = asyncio.Event()
task = asyncio.create_task(
	worker.run_loop(poll_interval_seconds=1.0, stop_event=stop)
)
# ... later:
stop.set()
await task
```

## Public API

- `HandlerRegistry` — register handlers by `(backend, kind)`, dispatch envelopes
- `DrainWorker` — claim-and-drain loop with retry, DLQ, and reconnect support
- `OutboxRow` — dataclass for one outbox table row
- `OutboxStatus` — enum: `PENDING`, `IN_FLIGHT`, `DISPATCHED`, `DEAD`

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `batch_size` | `32` | Max rows claimed per `run_once` call |
| `max_retries` | `5` | Retry limit before DLQ transition |
| `dlq_after_seconds` | `3600` | Age limit before DLQ regardless of retry count |
| `lock_window_seconds` | `60` | In-flight lease duration |
| `table` | `"outbox"` | SQL table name; schema-qualified names accepted (`"ums.outbox"`) |
| `sqlite_compat` | `False` | Use SQLite-safe claim (tests only; rejects `pool_size > 1`) |
| `reconnect_factory` | `None` | Async callable returning a fresh connection on connection-loss |

Row lifecycle:

```
pending -> in_flight -> dispatched   (success)
pending -> in_flight -> pending      (retry, retries < max_retries)
pending -> in_flight -> dead         (max retries exceeded, or row too old, or no handler)
```

## Audit-2026 hardening

- **OB-01** (E-42): `table` is validated against `^[a-zA-Z_][a-zA-Z_0-9.]*$` at constructor time; injection payloads like `"x; DROP TABLE foo"` raise `ValueError` before reaching the database
- **OB-02** (E-42): `DrainWorker(sqlite_compat=True, pool_size>1)` raises `RuntimeError`; SQLite is single-writer and cannot serialise concurrent drain workers
- **OB-03** (E-42): `reconnect_factory` callback fires on connection-loss exceptions inside `run_loop`; the worker swaps in a fresh connection and resumes; `worker.reconnects` exposes the count for metrics
- **OB-04** (E-42): `last_error` is truncated to a UTF-8 byte budget, never mid-codepoint, before being written to the database column

## Compatibility

- Python 3.11+
- `asyncpg` (PostgreSQL production path)
- `aiosqlite` (SQLite test path)
- `uuid6` (optional; falls back to `uuid4`)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge-core`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-audit-pg`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-audit-pg)
- [`flowforge-sqlalchemy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-sqlalchemy)
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
