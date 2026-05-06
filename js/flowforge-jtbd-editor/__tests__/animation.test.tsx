import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobMapAnimation } from "../src/JobMapAnimation.js";
import {
	animationReducer,
	initialAnimationState,
	runToEnd,
	stepLabel,
} from "../src/animation.js";
import { sampleBundle } from "../src/fixtures.js";
import {
	buildDefaultTrace,
	buildTraceFromEvents,
	type Trace,
} from "../src/trace.js";
import type { JtbdBundle } from "../src/types.js";

describe("trace builders", () => {
	it("orders the sample bundle topologically by requires depth", () => {
		const trace = buildDefaultTrace(sampleBundle());
		expect(trace.steps.map((s) => s.jtbdId)).toEqual([
			"claim_intake",
			"claim_triage",
			"claim_assign",
			"claim_approve",
		]);
	});

	it("indexes each step starting at zero", () => {
		const trace = buildDefaultTrace(sampleBundle());
		expect(trace.steps.map((s) => s.index)).toEqual([0, 1, 2, 3]);
	});

	it("appends cycle members at the end in declared order", () => {
		const cyclic: JtbdBundle = {
			project: { name: "x", package: "x", domain: "y" },
			jtbds: [
				{
					id: "root",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
				},
				{
					id: "a",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["b"],
				},
				{
					id: "b",
					actor: { role: "r" },
					situation: "s",
					motivation: "m",
					outcome: "o",
					success_criteria: ["sc"],
					requires: ["a"],
				},
			],
		};
		const trace = buildDefaultTrace(cyclic);
		expect(trace.steps.map((s) => s.jtbdId)).toEqual(["root", "a", "b"]);
	});

	it("buildTraceFromEvents drops unknown ids", () => {
		const trace = buildTraceFromEvents(sampleBundle(), [
			"claim_intake",
			"ghost_jtbd",
			"claim_triage",
		]);
		expect(trace.steps.map((s) => s.jtbdId)).toEqual([
			"claim_intake",
			"claim_triage",
		]);
		expect(trace.steps.map((s) => s.index)).toEqual([0, 1]);
	});

	it("buildTraceFromEvents preserves repeated ids (re-fire)", () => {
		const trace = buildTraceFromEvents(sampleBundle(), [
			"claim_triage",
			"claim_assign",
			"claim_triage",
		]);
		expect(trace.steps).toHaveLength(3);
		expect(trace.steps[0]?.jtbdId).toBe("claim_triage");
		expect(trace.steps[2]?.jtbdId).toBe("claim_triage");
	});
});

describe("animationReducer", () => {
	const trace = buildDefaultTrace(sampleBundle());

	it("starts in an idle state", () => {
		const state = initialAnimationState();
		expect(state.currentIndex).toBe(-1);
		expect(state.playing).toBe(false);
		expect(state.firedIds.size).toBe(0);
		expect(state.activeIds.size).toBe(0);
	});

	it("step_forward advances and fills firedIds + activeIds", () => {
		let state = initialAnimationState();
		state = animationReducer(state, { kind: "step_forward" }, trace);
		expect(state.currentIndex).toBe(0);
		expect([...state.activeIds]).toEqual(["claim_intake"]);
		expect([...state.firedIds]).toEqual(["claim_intake"]);

		state = animationReducer(state, { kind: "step_forward" }, trace);
		expect(state.currentIndex).toBe(1);
		expect([...state.activeIds]).toEqual(["claim_triage"]);
		expect(state.firedIds.has("claim_intake")).toBe(true);
		expect(state.firedIds.has("claim_triage")).toBe(true);
	});

	it("step_back unrolls fired ids back to a single active step", () => {
		let state = initialAnimationState();
		state = animationReducer(state, { kind: "step_forward" }, trace);
		state = animationReducer(state, { kind: "step_forward" }, trace);
		state = animationReducer(state, { kind: "step_back" }, trace);
		expect(state.currentIndex).toBe(0);
		expect([...state.activeIds]).toEqual(["claim_intake"]);
		expect(state.firedIds.has("claim_triage")).toBe(false);
	});

	it("step_back at start is a no-op", () => {
		const state = animationReducer(
			initialAnimationState(),
			{ kind: "step_back" },
			trace,
		);
		expect(state.currentIndex).toBe(-1);
	});

	it("step_forward at the end pauses without advancing", () => {
		let state = initialAnimationState();
		state = animationReducer(state, { kind: "play" }, trace);
		for (let i = 0; i < trace.steps.length; i++) {
			state = animationReducer(state, { kind: "step_forward" }, trace);
		}
		expect(state.currentIndex).toBe(trace.steps.length - 1);
		// One more step is a no-op + auto-pause.
		state = animationReducer(state, { kind: "step_forward" }, trace);
		expect(state.currentIndex).toBe(trace.steps.length - 1);
		expect(state.playing).toBe(false);
	});

	it("seek clamps to the trace bounds", () => {
		const a = animationReducer(
			initialAnimationState(),
			{ kind: "seek", index: 999 },
			trace,
		);
		expect(a.currentIndex).toBe(trace.steps.length - 1);

		const b = animationReducer(
			initialAnimationState(),
			{ kind: "seek", index: -42 },
			trace,
		);
		expect(b.currentIndex).toBe(-1);
	});

	it("seek populates firedIds for every prior step", () => {
		const state = animationReducer(
			initialAnimationState(),
			{ kind: "seek", index: 2 },
			trace,
		);
		expect(state.firedIds).toEqual(
			new Set(["claim_intake", "claim_triage", "claim_assign"]),
		);
		expect([...state.activeIds]).toEqual(["claim_assign"]);
	});

	it("play after end restarts from the beginning", () => {
		const end = runToEnd(trace);
		const state = animationReducer(end, { kind: "play" }, trace);
		expect(state.currentIndex).toBe(-1);
		expect(state.playing).toBe(true);
	});

	it("play with an empty trace stays idle", () => {
		const empty: Trace = { steps: [] };
		const state = animationReducer(
			initialAnimationState(),
			{ kind: "play" },
			empty,
		);
		expect(state.playing).toBe(false);
	});

	it("reset clears firedIds + currentIndex", () => {
		const advanced = animationReducer(
			initialAnimationState(),
			{ kind: "seek", index: 2 },
			trace,
		);
		const reset = animationReducer(advanced, { kind: "reset" }, trace);
		expect(reset.currentIndex).toBe(-1);
		expect(reset.firedIds.size).toBe(0);
	});

	it("stepLabel formats id + optional note", () => {
		expect(stepLabel({ jtbdId: "claim_intake", index: 0 })).toBe("claim_intake");
		expect(
			stepLabel({ jtbdId: "claim_intake", index: 0, note: "submitted" }),
		).toBe("claim_intake — submitted");
		expect(stepLabel(undefined)).toBe("");
	});
});

describe("JobMapAnimation (component)", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});
	afterEach(() => {
		vi.useRealTimers();
	});

	it("renders controls + an idle status before any step has fired", () => {
		render(<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />);
		expect(screen.getByTestId("ff-jobmap-animation")).toBeInTheDocument();
		expect(screen.getByTestId("ff-jobmap-animation-status")).toHaveTextContent(
			"Idle",
		);
		expect(
			screen.getByTestId("ff-jobmap-animation-step-label"),
		).toHaveTextContent("—");
	});

	it("step forward marks the first JTBD active in the canvas", () => {
		render(<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />);
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		const node = screen.getByTestId("ff-jobmap-node-claim_intake");
		expect(node.getAttribute("data-animation-state")).toBe("active");
		const status = screen.getByTestId("ff-jobmap-animation-status");
		expect(status).toHaveTextContent("Active: claim_intake");
	});

	it("step forward then back returns to the previous step", () => {
		render(<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />);
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-back"));
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("active");
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_triage")
				.getAttribute("data-animation-state"),
		).toBe("default");
	});

	it("play tickMs advances one step per tick", () => {
		render(
			<JobMapAnimation
				bundle={sampleBundle()}
				withReactFlow={false}
				tickMs={300}
			/>,
		);
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-play"));
		// First tick — advance to step 0.
		act(() => {
			vi.advanceTimersByTime(300);
		});
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("active");
		// Second tick — advance to step 1; previous step should be in
		// the fired (visited) state.
		act(() => {
			vi.advanceTimersByTime(300);
		});
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("fired");
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_triage")
				.getAttribute("data-animation-state"),
		).toBe("active");
	});

	it("pause halts the play loop without changing the slider", () => {
		render(
			<JobMapAnimation
				bundle={sampleBundle()}
				withReactFlow={false}
				tickMs={250}
			/>,
		);
		const playBtn = screen.getByTestId("ff-jobmap-animation-play");
		fireEvent.click(playBtn);
		act(() => {
			vi.advanceTimersByTime(250);
		});
		// Pause.
		fireEvent.click(playBtn);
		act(() => {
			vi.advanceTimersByTime(1000);
		});
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("active");
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_triage")
				.getAttribute("data-animation-state"),
		).toBe("default");
	});

	it("reset returns to idle from any animation state", () => {
		render(<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />);
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-reset"));
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("default");
		expect(screen.getByTestId("ff-jobmap-animation-status")).toHaveTextContent(
			"Idle",
		);
	});

	it("the slider seeks directly to a target step", () => {
		render(<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />);
		const slider = screen.getByTestId(
			"ff-jobmap-animation-slider",
		) as HTMLInputElement;
		fireEvent.change(slider, { target: { value: "2" } });
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_assign")
				.getAttribute("data-animation-state"),
		).toBe("active");
		// Steps before the active one should be in the fired state.
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("fired");
	});

	it("autoplay starts the animation on mount", () => {
		render(
			<JobMapAnimation
				bundle={sampleBundle()}
				withReactFlow={false}
				autoplay
				tickMs={150}
			/>,
		);
		act(() => {
			vi.advanceTimersByTime(150);
		});
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_intake")
				.getAttribute("data-animation-state"),
		).toBe("active");
	});

	it("calls onStepChange when the active step moves", () => {
		const onStepChange = vi.fn();
		render(
			<JobMapAnimation
				bundle={sampleBundle()}
				withReactFlow={false}
				onStepChange={onStepChange}
			/>,
		);
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		expect(onStepChange).toHaveBeenCalledTimes(2);
		const last = onStepChange.mock.calls.at(-1)?.[0];
		expect(last?.currentIndex).toBe(1);
	});

	it("disables Forward at the end of the trace", () => {
		render(<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />);
		const slider = screen.getByTestId(
			"ff-jobmap-animation-slider",
		) as HTMLInputElement;
		fireEvent.change(slider, { target: { value: "3" } });
		expect(
			(screen.getByTestId("ff-jobmap-animation-step-forward") as HTMLButtonElement)
				.disabled,
		).toBe(true);
	});

	it("custom trace overrides the default topological order", () => {
		const events = ["claim_triage", "claim_intake"]; // intentional reverse
		const customTrace = buildTraceFromEvents(sampleBundle(), events);
		render(
			<JobMapAnimation
				bundle={sampleBundle()}
				trace={customTrace}
				withReactFlow={false}
			/>,
		);
		fireEvent.click(screen.getByTestId("ff-jobmap-animation-step-forward"));
		expect(
			screen
				.getByTestId("ff-jobmap-node-claim_triage")
				.getAttribute("data-animation-state"),
		).toBe("active");
	});
});

describe("JobMapAnimation snapshots", () => {
	it("renders the controls toolbar exactly once", () => {
		const { container } = render(
			<JobMapAnimation bundle={sampleBundle()} withReactFlow={false} />,
		);
		const toolbars = container.querySelectorAll(
			'[data-testid="ff-jobmap-animation-controls"]',
		);
		expect(toolbars).toHaveLength(1);
		// Snapshot of the controls + status section pins the structure
		// that future refactors must preserve. The job-map canvas itself
		// is excluded from the snapshot because reactflow geometry is
		// noisy.
		const controls = container.querySelector(
			'[data-testid="ff-jobmap-animation-controls"]',
		);
		expect(controls?.outerHTML).toMatchSnapshot();
	});
});
