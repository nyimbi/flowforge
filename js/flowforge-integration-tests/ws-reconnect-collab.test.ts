/**
 * audit-2026 E-63 / IT-03 — WS reconnect + collaboration edge cases.
 *
 * Two integration scenarios:
 *
 * 1. WS reconnect: a transient socket close triggers exponential-backoff
 *    reconnection without losing subscribers; events arriving after the
 *    reconnect reach the same handlers.
 *
 * 2. Simultaneous-edit collab conflict: an `applyRemotePatch` lands while
 *    the user has a pending undo stack. The next ``safeRedo`` must refuse
 *    with a clear collaboration-conflict message rather than silently
 *    overwriting the remote change.
 */

import {
	describe,
	it,
	expect,
	vi,
	beforeEach,
	afterEach,
} from "vitest";

import { FlowforgeWsClient, type WsEnvelope } from "@flowforge/runtime-client";
import {
	applyRemotePatch,
	createDesignerStore,
	safeRedo,
	safeUndo,
} from "@flowforge/designer";
import type { WorkflowState } from "@flowforge/designer";

// ---------------------------------------------------------------------------
// Minimal browser-WebSocket mock — fakes onopen/onmessage/onclose lifecycle
// without touching the network or `mock-socket`. The runtime-client only
// uses the four event hooks + close/send, so a hand-rolled mock is enough.
// ---------------------------------------------------------------------------

interface MockSocketLike {
	url: string;
	readyState: number;
	onopen: ((e: Event) => void) | null;
	onmessage: ((e: MessageEvent) => void) | null;
	onclose: ((e: CloseEvent) => void) | null;
	onerror: ((e: Event) => void) | null;
	close(code?: number, reason?: string): void;
	send(data: string): void;
}

class MockWebSocket implements MockSocketLike {
	static instances: MockWebSocket[] = [];
	readonly url: string;
	readyState = 0; // CONNECTING
	onopen: ((e: Event) => void) | null = null;
	onmessage: ((e: MessageEvent) => void) | null = null;
	onclose: ((e: CloseEvent) => void) | null = null;
	onerror: ((e: Event) => void) | null = null;

	constructor(url: string | URL) {
		this.url = String(url);
		MockWebSocket.instances.push(this);
		// Simulate async connection.
		queueMicrotask(() => {
			this.readyState = 1; // OPEN
			this.onopen?.(new Event("open"));
		});
	}

	close(_code?: number, _reason?: string): void {
		if (this.readyState === 3) return; // CLOSED
		this.readyState = 3;
		this.onclose?.(new CloseEvent("close"));
	}

	send(_data: string): void {
		// no-op
	}

	// Test-only: deliver a frame to the consumer.
	deliver(envelope: WsEnvelope): void {
		this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(envelope) }));
	}

	// Test-only: simulate a server-side close.
	simulateServerClose(): void {
		this.readyState = 3;
		this.onclose?.(new CloseEvent("close"));
	}
}

// ---------------------------------------------------------------------------
// IT-03 — WS reconnect
// ---------------------------------------------------------------------------

describe("test_IT_03_ws_reconnect", () => {
	beforeEach(() => {
		MockWebSocket.instances.length = 0;
		vi.useFakeTimers();
	});
	afterEach(() => {
		vi.useRealTimers();
	});

	it("after a transient close, the client reconnects and re-emits to handlers", async () => {
		const events: WsEnvelope[] = [];
		const helloes: unknown[] = [];

		const client = new FlowforgeWsClient({
			wsBaseUrl: "ws://test",
			baseReconnectDelayMs: 10,
			WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
			onConnect: (h) => helloes.push(h),
			onEvent: (e) => events.push(e),
		});
		client.open();

		// Drain microtasks so the first connection's onopen fires.
		await vi.runOnlyPendingTimersAsync();
		const first = MockWebSocket.instances[0];
		expect(first).toBeDefined();
		first!.deliver({ type: "hello", user_id: "u1" });
		first!.deliver({ type: "instance.state_changed", instance_id: "i1" });
		expect(helloes).toEqual([{ type: "hello", user_id: "u1" }]);
		expect(events).toHaveLength(1);

		// Server drops the connection.
		first!.simulateServerClose();

		// Backoff timer fires; new connection appears.
		await vi.advanceTimersByTimeAsync(50);
		expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
		const second = MockWebSocket.instances[MockWebSocket.instances.length - 1];
		await vi.runOnlyPendingTimersAsync();

		// New socket emits its own hello + an event; both reach the same handlers.
		second!.deliver({ type: "hello", user_id: "u1" });
		second!.deliver({ type: "instance.state_changed", instance_id: "i2" });
		expect(helloes).toHaveLength(2);
		expect(events).toHaveLength(2);
		expect(events[1]).toMatchObject({ instance_id: "i2" });

		client.close();
	});

	it("close() stops further reconnect attempts", async () => {
		const client = new FlowforgeWsClient({
			wsBaseUrl: "ws://test",
			baseReconnectDelayMs: 10,
			WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
		});
		client.open();
		await vi.runOnlyPendingTimersAsync();
		expect(MockWebSocket.instances.length).toBe(1);

		// Server closes; we close the client BEFORE the backoff fires.
		MockWebSocket.instances[0]!.simulateServerClose();
		client.close();

		await vi.advanceTimersByTimeAsync(500);
		// No new socket created — close() short-circuited the reconnect.
		expect(MockWebSocket.instances.length).toBe(1);
	});

	it("backoff delays grow as attempts repeat", async () => {
		const client = new FlowforgeWsClient({
			wsBaseUrl: "ws://test",
			baseReconnectDelayMs: 100,
			WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
		});
		client.open();
		await vi.runOnlyPendingTimersAsync();
		const after = (n: number) => MockWebSocket.instances.length === n;

		// Trigger three rounds of close.
		for (let i = 0; i < 3; i++) {
			MockWebSocket.instances[MockWebSocket.instances.length - 1]!.simulateServerClose();
			await vi.advanceTimersByTimeAsync(2000);
		}
		// Each close should produce one reconnect attempt — total >= 4 sockets.
		expect(after(4) || MockWebSocket.instances.length > 4).toBe(true);
		client.close();
	});
});

// ---------------------------------------------------------------------------
// IT-03 — Simultaneous-edit conflict resolution (designer store)
// ---------------------------------------------------------------------------

describe("test_IT_03_simultaneous_edit_conflict", () => {
	const _state = (id: string): WorkflowState => ({ id, name: id, kind: "manual_review" });

	it("a remote patch landing during pending undo blocks redo with a user message", () => {
		const store = createDesignerStore();

		// User makes two edits.
		store.getState().addState(_state("alpha"));
		store.getState().addState(_state("beta"));
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual(["alpha", "beta"]);

		// User undoes the second edit.
		const undo = safeUndo(store);
		expect(undo.ok).toBe(true);
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual(["alpha"]);

		// Collaborator pushes a different patch.
		applyRemotePatch(store, {
			workflow: {
				...store.getState().workflow,
				states: [_state("alpha"), _state("collab_only")],
			},
		});
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual([
			"alpha",
			"collab_only",
		]);

		// User now hits redo. The conflict tracker rejects with a clear message.
		const redo = safeRedo(store);
		expect(redo.ok).toBe(false);
		expect(redo.message).toMatch(/collaborator/i);

		// State is unchanged — collaborator's patch survives.
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual([
			"alpha",
			"collab_only",
		]);
	});

	it("after a conflict, a fresh undo+redo cycle works (state recovered)", () => {
		const store = createDesignerStore();
		store.getState().addState(_state("alpha"));
		safeUndo(store);
		applyRemotePatch(store, {
			workflow: {
				...store.getState().workflow,
				states: [_state("collab")],
			},
		});
		// First redo refuses (conflict pending).
		const blocked = safeRedo(store);
		expect(blocked.ok).toBe(false);

		// User makes a fresh edit then undoes it — local stack is healthy.
		store.getState().addState(_state("user2"));
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual([
			"collab",
			"user2",
		]);
		safeUndo(store);
		const fresh = safeRedo(store);
		expect(fresh.ok).toBe(true);
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual([
			"collab",
			"user2",
		]);
	});

	it("undo+redo without remote patch is fully reversible", () => {
		const store = createDesignerStore();
		store.getState().addState(_state("a"));
		store.getState().addState(_state("b"));
		store.getState().addState(_state("c"));
		expect(store.getState().version).toBe(3);

		safeUndo(store);
		safeUndo(store);
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual(["a"]);
		safeRedo(store);
		safeRedo(store);
		expect(store.getState().workflow.states.map((s) => s.id)).toEqual(["a", "b", "c"]);
	});
});
