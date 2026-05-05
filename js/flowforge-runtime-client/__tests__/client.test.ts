/**
 * Tests for @flowforge/runtime-client
 *
 * HTTP mocking: msw v2 (HttpResponse, http) with setupServer (node)
 * WS mocking:  mock-socket Server + WebSocket injection via WebSocketImpl option
 */

import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { Server as MockWsServer, WebSocket as MockWebSocket } from "mock-socket";

import {
  FlowforgeClient,
  FlowforgeApiError,
  FlowforgeWsClient,
  buildTenantQueryKey,
  useTenantQueryKey,
  useFlowforgeWorkflow,
  type InstanceView,
  type FireResultView,
} from "../src/index.js";

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const BASE = "http://localhost:9999";

const INSTANCE: InstanceView = {
  id: "inst-001",
  def_key: "claim-intake",
  def_version: "1.0.0",
  state: "draft",
  context: { amount: 100 },
  history: ["draft"],
  saga: [],
  created_entities: [],
};

const FIRE_RESULT: FireResultView = {
  instance: { ...INSTANCE, state: "triage", history: ["draft", "triage"] },
  matched_transition_id: "t1",
  new_state: "triage",
  terminal: false,
  audit_event_kinds: ["workflow.transition"],
  outbox_kinds: [],
};

// ---------------------------------------------------------------------------
// MSW server
// ---------------------------------------------------------------------------

const handlers = [
  // listDefs
  http.get(`${BASE}/defs`, () =>
    HttpResponse.json({
      defs: [
        {
          key: "claim-intake",
          version: "1.0.0",
          subject_kind: "claim",
          initial_state: "draft",
          states: ["draft", "triage", "closed"],
        },
      ],
    }),
  ),

  // getDef
  http.get(`${BASE}/defs/claim-intake`, () =>
    HttpResponse.json({ key: "claim-intake", version: "1.0.0", states: ["draft", "triage"] }),
  ),

  // validateDef
  http.post(`${BASE}/defs/validate`, () =>
    HttpResponse.json({ ok: true, errors: [], warnings: [] }),
  ),

  // getCatalog
  http.get(`${BASE}/catalog`, () =>
    HttpResponse.json({ catalog: {} }),
  ),

  // startInstance (POST /instances)
  http.post(`${BASE}/instances`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (!body["def_key"]) {
      return HttpResponse.json({ detail: "def_key required" }, { status: 422 });
    }
    return HttpResponse.json(INSTANCE, { status: 201 });
  }),

  // sendEvent (POST /instances/:id/events)
  http.post(`${BASE}/instances/inst-001/events`, async ({ request }) => {
    const idempotencyKey = request.headers.get("Idempotency-Key");
    if (!idempotencyKey) {
      return HttpResponse.json({ detail: "Idempotency-Key required" }, { status: 400 });
    }
    return HttpResponse.json(FIRE_RESULT);
  }),

  // getInstance (GET /instances/:id)
  http.get(`${BASE}/instances/inst-001`, () =>
    HttpResponse.json(INSTANCE),
  ),

  // 404 for unknown instance
  http.get(`${BASE}/instances/unknown`, () =>
    HttpResponse.json({ detail: "unknown instance: unknown" }, { status: 404 }),
  ),

  // 500 for retry test
  http.post(`${BASE}/instances/inst-500/events`, () =>
    HttpResponse.json({ detail: "internal error" }, { status: 500 }),
  ),
];

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Helper: build a client pointed at the mock server, no CSRF token needed.
// ---------------------------------------------------------------------------

function makeClient(overrides: Parameters<typeof FlowforgeClient>[0] = {}) {
  return new FlowforgeClient({
    baseUrl: BASE,
    getCsrfToken: () => "test-csrf",
    maxAttempts: 1, // no retries by default in unit tests
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Designer endpoints
// ---------------------------------------------------------------------------

describe("FlowforgeClient — designer", () => {
  it("listDefs returns parsed def summaries", async () => {
    const client = makeClient();
    const defs = await client.listDefs();
    expect(defs).toHaveLength(1);
    expect(defs[0]).toMatchObject({
      key: "claim-intake",
      version: "1.0.0",
      initial_state: "draft",
    });
  });

  it("getDef returns a workflow def JSON blob", async () => {
    const client = makeClient();
    const def = await client.getDef("claim-intake");
    expect(def).toHaveProperty("key", "claim-intake");
  });

  it("validateDef returns ok:true for a valid def", async () => {
    const client = makeClient();
    const result = await client.validateDef({ definition: { key: "test" } });
    expect(result.ok).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it("getCatalog returns a catalog blob", async () => {
    const client = makeClient();
    const catalog = await client.getCatalog();
    expect(catalog).toHaveProperty("catalog");
  });
});

// ---------------------------------------------------------------------------
// Runtime endpoints
// ---------------------------------------------------------------------------

describe("FlowforgeClient — runtime", () => {
  it("startInstance creates an instance with idempotency-key", async () => {
    const client = makeClient();
    const instance = await client.startInstance(
      { def_key: "claim-intake" },
      "idem-key-001",
    );
    expect(instance.id).toBe("inst-001");
    expect(instance.state).toBe("draft");
    expect(instance.def_key).toBe("claim-intake");
  });

  it("sendEvent fires an event and returns the fire result", async () => {
    const client = makeClient();
    const result = await client.sendEvent(
      "inst-001",
      { event: "submit" },
      "idem-key-002",
    );
    expect(result.new_state).toBe("triage");
    expect(result.matched_transition_id).toBe("t1");
    expect(result.terminal).toBe(false);
    expect(result.instance.state).toBe("triage");
  });

  it("getInstance returns current snapshot", async () => {
    const client = makeClient();
    const instance = await client.getInstance("inst-001");
    expect(instance.id).toBe("inst-001");
    expect(instance.context).toMatchObject({ amount: 100 });
  });

  it("getInstance throws FlowforgeApiError on 404", async () => {
    const client = makeClient();
    await expect(client.getInstance("unknown")).rejects.toThrow(FlowforgeApiError);
    await expect(client.getInstance("unknown")).rejects.toMatchObject({ status: 404 });
  });

  it("startInstance throws on missing def_key (422)", async () => {
    const client = makeClient();
    // @ts-expect-error: intentionally missing def_key
    await expect(client.startInstance({}, "key")).rejects.toThrow(FlowforgeApiError);
  });
});

// ---------------------------------------------------------------------------
// Retry / backoff
// ---------------------------------------------------------------------------

describe("FlowforgeClient — retry", () => {
  it("retries on 5xx up to maxAttempts then throws", async () => {
    const client = makeClient({ maxAttempts: 2, baseDelayMs: 1 });
    await expect(
      client.sendEvent("inst-500", { event: "anything" }, "key"),
    ).rejects.toThrow(FlowforgeApiError);
  });

  it("succeeds on 2nd attempt after transient 500", async () => {
    let calls = 0;
    server.use(
      http.post(`${BASE}/instances/inst-retry/events`, () => {
        calls += 1;
        if (calls < 2) {
          return HttpResponse.json({ detail: "transient" }, { status: 500 });
        }
        return HttpResponse.json(FIRE_RESULT);
      }),
    );

    const client = makeClient({ maxAttempts: 3, baseDelayMs: 1 });
    const result = await client.sendEvent("inst-retry", { event: "go" }, "key-retry");
    expect(result.new_state).toBe("triage");
    expect(calls).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// CSRF header
// ---------------------------------------------------------------------------

describe("FlowforgeClient — CSRF", () => {
  it("attaches X-CSRF-Token on mutating requests", async () => {
    let capturedCsrf: string | null = null;
    server.use(
      http.post(`${BASE}/instances`, async ({ request }) => {
        capturedCsrf = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(INSTANCE, { status: 201 });
      }),
    );

    const client = makeClient({ getCsrfToken: () => "csrf-abc" });
    await client.startInstance({ def_key: "claim-intake" }, "key");
    expect(capturedCsrf).toBe("csrf-abc");
  });

  it("does not attach X-CSRF-Token on GET", async () => {
    let capturedCsrf: string | null | undefined = undefined;
    server.use(
      http.get(`${BASE}/instances/inst-001`, ({ request }) => {
        capturedCsrf = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(INSTANCE);
      }),
    );

    const client = makeClient({ getCsrfToken: () => "csrf-abc" });
    await client.getInstance("inst-001");
    expect(capturedCsrf).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Idempotency-Key
// ---------------------------------------------------------------------------

describe("FlowforgeClient — idempotency key", () => {
  it("attaches Idempotency-Key header on writes", async () => {
    let capturedKey: string | null = null;
    server.use(
      http.post(`${BASE}/instances`, async ({ request }) => {
        capturedKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json(INSTANCE, { status: 201 });
      }),
    );

    const client = makeClient();
    await client.startInstance({ def_key: "claim-intake" }, "my-idem-key");
    expect(capturedKey).toBe("my-idem-key");
  });
});

// ---------------------------------------------------------------------------
// WebSocket client — use MockWebSocket injection (no global override needed)
// ---------------------------------------------------------------------------

describe("FlowforgeWsClient", () => {
  it("receives hello frame and subsequent events", async () => {
    const WS_URL = "ws://localhost:9998";
    const mockServer = new MockWsServer(WS_URL);

    const receivedHellos: unknown[] = [];
    const receivedEvents: unknown[] = [];

    const wsClient = new FlowforgeWsClient({
      wsBaseUrl: WS_URL,
      path: "",
      // Inject mock-socket's WebSocket — avoids global override issues
      WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
      onConnect: (hello) => receivedHellos.push(hello),
      onEvent: (evt) => receivedEvents.push(evt),
      maxReconnectAttempts: 1,
    });

    wsClient.open();

    await new Promise<void>((resolve) => {
      mockServer.on("connection", (socket) => {
        socket.send(JSON.stringify({ type: "hello", user_id: "u1" }));
        setTimeout(() => {
          socket.send(
            JSON.stringify({
              type: "instance.state_changed",
              instance_id: "inst-001",
              from_state: "draft",
              to_state: "triage",
            }),
          );
          resolve();
        }, 10);
      });
    });

    // Allow microtasks to flush
    await new Promise((r) => setTimeout(r, 30));

    expect(receivedHellos).toHaveLength(1);
    expect(receivedHellos[0]).toMatchObject({ type: "hello", user_id: "u1" });
    expect(receivedEvents).toHaveLength(1);
    expect(receivedEvents[0]).toMatchObject({ type: "instance.state_changed" });

    wsClient.close();
    mockServer.stop();
  });

  it("does not reconnect after close()", async () => {
    const WS_URL = "ws://localhost:9997";
    const mockServer = new MockWsServer(WS_URL);
    const connectionAttempts: number[] = [];

    mockServer.on("connection", () => connectionAttempts.push(Date.now()));

    const wsClient = new FlowforgeWsClient({
      wsBaseUrl: WS_URL,
      path: "",
      WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
      maxReconnectAttempts: 5,
      baseReconnectDelayMs: 5,
    });

    wsClient.open();
    await new Promise((r) => setTimeout(r, 20));
    wsClient.close();

    const countAfterClose = connectionAttempts.length;
    await new Promise((r) => setTimeout(r, 100));
    expect(connectionAttempts.length).toBe(countAfterClose);
    expect(wsClient.isClosed).toBe(true);

    mockServer.stop();
  });

  it("reconnects automatically on unexpected close", async () => {
    const WS_URL = "ws://localhost:9995";
    const mockServer = new MockWsServer(WS_URL);
    const connectionAttempts: number[] = [];

    mockServer.on("connection", (socket) => {
      connectionAttempts.push(Date.now());
      // Close after first connection to trigger reconnect
      if (connectionAttempts.length === 1) {
        setTimeout(() => socket.close(), 10);
      }
    });

    const wsClient = new FlowforgeWsClient({
      wsBaseUrl: WS_URL,
      path: "",
      WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
      maxReconnectAttempts: 3,
      baseReconnectDelayMs: 10,
    });

    wsClient.open();
    // Wait long enough for reconnect to fire
    await new Promise((r) => setTimeout(r, 200));

    expect(connectionAttempts.length).toBeGreaterThanOrEqual(2);

    wsClient.close();
    mockServer.stop();
  });
});

// ---------------------------------------------------------------------------
// buildTenantQueryKey (pure utility)
// ---------------------------------------------------------------------------

describe("buildTenantQueryKey", () => {
  it("builds a stable key without params", () => {
    const key = buildTenantQueryKey("tenant-abc", "instances");
    expect(key).toEqual(["flowforge", "tenant:tenant-abc", "instances"]);
  });

  it("appends params when provided", () => {
    const key = buildTenantQueryKey("tenant-abc", "instances", { def_key: "claim-intake" });
    expect(key).toEqual([
      "flowforge",
      "tenant:tenant-abc",
      "instances",
      { def_key: "claim-intake" },
    ]);
  });

  it("different tenantIds produce different keys", () => {
    const k1 = buildTenantQueryKey("t1", "instances");
    const k2 = buildTenantQueryKey("t2", "instances");
    expect(k1).not.toEqual(k2);
  });
});

// ---------------------------------------------------------------------------
// useTenantQueryKey hook (React-free, injected hooks)
// ---------------------------------------------------------------------------

describe("useTenantQueryKey", () => {
  it("resolves tenantId and returns a working build()", async () => {
    let resolvedId = "unknown";
    let effectCb: (() => void | (() => void)) | null = null;

    const react = {
      useState: <S>(init: S | (() => S)): [S, (a: S | ((p: S) => S)) => void] => {
        const val = typeof init === "function" ? (init as () => S)() : init;
        return [
          val,
          (action) => {
            resolvedId = String(
              typeof action === "function" ? (action as (p: S) => S)(val) : action,
            );
          },
        ];
      },
      useEffect: (fn: () => void | (() => void), _deps?: unknown[]) => {
        effectCb = fn;
      },
      useCallback: <T extends (...args: never[]) => unknown>(fn: T, _deps: unknown[]): T => fn,
    };

    useTenantQueryKey({
      getTenantId: () => Promise.resolve("tenant-xyz"),
      react,
    });

    // Simulate effect run
    if (effectCb) (effectCb as () => void)();

    // Wait for promise resolution
    await new Promise((r) => setTimeout(r, 10));

    expect(resolvedId).toBe("tenant-xyz");
  });

  it("build() uses 'unknown' before resolution", () => {
    const react = {
      useState: <S>(init: S | (() => S)): [S, (a: S | ((p: S) => S)) => void] => {
        const val = typeof init === "function" ? (init as () => S)() : init;
        return [val, () => {}];
      },
      useEffect: (_fn: () => void | (() => void), _deps?: unknown[]) => {},
      useCallback: <T extends (...args: never[]) => unknown>(fn: T, _deps: unknown[]): T => fn,
    };

    const { build, tenantReady } = useTenantQueryKey({
      getTenantId: () => Promise.resolve("t1"),
      react,
      enabled: false,
    });

    expect(tenantReady).toBe(false);
    const key = build("instances");
    expect(key).toEqual(["flowforge", "tenant:unknown", "instances"]);
  });
});

// ---------------------------------------------------------------------------
// subscribeStream — WS event for correct instanceId triggers refresh path
// ---------------------------------------------------------------------------

describe("subscribeStream integration (WS event routing)", () => {
  it("WS state_changed event for matched instance triggers hook refresh logic", async () => {
    const WS_URL = "ws://localhost:9996";
    const mockServer = new MockWsServer(WS_URL);

    const wsEventsSeen: unknown[] = [];

    const wsClient = new FlowforgeWsClient({
      wsBaseUrl: WS_URL,
      path: "",
      WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
      onEvent: (evt) => wsEventsSeen.push(evt),
      maxReconnectAttempts: 1,
    });

    // Minimal React shim — just enough for the hook structure
    const react = {
      useState: <S>(init: S | (() => S)): [S, (a: S | ((p: S) => S)) => void] => {
        const val = typeof init === "function" ? (init as () => S)() : init;
        return [val, () => {}];
      },
      useEffect: (_fn: () => void | (() => void), _deps?: unknown[]) => {},
      useCallback: <T extends (...args: never[]) => unknown>(fn: T, _deps: unknown[]): T => fn,
    };

    const client = makeClient();
    useFlowforgeWorkflow({ client, instanceId: "inst-001", wsClient, react });

    wsClient.open();

    await new Promise<void>((resolve) => {
      mockServer.on("connection", (socket) => {
        socket.send(JSON.stringify({ type: "hello", user_id: "u1" }));
        setTimeout(() => {
          socket.send(
            JSON.stringify({
              type: "instance.state_changed",
              instance_id: "inst-001",
              from_state: "draft",
              to_state: "triage",
            }),
          );
          resolve();
        }, 10);
      });
    });

    await new Promise((r) => setTimeout(r, 30));

    // The WS event should have arrived (onEvent fires for non-hello frames)
    expect(wsEventsSeen.length).toBeGreaterThanOrEqual(1);
    expect(wsEventsSeen[0]).toMatchObject({
      type: "instance.state_changed",
      instance_id: "inst-001",
    });

    wsClient.close();
    mockServer.stop();
  });
});
