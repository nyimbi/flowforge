# flowforge-fastapi

FastAPI HTTP and WebSocket adapter for the flowforge workflow engine.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-fastapi
# or
pip install flowforge-fastapi
```

## What it does

`flowforge-fastapi` mounts three routers onto an existing `FastAPI` application: a designer router for reading and validating workflow definitions, a runtime router for creating instances and firing events, and a WebSocket router for pushing state changes to subscribed clients. One `mount_routers()` call wires all three under a shared path prefix.

The adapter owns transport concerns only — request parsing, CSRF protection, cookie-based auth, principal extraction, and WebSocket fan-out. All workflow state goes through `flowforge.config` ports. The adapter holds no globals beyond the per-app `WorkflowEventsHub` attached to `app.state`.

Auth is pluggable: implement the `PrincipalExtractor` protocol (an `async __call__(Request) -> Principal`) and pass it to `mount_routers`. Two implementations ship out of the box — `StaticPrincipalExtractor` for tests, and `CookiePrincipalExtractor` for signed-cookie sessions with `iat`/`exp` expiry enforcement.

## Quick start

```python
from fastapi import FastAPI
from flowforge import config
from flowforge_fastapi import mount_routers, StaticPrincipalExtractor, get_registry
from flowforge.ports.types import Principal

config.reset_to_fakes()

app = FastAPI()
mount_routers(
	app,
	prefix="/api/v1/workflows",
	principal_extractor=StaticPrincipalExtractor(
		Principal(user_id="alice", roles=("staff",))
	),
	require_csrf=False,
)

# Register a WorkflowDef so the runtime router can resolve def_key lookups.
# get_registry().register(my_workflow_def)
```

Then drive it from a client:

```text
POST /api/v1/workflows/instances           {"def_key": "claim", ...}
POST /api/v1/workflows/instances/{id}/events  {"event": "submit", ...}
GET  /api/v1/workflows/instances/{id}
WS   /api/v1/workflows/ws
```

Tests use `httpx.ASGITransport` — no live server is started.

## Public API

- `mount_routers(app, *, prefix, principal_extractor, tags, require_csrf)` — attach all three routers to a `FastAPI` app; creates a per-app `WorkflowEventsHub`.
- `build_designer_router(...)` — returns just the designer router if you need finer control over mounting.
- `build_runtime_router(...)` — returns just the runtime router.
- `build_ws_router(...)` — returns just the WebSocket router.
- `WorkflowDefRegistry` — in-memory definition store keyed by `def_key`.
- `get_registry()` — module-level singleton accessor for `WorkflowDefRegistry`.
- `InstanceStore` — engine snapshot store with an instance/def index for `GET /instances/{id}`.
- `get_instance_store()` — module-level singleton accessor for `InstanceStore`.
- `WorkflowEventsHub` — pub/sub hub for WebSocket fan-out; one per `FastAPI` app.
- `get_events_hub()` — FastAPI dependency; overridden per-app by `mount_routers`.
- `PrincipalExtractor` — protocol: `async __call__(Request) -> Principal`.
- `WSPrincipalExtractor` — protocol: `async __call__(WebSocket) -> Principal` (FA-03).
- `StaticPrincipalExtractor(principal)` — always returns the same `Principal`; for tests and demos.
- `CookiePrincipalExtractor(*, secret, cookie_name, ttl_seconds)` — signed-cookie auth with `iat`/`exp`.
- `csrf_protect` — FastAPI dependency; compares cookie token against `X-CSRF-Token` header.
- `issue_csrf_token(response, *, secure, dev_mode)` — set the CSRF cookie; defaults `secure=True`.
- `csrf_cookie_name` / `csrf_header_name` — string constants for the cookie and header names.
- `ConfigError` — raised when a config shape is unsafe (e.g. `secure=False` outside `dev_mode`).
- `reset_state()` — clear registry and instance store; call between tests.

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `prefix` | `""` | Common path prefix for all three routers. |
| `require_csrf` | `False` | Enforce double-submit CSRF on mutating runtime endpoints. |
| `CookiePrincipalExtractor.ttl_seconds` | `86400` | Cookie lifetime before `exp` rejection (24 h). |

No environment variables are required. The adapter reads only from `flowforge.config`.

## Audit-2026 hardening

- **E-41 (FA-01)** — `CookiePrincipalExtractor.verify` canonicalises base64 padding before HMAC recomputation; re-padded cookies from upstream proxies still verify.
- **E-41 (FA-02)** — `issue_csrf_token` defaults `secure=True`; `secure=False` without `dev_mode=True` raises `ConfigError`.
- **E-41 (FA-03)** — `WSPrincipalExtractor` takes `WebSocket` directly; the legacy scope-mutation trampoline (`scope['type'] = 'http'`) is gone.
- **E-41 (FA-04)** — `WorkflowEventsHub` is per-app; each `mount_routers` call binds a fresh hub to `app.state`, preventing cross-app subscriber leaks in a single process.
- **E-41 (FA-05)** — `engine_fire` and `store.put` run as one unit of work; a `put` failure restores the pre-fire snapshot so retries start clean.
- **E-41 (FA-06)** — `CookiePrincipalExtractor` embeds `iat`/`exp` in the cookie payload; expired cookies are rejected with 401.

## Compatibility

- Python 3.11+
- Pydantic v2
- FastAPI 0.100+
- `flowforge` (core)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core) — ports, DSL, two-phase fire engine
- [`flowforge-sqlalchemy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-sqlalchemy) — durable Postgres/SQLite storage adapter
- [`flowforge-tenancy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-tenancy) — tenant resolver implementations
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md) for the security hardening rationale
