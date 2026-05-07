import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Designer } from "../src/Designer.js";
import { DiffViewer } from "../src/DiffViewer.js";
import { diffWorkflows } from "../src/diff.js";
import { sampleForm, sampleWorkflow } from "../src/fixtures.js";
import { simulate } from "../src/simulation.js";
import { createDesignerStore } from "../src/store.js";
import type { WorkflowDef } from "../src/types.js";
import { validateWorkflow } from "../src/validation.js";

describe("createDesignerStore", () => {
	it("exposes the seeded workflow", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		expect(store.getState().workflow.states).toHaveLength(3);
		expect(store.getState().workflow.transitions).toHaveLength(3);
	});

	it("supports undo/redo on state edits via temporal middleware", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		store.getState().updateState("in_review", { name: "Reviewing" });
		expect(store.getState().workflow.states[1]?.name).toBe("Reviewing");

		act(() => {
			store.temporal.getState().undo();
		});
		expect(store.getState().workflow.states[1]?.name).toBe("In review");

		act(() => {
			store.temporal.getState().redo();
		});
		expect(store.getState().workflow.states[1]?.name).toBe("Reviewing");
	});

	it("removes transitions when their endpoints disappear", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		store.getState().removeState("in_review");
		const wf = store.getState().workflow;
		expect(wf.states.find((s) => s.id === "in_review")).toBeUndefined();
		// All transitions touching in_review should be gone.
		expect(wf.transitions.every((t) => t.from !== "in_review" && t.to !== "in_review")).toBe(
			true,
		);
	});

	it("reorders form fields with moveField", () => {
		const store = createDesignerStore({ form: sampleForm() });
		store.getState().moveField("notes", 0);
		expect(store.getState().form?.fields[0]?.id).toBe("notes");
	});
});

describe("validateWorkflow", () => {
	it("returns no errors for the sample workflow", () => {
		const issues = validateWorkflow(sampleWorkflow());
		expect(issues.filter((i) => i.severity === "error")).toEqual([]);
	});

	it("flags unknown initial_state", () => {
		const wf = sampleWorkflow();
		wf.initial_state = "ghost";
		const issues = validateWorkflow(wf);
		expect(issues.find((i) => i.code === "WF_INITIAL_UNKNOWN")).toBeDefined();
	});

	it("flags transitions to unknown states", () => {
		const wf = sampleWorkflow();
		wf.transitions.push({ id: "tx", from: "submitted", to: "missing", event: "ev" });
		const issues = validateWorkflow(wf);
		expect(issues.find((i) => i.code === "TRANS_TO_UNKNOWN")).toBeDefined();
	});

	it("flags duplicate state ids", () => {
		const wf = sampleWorkflow();
		wf.states.push({ id: "submitted", name: "dup", kind: "automatic" });
		const issues = validateWorkflow(wf);
		expect(issues.find((i) => i.code === "STATE_DUP")).toBeDefined();
	});
});

describe("simulate", () => {
	it("walks happy path to terminal", () => {
		const result = simulate(sampleWorkflow(), {
			events: ["begin_review", "approve"],
		});
		expect(result.terminated).toBe(true);
		expect(result.final_state).toBe("closed");
		expect(result.trace).toHaveLength(2);
	});

	it("stops when no transition matches the event", () => {
		const result = simulate(sampleWorkflow(), { events: ["unknown_event"] });
		expect(result.trace).toEqual([]);
		expect(result.terminated).toBe(false);
		expect(result.final_state).toBe("submitted");
	});
});

describe("diffWorkflows", () => {
	it("detects added, removed, and modified entities", () => {
		const before = sampleWorkflow();
		const after: WorkflowDef = {
			...sampleWorkflow(),
			name: "Claim intake v2",
			states: [
				...sampleWorkflow().states.filter((s) => s.id !== "in_review"),
				{ id: "in_review", name: "Reviewing now", kind: "manual_review" },
				{ id: "rejected", name: "Rejected", kind: "terminal_fail" },
			],
			transitions: [
				...sampleWorkflow().transitions.filter((t) => t.id !== "t3"),
				{ id: "t4", from: "in_review", to: "rejected", event: "reject" },
			],
			terminal_states: ["closed", "rejected"],
		};

		const entries = diffWorkflows(before, after);
		const kinds = entries.map((e) => `${e.kind}:${e.path}`);
		expect(kinds).toContain("modified:name");
		expect(kinds).toContain("modified:states/in_review");
		expect(kinds).toContain("added:states/rejected");
		expect(kinds).toContain("added:transitions/t4");
		expect(kinds).toContain("removed:transitions/t3");
	});
});

describe("Designer (integration)", () => {
	it("renders the canvas and selects a state on click + commit", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		render(<Designer store={store} withReactFlow={false} />);

		const stateNode = screen.getByTestId("canvas-state-in_review");
		fireEvent.click(stateNode);

		const panel = screen.getByTestId("property-panel");
		expect(within(panel).getByText(/State: in_review/)).toBeInTheDocument();

		// Edit name + commit, store should reflect the new value.
		const nameInput = screen.getByTestId("state-name-input") as HTMLInputElement;
		fireEvent.change(nameInput, { target: { value: "Under review" } });
		fireEvent.click(screen.getByTestId("state-name-commit"));

		expect(store.getState().workflow.states.find((s) => s.id === "in_review")?.name).toBe(
			"Under review",
		);
	});

	it("switches to the form builder tab and adds a field via the palette", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow(), form: sampleForm() });
		render(<Designer store={store} withReactFlow={false} />);

		fireEvent.click(screen.getByTestId("tab-form"));
		expect(screen.getByTestId("form-builder")).toBeInTheDocument();

		fireEvent.click(screen.getByTestId("palette-date"));
		const fields = store.getState().form?.fields ?? [];
		expect(fields.some((f) => f.kind === "date")).toBe(true);
	});

	it("adds a conditional rule to a field via the rules editor", () => {
		const store = createDesignerStore({ form: sampleForm() });
		render(<Designer store={store} withReactFlow={false} initialTab="form" />);

		// Pick the first field (claim_id).
		fireEvent.click(screen.getByTestId("form-field-claim_id"));
		fireEvent.click(screen.getByTestId("rule-add"));
		const rules = store.getState().form?.fields.find((f) => f.id === "claim_id")?.rules ?? [];
		expect(rules).toHaveLength(1);
		expect(rules[0]?.action).toBe("show");
	});

	it("renders the validation panel with issue counts", () => {
		const wf = sampleWorkflow();
		wf.initial_state = "ghost";
		const store = createDesignerStore({ workflow: wf });
		render(<Designer store={store} withReactFlow={false} initialTab="validation" />);
		expect(screen.getByTestId("validation-counts").textContent).toMatch(/errors/);
	});

	it("simulates events from the simulation panel", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		render(<Designer store={store} withReactFlow={false} initialTab="simulation" />);

		fireEvent.change(screen.getByTestId("simulation-events"), {
			target: { value: "begin_review, approve" },
		});
		expect(screen.getByTestId("simulation-final").textContent).toBe("closed");
		expect(screen.getByTestId("simulation-terminated").textContent).toBe("yes");
	});

	it("renders a two-version diff", () => {
		const before = sampleWorkflow();
		const after: WorkflowDef = {
			...before,
			name: "Renamed",
			states: [
				...before.states.filter((s) => s.id !== "in_review"),
				{ id: "in_review", name: "Reviewing", kind: "manual_review" },
			],
		};
		render(<DiffViewer before={before} after={after} />);
		expect(screen.getByTestId("diff-counts").textContent).toMatch(/~/);
		expect(screen.getAllByText(/modified/i).length).toBeGreaterThan(0);
		expect(screen.getByTestId("diff-modified-0")).toHaveAttribute("data-path", "name");
	});

	it("toggles undo/redo buttons based on temporal stack", () => {
		const store = createDesignerStore({ workflow: sampleWorkflow() });
		render(<Designer store={store} withReactFlow={false} />);

		const undo = screen.getByTestId("undo") as HTMLButtonElement;
		expect(undo.disabled).toBe(true);

		act(() => {
			store.getState().updateState("in_review", { name: "Reviewing" });
		});

		expect((screen.getByTestId("undo") as HTMLButtonElement).disabled).toBe(false);
	});
});
