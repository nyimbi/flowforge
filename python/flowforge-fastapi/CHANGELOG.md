# flowforge-fastapi changelog

## 0.1.0 — U02

- HTTP routers: designer (`/defs`, `/defs/validate`) and runtime
  (`/instances`, `/instances/{id}/events`, `/instances/{id}`).
- WebSocket fan-out hub (`ws.WorkflowEventsHub`) wired to runtime
  state changes; tests cover state-change push.
- `WorkflowDefRegistry` for in-memory definition lookup, plus a
  module-level singleton accessor (`get_registry`).
- Pluggable principal extraction (`StaticPrincipalExtractor`,
  `CookiePrincipalExtractor`) plus a CSRF dependency that compares a
  cookie token against the `X-CSRF-Token` header.
- `mount_routers(app, ...)` convenience that attaches all three
  routers under a single prefix.
- Tests use `httpx.ASGITransport`; no live network.
