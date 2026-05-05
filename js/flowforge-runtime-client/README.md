# @flowforge/runtime-client

Typed REST and WebSocket client for the `flowforge-fastapi` backend.

## Features

- `FlowforgeClient` — typed REST client covering all runtime and designer endpoints
- `FlowforgeWsClient` — WebSocket subscription client with exponential-backoff reconnect
- `useFlowforgeWorkflow` — React hook (React-injected, no direct peer dep at build time)
- `useTenantQueryKey` — host-pluggable React Query key builder
- Cookie auth with double-submit-cookie CSRF (`X-CSRF-Token`)
- Idempotency-Key on all mutating requests
- Retry with exponential backoff + jitter on transient failures

## Quick start

```ts
import { FlowforgeClient, FlowforgeWsClient } from "@flowforge/runtime-client";

const client = new FlowforgeClient({ baseUrl: "http://localhost:8000" });

// List workflow definitions
const defs = await client.listDefs();

// Create an instance
const instance = await client.startInstance(
  { def_key: "claim-intake", tenant_id: "acme" },
  crypto.randomUUID(),
);

// Send an event
const result = await client.sendEvent(
  instance.id,
  { event: "submit", payload: { amount: 5000 } },
  crypto.randomUUID(),
);

// Subscribe to live updates
const ws = new FlowforgeWsClient({
  wsBaseUrl: "ws://localhost:8000",
  onConnect: (hello) => console.log("connected as", hello.user_id),
  onEvent: (envelope) => console.log("event", envelope),
});
ws.open();
```

## Auth model

Sends `credentials: "include"` on every request so the browser cookie jar carries the session cookie. Mutating requests also echo the `flowforge_csrf` cookie as `X-CSRF-Token` (double-submit-cookie). Override via the `getCsrfToken` option in tests or non-browser environments.

## Retry / backoff

`maxAttempts` (default 3) retries on network errors or 5xx. Delay: `baseDelayMs * 2^(attempt-1) + jitter`. 4xx errors are not retried.

## Testing

```bash
pnpm test
```

Tests use `msw` for HTTP mocking and `mock-socket` for WebSocket mocking via `WebSocketImpl` injection.
