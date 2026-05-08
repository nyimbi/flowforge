# flowforge-tenancy

Tenant resolver implementations for the flowforge framework — GUC-based single and multi-tenant, plus a no-op for single-org apps.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-tenancy
# or
pip install flowforge-tenancy
```

## What it does

`flowforge-tenancy` provides three concrete implementations of the `flowforge.ports.TenancyResolver` ABC. Each one handles a different deployment shape without changing any engine code.

`SingleTenantGUC` holds a fixed tenant id and issues `SELECT set_config('app.tenant_id', :v, true)` on every session it binds, activating PostgreSQL row-level security policies scoped to that tenant. `MultiTenantGUC` does the same but resolves the tenant id at call time via a sync or async callable — useful when a request carries a JWT or a header that identifies the tenant. `NoTenancy` is a no-op for single-organisation apps that have no isolation requirement.

All three implementations carry an `elevated_scope()` async context manager that sets `app.elevated = 'true'` on the GUC for the duration of the block. This is the mechanism for admin operations that need to read across all tenant rows. Elevation state is tracked in a per-instance `ContextVar`, so concurrent async tasks in the same process see their own scope independently.

## Quick start

```python
from flowforge import config
from flowforge_tenancy import MultiTenantGUC, SingleTenantGUC, NoTenancy

# Multi-tenant SaaS: resolve tenant from request context.
config.tenancy = MultiTenantGUC(resolver=lambda: get_current_request_tenant_id())

# Single-tenant deployment with a fixed id.
# config.tenancy = SingleTenantGUC(tenant_id="acme")

# No isolation required.
# config.tenancy = NoTenancy()

# Elevate for an admin operation that needs cross-tenant reads.
async with config.tenancy.elevated_scope():
	rows = await admin_query(session)
```

## Public API

- `SingleTenantGUC(tenant_id)` — fixed tenant; issues `set_config` GUC calls on each `bind_session`.
- `MultiTenantGUC(resolver)` — per-call resolver (sync or async callable returning a non-empty `str`).
- `NoTenancy()` — no-op; `current_tenant()` returns `"default"`, `bind_session` does nothing.
- All three expose:
  - `async current_tenant() -> str` — return the active tenant id.
  - `async bind_session(session, tenant_id) -> None` — issue GUC calls; must be inside a transaction.
  - `async elevated_scope() -> AsyncContextManager` — toggle `app.elevated = 'true'` for the block.

## Configuration

No environment variables. Pass a `resolver` callable to `MultiTenantGUC` that returns the tenant id for the current async context (e.g. from a `ContextVar` set by middleware, or from a request-scoped dependency).

The GUC names (`app.tenant_id`, `app.elevated`) are validated against `^[a-zA-Z_][a-zA-Z_0-9.]*$` before any SQL is issued. Both name and value are bound as parameters — no string interpolation reaches the SQL constant.

## Audit-2026 hardening

- **E-36 (T-01)** — `_set_config()` validates the GUC key against a regex whitelist and binds both key and value as named parameters into the constant SQL `SELECT set_config(:k, :v, true)`. String interpolation into SQL is structurally impossible.
- **E-36 (T-02)** — `_elevated` is a per-instance `ContextVar` (not a plain attribute). Concurrent `elevated_scope()` calls in separate async tasks each see their own elevation flag; one task's elevation cannot leak to another.
- **E-36 (T-03)** — `bind_session()` asserts `session.in_transaction()` before issuing any GUC call. Without an enclosing transaction `set_config(..., true)` would not scope to the request; the assertion prevents silent GUC leaks.

## Compatibility

- Python 3.11+
- Pydantic v2
- SQLAlchemy 2.x (async) for the GUC impls; `NoTenancy` has no SQLAlchemy dependency
- `flowforge` (core)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core) — ports, DSL, two-phase fire engine
- [`flowforge-sqlalchemy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-sqlalchemy) — `PgRlsBinder` that pairs with these resolvers
- [`flowforge-fastapi`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-fastapi) — HTTP adapter that wires a `TenancyResolver` per request
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md) for the security hardening rationale
