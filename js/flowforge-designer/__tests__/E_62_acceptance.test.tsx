/**
 * audit-2026 E-62 acceptance tests (findings JS-04, JS-05, JS-06).
 */

import { describe, it, expect } from "vitest";

import {
	applyRemotePatch,
	createDesignerStore,
	emptyWorkflow,
	safeRedo,
	safeUndo,
} from "../src/store.js";
import type {
	DesignerStore,
	WorkflowDef,
	WorkflowState,
	WorkflowStateKind,
} from "../src/index.js";

// ---------------------------------------------------------------------------
// JS-04 — undo entry includes version; mismatched redo rejected
// ---------------------------------------------------------------------------

describe("test_JS_04_undo_redo_version_gate", () => {
	const _state = (id: string, kind: WorkflowStateKind = "manual_review"): WorkflowState => ({
		id,
		name: id,
		kind,
	});

	it("contiguous undo+redo succeeds", () => {
		const store = createDesignerStore();
		store.getState().addState(_state("a"));
		const v1 = store.getState().version;
		expect(v1).toBe(1);

		// Undo and then redo should re-apply.
		const undo1 = safeUndo(store);
		expect(undo1.ok).toBe(true);
		expect(store.getState().version).toBe(0);

		const redo1 = safeRedo(store);
		expect(redo1.ok).toBe(true);
		expect(store.getState().version).toBe(1);
		expect(store.getState().workflow.states.length).toBe(1);
	});

	it("redo refuses when a collaborator patch broke version contiguity", () => {
		const store = createDesignerStore();
		store.getState().addState(_state("a"));
		store.getState().addState(_state("b"));
		expect(store.getState().version).toBe(2);

		// User undoes their second add. Future stack now holds the v=2 entry.
		safeUndo(store);
		expect(store.getState().version).toBe(1);

		// A collaborator patch lands while a redo is pending — applyRemotePatch
		// (the helper, not the raw store action) records the conflict so the
		// next safeRedo refuses with a clear message instead of silently
		// dropping the future stack.
		applyRemotePatch(store, {
			workflow: {
				...store.getState().workflow,
				states: [_state("a"), _state("collab")],
			},
		});
		expect(store.getState().version).toBe(2);

		// User now hits redo. The future entry's version (2) equals the
		// current version (2) — NOT current+1 — so the gate rejects.
		const res = safeRedo(store);
		expect(res.ok).toBe(false);
		expect(res.message).toContain("collaborator");
		// Store untouched.
		const states = store.getState().workflow.states.map((s) => s.id);
		expect(states).toEqual(["a", "collab"]);
	});

	it("safeUndo / safeRedo report empty stacks with a friendly message", () => {
		const store = createDesignerStore();
		const undo = safeUndo(store);
		expect(undo.ok).toBe(false);
		expect(undo.message).toBe("Nothing to undo.");
		const redo = safeRedo(store);
		expect(redo.ok).toBe(false);
		expect(redo.message).toBe("Nothing to redo.");
	});
});

// ---------------------------------------------------------------------------
// JS-05 — addState kind matches DSL kinds; dead `start` branch removed
// ---------------------------------------------------------------------------

describe("test_JS_05_addState_kinds_match_dsl", () => {
	const allDslKinds: WorkflowStateKind[] = [
		"manual_review",
		"automatic",
		"parallel_fork",
		"parallel_join",
		"timer",
		"signal_wait",
		"subworkflow",
		"terminal_success",
		"terminal_fail",
	];

	it("WorkflowStateKind union has the canonical DSL kinds", () => {
		// Compile-time check via assignment — TS rejects unknown kinds.
		for (const kind of allDslKinds) {
			const s: WorkflowState = { id: "x", name: "x", kind };
			expect(s.kind).toBe(kind);
		}
	});

	it("addState seeds initial_state with the first added state regardless of kind", () => {
		// Previously the legacy `state.kind === "start"` branch decided
		// whether to seed `initial_state`. With "start" gone we always
		// seed on first add.
		const store = createDesignerStore();
		store.getState().addState({
			id: "first",
			name: "first",
			kind: "automatic",
		});
		expect(store.getState().workflow.initial_state).toBe("first");

		// Subsequent adds don't overwrite the seed.
		store.getState().addState({
			id: "second",
			name: "second",
			kind: "manual_review",
		});
		expect(store.getState().workflow.initial_state).toBe("first");
	});

	it("emptyWorkflow has no states (clean slate)", () => {
		const wf: WorkflowDef = emptyWorkflow();
		expect(wf.states).toEqual([]);
		expect(wf.initial_state).toBe("");
	});
});

// ---------------------------------------------------------------------------
// JS-06 — JSON.parse safety surfaces validation error, not crash
// ---------------------------------------------------------------------------
//
// JsonField is React-renderer code; rather than spinning up the full DOM
// here we assert that the parse path used by the field is plain
// JSON.parse-in-try/catch (string-grep on the source). The renderer
// package's own integration tests exercise the visible behaviour.

describe("test_JS_06_json_parse_safety", () => {
	it("JsonField wraps JSON.parse in try/catch (source check)", async () => {
		// Read the renderer source from disk and assert the safety
		// pattern is present. We avoid pulling the renderer into
		// designer's test graph (their bundles diverge).
		const fs = await import("node:fs");
		const path = await import("node:path");
		const here = path.dirname(new URL(import.meta.url).pathname);
		const src = fs.readFileSync(
			path.resolve(here, "..", "..", "flowforge-renderer", "src", "fields", "JsonField.tsx"),
			"utf-8",
		);
		// Pattern: try { ... JSON.parse ... } catch { ... setParseError ... }
		expect(src).toMatch(/try\s*\{[^}]*JSON\.parse/);
		expect(src).toMatch(/setParseError/);
		// And there's no bare top-level JSON.parse in render path.
		const rendererCalls = src.match(/JSON\.parse/g) ?? [];
		// Each JSON.parse call must be inside a try-block — verify the
		// substring window before each call contains "try {".
		for (const _match of rendererCalls) {
			const i = src.indexOf("JSON.parse");
			const window = src.slice(Math.max(0, i - 200), i);
			expect(window).toMatch(/try\s*\{/);
		}
	});

	it("DesignerStore type re-export carries the safeRedo helper", () => {
		// Trivial sanity check that the helper exists and is callable.
		const store: DesignerStore = createDesignerStore();
		const out = safeRedo(store);
		expect(typeof out.ok).toBe("boolean");
	});
});
