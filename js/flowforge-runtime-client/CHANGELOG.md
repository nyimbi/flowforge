# @flowforge/runtime-client changelog

## 0.1.0 (2026-05-06)

Initial release (U16).

### Added

- `FlowforgeClient` — typed REST client: `listDefs`, `getDef`, `validateDef`, `getCatalog`, `startInstance`, `sendEvent`, `getInstance`
- `FlowforgeWsClient` — WebSocket subscription with exponential-backoff reconnect and `WebSocketImpl` injection
- `useFlowforgeWorkflow` — React hook combining REST + WS for a single instance (React injected, no direct peer dep)
- `useTenantQueryKey` — host-pluggable React Query key builder
- `buildTenantQueryKey` — pure key builder utility
- Cookie auth (`credentials: "include"`) + double-submit-cookie CSRF (`X-CSRF-Token`)
- Idempotency-Key header on all writes
- Retry/backoff on network errors and 5xx responses
- Zod schemas for all API response shapes
- 23 vitest tests covering REST, WS, retry, CSRF, idempotency, and hook utilities
