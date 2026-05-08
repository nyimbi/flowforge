# flowforge

Pure-Python core of the flowforge workflow framework — ports, DSL, expression evaluator, two-phase fire engine, and in-memory test fakes.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge
# or
pip install flowforge
```

## What it does

`flowforge` is the I/O-free kernel of the framework. It defines 14 port ABCs (`tenancy`, `rbac`, `audit`, `outbox`, `documents`, `money`, `settings`, `signing`, `notification`, `rls`, `entity_registry`, `metrics`, `tasks`, `grants`) that host applications wire to their own infrastructure. The core never imports a database driver, web framework, or cloud SDK — those all live in separate adapter packages.

The DSL layer (`flowforge.dsl`) gives you Pydantic v2 models for `WorkflowDef`, `FormSpec`, and the JTBD bundle schema, plus JSON schemas for cross-runtime validation. The compiler (`flowforge.compiler`) validates a `WorkflowDef` at load time: unreachable states, dead-end transitions, duplicate priorities, subworkflow cycles.

The engine (`flowforge.engine`) runs the two-phase fire loop: Phase 1 evaluates guards (via the whitelisted `flowforge.expr` evaluator — no `eval`, no arbitrary Python) and picks a transition; Phase 2 commits effects, appends saga steps, dispatches outbox envelopes, and records audit events. After the audit-2026 sprint the engine serialises concurrent fires per instance and rolls back the snapshot on any dispatch failure.

## Quick start

```python
from flowforge import config
from flowforge.dsl import WorkflowDef, State, Transition, Effect
from flowforge.engine import fire, new_instance

# Wire in-memory fakes — sufficient for tests and local dev.
config.reset_to_fakes()

# Define a minimal two-state workflow.
wf = WorkflowDef(
	key="claim",
	version="1",
	initial_state="draft",
	states=[
		State(id="draft", kind="manual_review", label="Draft"),
		State(id="submitted", kind="terminal_success", label="Submitted"),
	],
	transitions=[
		Transition(
			id="t1",
			from_state="draft",
			to_state="submitted",
			on_event="submit",
			priority=0,
			effects=[Effect(kind="notify", target="ops", template="claim_submitted")],
		)
	],
)

instance = new_instance(wf)
result = await fire(instance, event="submit", payload={}, wf=wf)
print(result.new_state)  # "submitted"
```

## Public API

- `flowforge.config` — mutable global port registry; wire adapters here at startup.
- `flowforge.config.reset_to_fakes()` — reinitialise every port to its in-memory fake; call this in test fixtures.
- `flowforge.engine.fire(instance, event, payload, wf)` — two-phase fire; returns `FireResult`.
- `flowforge.engine.new_instance(wf)` — create a fresh `Instance` from a `WorkflowDef`.
- `flowforge.engine.Instance` — dataclass holding state, context, saga, history for one running workflow.
- `flowforge.engine.FireResult` — result of a fire call (new_state, effects applied, outbox envelopes).
- `flowforge.engine.InMemorySnapshotStore` — copy-on-read in-memory snapshot store; default for tests.
- `flowforge.engine.SagaLedger` / `SagaStep` / `CompensationWorker` — saga primitives.
- `flowforge.engine.SignalCorrelator` — correlate external signals to waiting instances.
- `flowforge.engine.ConcurrentFireRejected` — raised when a second fire arrives while one is in flight (C-04).
- `flowforge.dsl.WorkflowDef` / `State` / `Transition` / `Effect` / `Guard` — DSL models.
- `flowforge.expr.evaluate(expr, context)` — whitelisted expression evaluator (25+ operators, no `eval`).
- `flowforge.compiler.validate(wf)` — static validator; returns a list of `ValidationError`.
- `flowforge.replay` — deterministic event replay and simulator.
- `flowforge.testing.port_fakes` — `InMemoryAuditSink`, `InMemoryOutbox`, `InMemoryRbac`, `InMemoryTenancy`, and all other in-memory port implementations.

## Configuration

All tunables live directly on `flowforge.config`:

| Name | Default | Description |
|---|---|---|
| `snapshot_interval` | `100` | Fire cycles between full snapshots. |
| `max_nesting_depth` | `5` | Maximum sub-workflow nesting depth. |
| `lookup_rate_limit_per_minute` | `600` | Entity-catalog lookup rate cap. |

Port attributes (`config.tenancy`, `config.rbac`, etc.) default to `None`; call `reset_to_fakes()` or assign adapter instances before running the engine.

## Audit-2026 hardening

- **E-32 (C-01, C-04)** — Engine `fire()` is per-instance serialised; concurrent fires raise `ConcurrentFireRejected`. Outbox or audit failure restores the pre-fire snapshot.
- **E-35 (C-06, C-07)** — Expression operator registry frozen at module-init; post-startup `register_op()` raises `RegistryFrozenError`. Arity is validated at compile time and at runtime.
- **E-39 (C-02, C-03, C-05, C-08, C-10, C-13, SA-01)** — Engine cleanup: guard evaluation errors surface as `GuardEvaluationError` instead of silently returning `False`; snapshot store switched to copy-on-read.
- **E-40 (C-09, SA-02)** — Saga ledger durable persistence path wired; compensation queries covered.
- **E-61 (C-11, C-12)** — DSL hygiene: `Guard.expr` rejects multi-key dicts at parse time; `InMemorySnapshotStore` copy-on-read cuts snapshot latency by ~10x on large contexts.

## Compatibility

- Python 3.11+
- Pydantic v2
- No I/O dependencies (SQLAlchemy, FastAPI, etc. are in separate adapter packages)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge-fastapi`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-fastapi) — HTTP/WebSocket routers for FastAPI hosts
- [`flowforge-sqlalchemy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-sqlalchemy) — durable Postgres/SQLite storage adapter
- [`flowforge-tenancy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-tenancy) — tenant resolver implementations
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md) for the security hardening rationale
