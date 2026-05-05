# flowforge-fastapi

FastAPI adapter for [flowforge](../flowforge-core/). Wraps the engine,
designer, and runtime ports behind small HTTP and WebSocket routers so a
host application can mount workflows with one `include_router` call.

The adapter is intentionally thin: it owns transport concerns (request
parsing, CSRF, cookie auth, principal extraction, broadcast pumps) and
delegates all state to `flowforge.config` ports. No DB, no globals
beyond `flowforge.config`.

## What you get

- `mount_routers(app, ...)` — one call to attach designer + runtime + WS.
- `router_designer` — `GET /defs`, `POST /defs/validate`, catalog read.
- `router_runtime` — `POST /instances`, `POST /instances/{id}/events`,
  `GET /instances/{id}`.
- `ws.WorkflowEventsHub` + `router_ws` — WebSocket fan-out of state
  changes to subscribed clients.
- `auth` — cookie/CSRF helpers and a pluggable `PrincipalExtractor`
  that turns a request into a `flowforge.ports.types.Principal`.

The adapter never touches a database directly; tests run against the
in-memory port fakes that ship with `flowforge.testing.port_fakes`.

## Quick start

```python
from fastapi import FastAPI
from flowforge import config
from flowforge_fastapi import mount_routers, StaticPrincipalExtractor
from flowforge.ports.types import Principal

config.reset_to_fakes()
app = FastAPI()
mount_routers(
	app,
	prefix="/api/v1/workflows",
	principal_extractor=StaticPrincipalExtractor(
		Principal(user_id="alice", roles=("staff",))
	),
)
```

You can register `WorkflowDef` instances on the runtime registry:

```python
from flowforge_fastapi import get_registry

get_registry().register(my_workflow_def)
```

Then drive it from a client:

```text
POST /api/v1/workflows/instances        {"def_key": "claim_intake", ...}
POST /api/v1/workflows/instances/{id}/events  {"event": "submit", ...}
GET  /api/v1/workflows/instances/{id}
WS   /api/v1/workflows/ws
```

## Auth model

Two helpers ship out of the box:

- `StaticPrincipalExtractor(Principal(...))` — for tests / demos.
- `CookiePrincipalExtractor(secret=..., cookie_name=...)` — reads a signed
  cookie and (optionally) enforces a CSRF token via the
  `csrf_protect` dependency.

Hosts plug their own extractor by implementing `PrincipalExtractor`
(an `async __call__(request) -> Principal`) — for example, your UMS app
can return whatever your existing session middleware already attached.

## Testing

`pytest` with `httpx.ASGITransport`. No real server is started; the
ASGI app is invoked in-process.

```bash
uv run pytest framework/python/flowforge-fastapi/tests
```

## Status

`0.1.0` — first cut, in-process testing only. See
`docs/workflow-framework-portability.md` §3.1 and the U02 plan for
acceptance criteria.
