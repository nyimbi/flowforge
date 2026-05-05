# flowforge

Core of the flowforge workflow framework. Pure Python; no I/O, no web, no DB.

## What's here

- `flowforge.ports` — 14 protocol ABCs that hosts wire to their own infrastructure (tenancy, RBAC, audit, outbox, documents, money, settings, signing, notification, RLS, entity catalog, metrics, tasks, grants).
- `flowforge.dsl` — Pydantic models + JSON schemas for `WorkflowDef` and `FormSpec`, plus the JTBD bundle schema.
- `flowforge.expr` — whitelisted expression evaluator (operators are pure functions; the runtime never executes arbitrary Python).
- `flowforge.compiler` — DSL validator and entity-catalog projection.
- `flowforge.engine` — two-phase fire (plan + commit), saga ledger, signal correlator, sub-workflow handle, timers, snapshots.
- `flowforge.replay` — deterministic event replay + simulator.
- `flowforge.testing` — in-memory port fakes and pytest fixtures hosts can import.

## Wiring

```python
from flowforge import config
from flowforge.testing.port_fakes import (
    InMemoryAuditSink, InMemoryOutbox, InMemoryRbac, InMemoryTenancy,
)

config.tenancy = InMemoryTenancy(tenant_id="t-1")
config.audit = InMemoryAuditSink()
config.outbox = InMemoryOutbox()
config.rbac = InMemoryRbac(grants={"alice": {"claim.create"}})
```

## Running tests

```sh
cd framework/python/flowforge-core
uv run pytest -vxs
```

See `docs/workflow-framework-portability.md` (root of UMS repo) for the full spec.
