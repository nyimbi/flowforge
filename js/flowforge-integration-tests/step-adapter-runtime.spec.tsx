/**
 * Integration test #14: step-adapters registry + runtime-client round-trip.
 *
 * Uses @flowforge/step-adapters to:
 *   1. Register step components in a registry and load by kind.
 *   2. Render ManualReviewStep — verify button + onAction wiring.
 *   3. Verify withReadOnly HOC disables actions when readOnly=true.
 *   4. Wire a step action to FlowforgeClient.sendEvent (spied, not HTTP)
 *      to prove the integration seam without a real server in jsdom.
 *
 * HTTP transport is fully exercised by designer-runtime-integration.spec.ts
 * (node environment + msw). This file focuses on the component ↔ client
 * contract in jsdom.
 */

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import {
	createRegistry,
	loadStep,
	ManualReviewStep,
	registerStep,
	withReadOnly,
} from "@flowforge/step-adapters";

import { FlowforgeClient } from "@flowforge/runtime-client";
import type { FireResultView } from "@flowforge/runtime-client";
import type { StepActionPayload } from "@flowforge/types";

afterEach(() => {
	vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const APPROVE_RESULT: FireResultView = {
	instance: {
		id: "inst-step-001",
		def_key: "review_demo",
		def_version: "1.0.0",
		state: "approved",
		context: {},
		history: ["intake", "in_review", "approved"],
		saga: [],
		created_entities: [],
	},
	matched_transition_id: "approve",
	new_state: "approved",
	terminal: true,
	audit_event_kinds: ["wf.review_demo.transitioned"],
	outbox_kinds: [],
};

// ---------------------------------------------------------------------------
// Test: registry integration
// ---------------------------------------------------------------------------

describe("step registry", () => {
	it("registers and loads ManualReviewStep by kind", async () => {
		const reg = createRegistry();
		registerStep(reg, {
			kind: "manual_review",
			load: async () => ({ default: ManualReviewStep }),
		});
		const Component = await loadStep(reg, "manual_review");
		expect(Component).toBe(ManualReviewStep);
	});

	it("throws on unknown kind", async () => {
		const reg = createRegistry();
		await expect(loadStep(reg, "unknown_kind")).rejects.toThrow();
	});
});

// ---------------------------------------------------------------------------
// Test: ManualReviewStep rendering + onAction
// ---------------------------------------------------------------------------

describe("ManualReviewStep", () => {
	it("renders the step and fires onAction on button click", () => {
		const onAction = vi.fn<(payload: StepActionPayload) => void>();
		render(
			<ManualReviewStep
				instanceId="inst-1"
				stepId="review-step"
				meta={{ actions: ["approve", "reject"] }}
				onAction={onAction}
			/>,
		);

		expect(screen.getByRole("button", { name: /approve/i })).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: /approve/i }));

		expect(onAction).toHaveBeenCalledOnce();
		expect(onAction.mock.calls[0][0]).toMatchObject({ action: "approve" });
	});
});

// ---------------------------------------------------------------------------
// Test: withReadOnly HOC blocks onAction
// ---------------------------------------------------------------------------

describe("withReadOnly HOC", () => {
	it("disables buttons and blocks onAction when readOnly=true", () => {
		const onAction = vi.fn<(payload: StepActionPayload) => void>();
		const ReadOnlyStep = withReadOnly(ManualReviewStep);

		render(
			<ReadOnlyStep
				instanceId="inst-ro"
				stepId="review-step"
				meta={{ actions: ["approve"] }}
				onAction={onAction}
				readOnly
			/>,
		);

		const btn = screen.getByRole("button", { name: /approve/i }) as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
		fireEvent.click(btn);
		expect(onAction).not.toHaveBeenCalled();
	});
});

// ---------------------------------------------------------------------------
// Test: step action wired to FlowforgeClient.sendEvent (spy — no real HTTP)
// ---------------------------------------------------------------------------

describe("step-adapter → runtime-client integration", () => {
	it("calls client.sendEvent when step action fires", async () => {
		// Spy on sendEvent so we don't need a real server in jsdom.
		const client = new FlowforgeClient({ baseUrl: "http://nowhere", maxAttempts: 1 });
		const spy = vi
			.spyOn(client, "sendEvent")
			.mockResolvedValue(APPROVE_RESULT);

		const captured: FireResultView[] = [];

		const onAction = vi.fn<(payload: StepActionPayload) => Promise<void>>(
			async ({ action }) => {
				const result = await client.sendEvent(
					"inst-step-001",
					{ event: action },
					`idem-${action}-1`,
				);
				captured.push(result);
			},
		);

		render(
			<ManualReviewStep
				instanceId="inst-step-001"
				stepId="review-step"
				meta={{ actions: ["approve"] }}
				onAction={onAction}
			/>,
		);

		fireEvent.click(screen.getByRole("button", { name: /approve/i }));

		// Wait for the async onAction to settle.
		await vi.waitFor(() => expect(captured).toHaveLength(1));

		expect(spy).toHaveBeenCalledWith(
			"inst-step-001",
			{ event: "approve" },
			"idem-approve-1",
		);
		expect(captured[0].new_state).toBe("approved");
		expect(captured[0].terminal).toBe(true);
	});
});
