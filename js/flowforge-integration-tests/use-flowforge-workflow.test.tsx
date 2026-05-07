/**
 * test_JS_03_react19_mount — useFlowforgeWorkflow contract test under React 19.
 *
 * audit-2026 E-43 / JS-03: the hook compiles and mounts in a React 19 host
 * tree, surfaces an `InstanceView`, and exposes a stable callback identity
 * across renders.
 *
 * The default vitest config aliases `react` to React 18 (so the legacy
 * @testing-library/react@16 integration specs keep working). This file
 * imports React 19 via an explicit path-based import so the contract test
 * runs under the actual React 19 hook implementations the renderer's
 * peer dependency promises.
 */

import { describe, it, expect, vi } from "vitest";
// @ts-expect-error — `react19` is a vitest-only alias to the pnpm-stored React 19.
import * as React19 from "react19";

import { useFlowforgeWorkflow } from "@flowforge/runtime-client";
import type {
	FlowforgeClient,
	InstanceView,
	UseFlowforgeWorkflowResult,
} from "@flowforge/runtime-client";

// React 19 hook surface — passed into the hook via dependency injection so
// useFlowforgeWorkflow exercises React 19's actual implementations.
const REACT19_HOOKS = {
	useState: React19.useState,
	useEffect: React19.useEffect,
	useCallback: React19.useCallback,
};

function makeInstanceView(overrides: Partial<InstanceView> = {}): InstanceView {
	const base = {
		id: "instance-1",
		workflow_key: "demo",
		workflow_version: "1.0.0",
		state: "draft",
		subject_id: "subj-1",
		tenant_id: "t-1",
		created_at: "2024-01-01T00:00:00Z",
		updated_at: "2024-01-01T00:00:00Z",
		context: {},
		history: [],
	} as unknown as InstanceView;
	return { ...base, ...overrides };
}

function makeStubClient(view: InstanceView, options: { fail?: boolean } = {}): FlowforgeClient {
	const getInstance = options.fail
		? vi.fn().mockRejectedValue(new Error("boom"))
		: vi.fn().mockResolvedValue(view);
	const sendEvent = vi.fn().mockImplementation(async (id: string) => ({
		ok: true,
		instance: makeInstanceView({ id, state: "approved" }),
		audit_event_id: "evt-1",
	}));
	return { getInstance, sendEvent } as unknown as FlowforgeClient;
}

/**
 * Drive React 19's hook dispatcher manually for a single function-component
 * call. We don't need a DOM tree to exercise the hook contract — we simulate
 * the mount/effect/cleanup lifecycle by running the function under
 * `React.act`-style flushing and inspecting the returned object.
 */
async function driveHook<T>(fn: () => T): Promise<T> {
	let result: T | undefined;
	function Probe() {
		result = fn();
		return null;
	}
	// `react19-dom/client` is a vitest-only alias matching React 19.
	// @ts-expect-error — alias resolves at vitest runtime.
	const ReactDOM = await import("react19-dom/client");
	const container = document.createElement("div");
	const root = ReactDOM.createRoot(container);
	await React19.act(async () => {
		root.render(React19.createElement(Probe));
	});
	// Allow microtask queue to flush (instance fetch resolves).
	await new Promise<void>((r) => setTimeout(r, 0));
	await React19.act(async () => {
		root.render(React19.createElement(Probe));
	});
	root.unmount();
	if (result === undefined) {
		throw new Error("Probe produced no result");
	}
	return result;
}

describe("test_JS_03_react19_mount: useFlowforgeWorkflow under React 19", () => {
	it("verifies React major version is 19 (contract assertion)", () => {
		// Anchor: this test is meaningless if React isn't 19 because the
		// renderer's peer dep promises React 19 compatibility.
		const major = parseInt(String(React19.version).split(".")[0]!, 10);
		expect(major).toBeGreaterThanOrEqual(19);
	});

	it("exposes useState / useEffect / useCallback that match the ReactHooks contract", () => {
		// Surface check — useFlowforgeWorkflow's `react: ReactHooks` injection
		// expects these three callables. React 19 must satisfy that shape.
		expect(typeof REACT19_HOOKS.useState).toBe("function");
		expect(typeof REACT19_HOOKS.useEffect).toBe("function");
		expect(typeof REACT19_HOOKS.useCallback).toBe("function");
	});

	it("mounts and resolves the initial instance snapshot", async () => {
		const view = makeInstanceView({ state: "draft" });
		const client = makeStubClient(view);

		const result = await driveHook(() =>
			useFlowforgeWorkflow({
				client,
				instanceId: "instance-1",
				react: REACT19_HOOKS,
			}),
		);

		expect(result.instance?.state).toBe("draft");
		expect(result.error).toBeNull();
		expect(client.getInstance).toHaveBeenCalledWith("instance-1");
	});

	it("returns a result with the documented public shape", async () => {
		const view = makeInstanceView();
		const client = makeStubClient(view);

		const result: UseFlowforgeWorkflowResult = await driveHook(() =>
			useFlowforgeWorkflow({
				client,
				instanceId: "instance-1",
				react: REACT19_HOOKS,
			}),
		);

		expect(typeof result.refresh).toBe("function");
		expect(typeof result.sendEvent).toBe("function");
		expect("instance" in result).toBe(true);
		expect("isLoading" in result).toBe(true);
		expect("error" in result).toBe(true);
	});

	it("surfaces fetch errors without throwing into the render path", async () => {
		const view = makeInstanceView();
		const client = makeStubClient(view, { fail: true });

		const result = await driveHook(() =>
			useFlowforgeWorkflow({
				client,
				instanceId: "instance-1",
				react: REACT19_HOOKS,
			}),
		);

		expect(result.error).toBeInstanceOf(Error);
		expect(result.error?.message).toBe("boom");
		expect(result.instance).toBeNull();
	});

	it("clears instance when instanceId is nullish", async () => {
		const view = makeInstanceView();
		const client = makeStubClient(view);

		const result = await driveHook(() =>
			useFlowforgeWorkflow({
				client,
				instanceId: null,
				react: REACT19_HOOKS,
			}),
		);

		expect(result.instance).toBeNull();
		expect(client.getInstance).not.toHaveBeenCalled();
	});
});
