/**
 * Integration test #12: designer authoring → runtime-client round-trip.
 *
 * @flowforge/designer is used to author a workflow def in-memory.
 * @flowforge/runtime-client (mocked HTTP via msw) is used to:
 *   1. Validate the def (POST /defs/validate).
 *   2. Publish it (mock GET /defs to return it).
 *   3. Start an instance (POST /instances).
 *   4. Fire an event (POST /instances/{id}/events).
 *
 * No real server — msw intercepts fetch at the node layer.
 */

import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { createDesignerStore, sampleWorkflow } from "@flowforge/designer";
import { FlowforgeClient } from "@flowforge/runtime-client";
import type { InstanceView, FireResultView } from "@flowforge/runtime-client";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE = "http://test-server.local";

const INSTANCE: InstanceView = {
	id: "inst-abc",
	def_key: "demo_claim",
	def_version: "1.0.0",
	state: "draft",
	context: {},
	history: ["draft"],
	saga: [],
	created_entities: [],
};

const FIRE_RESULT: FireResultView = {
	instance: { ...INSTANCE, state: "in_review", history: ["draft", "in_review"] },
	matched_transition_id: "submit",
	new_state: "in_review",
	terminal: false,
	audit_event_kinds: ["wf.demo_claim.transitioned"],
	outbox_kinds: [],
};

// ---------------------------------------------------------------------------
// MSW server
// ---------------------------------------------------------------------------

const server = setupServer(
	http.post(`${BASE}/defs/validate`, () =>
		HttpResponse.json({ ok: true, errors: [], warnings: [] }),
	),
	http.get(`${BASE}/defs`, () =>
		HttpResponse.json({
			defs: [
				{
					key: "demo_claim",
					version: "1.0.0",
					subject_kind: "claim",
					initial_state: "draft",
					states: ["draft", "in_review", "approved"],
				},
			],
		}),
	),
	http.post(`${BASE}/instances`, () => HttpResponse.json(INSTANCE, { status: 201 })),
	http.post(`${BASE}/instances/:id/events`, () => HttpResponse.json(FIRE_RESULT)),
	http.get(`${BASE}/instances/:id`, () =>
		HttpResponse.json({ ...INSTANCE, state: "in_review" }),
	),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("designer authoring → runtime-client round-trip", () => {
	const client = new FlowforgeClient({ baseUrl: BASE, maxAttempts: 1 });

	it("creates and mutates a workflow def in the designer store", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		const before = store.getState().workflow.states.length;
		store.getState().addState({
			id: "extra",
			name: "Extra step",
			kind: "review",
		});
		expect(store.getState().workflow.states).toHaveLength(before + 1);
	});

	it("validates the authored def via the runtime-client", async () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		const wf = store.getState().workflow;

		const result = await client.validateDef({ definition: wf as unknown as Record<string, unknown> });
		expect(result.ok).toBe(true);
		expect(result.errors).toHaveLength(0);
	});

	it("lists defs after publication", async () => {
		const defs = await client.listDefs();
		expect(defs).toHaveLength(1);
		expect(defs[0].key).toBe("demo_claim");
	});

	it("starts an instance from the published def", async () => {
		const inst = await client.startInstance(
			{ def_key: "demo_claim", tenant_id: "t-1" },
			"idem-key-1",
		);
		expect(inst.id).toBe("inst-abc");
		expect(inst.state).toBe("draft");
	});

	it("fires an event and advances state", async () => {
		const result = await client.sendEvent(
			"inst-abc",
			{ event: "submit", tenant_id: "t-1" },
			"idem-key-2",
		);
		expect(result.new_state).toBe("in_review");
		expect(result.matched_transition_id).toBe("submit");
		expect(result.terminal).toBe(false);
	});

	it("reads the updated snapshot", async () => {
		const snap = await client.getInstance("inst-abc");
		expect(snap.state).toBe("in_review");
	});
});
