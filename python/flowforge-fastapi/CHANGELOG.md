# flowforge-fastapi changelog

## Unreleased

- **[SECURITY] (audit-2026 E-41, P1/P2)** FastAPI + WS hardening (FA-01..FA-06).
  - **FA-01.** `CookiePrincipalExtractor` verify canonicalises base64
    padding before recomputing the HMAC.  Cookies whose body or signature
    were re-padded with trailing `=` by an upstream proxy now verify.
  - **FA-02.** `issue_csrf_token` defaults `secure=True`.  Passing
    `secure=False` raises the new `flowforge_fastapi.ConfigError` unless
    the caller also passes `dev_mode=True` so insecure cookie shapes
    cannot silently slip into a TLS-terminated host.
  - **FA-03.** New `WSPrincipalExtractor` protocol takes the
    `WebSocket` directly; `build_ws_router(ws_principal_extractor=…)`
    routes through it without mutating the WS scope.  The legacy
    "spoof scope['type']='http'" trampoline is gone.  When a host
    supplies the HTTP-side `principal_extractor=` only, the framework
    wraps it in `_HTTPOnlyAdapter` which builds a fresh faux Request
    from a defensive copy of the WS scope without ever mutating the
    original socket.
  - **FA-04.** `WorkflowEventsHub` is now request-scoped at the app
    level: each `mount_routers` call attaches a fresh hub to
    `app.state.flowforge_events_hub` and overrides the
    `get_events_hub` dependency for that app.  Two FastAPI apps in
    the same process never share subscribers; cross-test leak is
    structurally impossible.
  - **FA-05.** `engine_fire(...)` + `store.put(instance)` are now one
    unit of work via the new `_fire_with_unit_of_work` helper.  If
    `store.put` raises, the in-memory `Instance` is restored to its
    pre-fire snapshot (deep copy) so retries start clean.
  - **FA-06.** `CookiePrincipalExtractor` now embeds `iat` (issued-at)
    and `exp` (expiration, 24 h default; configurable via
    `ttl_seconds=`) in the cookie payload.  Verify rejects expired
    cookies with 401.  Pre-FA-06 cookies (no `exp`) remain valid —
    the field is opt-in additive, not breaking validation.

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
