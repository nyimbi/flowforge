/**
 * Pure animation engine — no React, no DOM, no timers.
 *
 * The component layer (`<JobMapAnimation />`) drives a `setInterval`
 * tick that calls `advanceStep`, but the state machine itself is a
 * pure function from `(state, action) => state`. That keeps the unit
 * tests deterministic (no fake timers required for state assertions)
 * and makes the same engine reusable from a server-side preview /
 * snapshot test.
 *
 * State shape:
 *
 *   * `currentIndex` — `-1` before the first step has run; `0..steps-1`
 *     while iterating; `steps.length-1` once the trace is complete.
 *   * `playing` — true while the play loop is ticking.
 *   * `firedIds` — set of every JTBD id that has been or is currently
 *     active. Lets the canvas distinguish fired-already (faded) from
 *     active (highlighted) from pending (default).
 *   * `activeIds` — JTBD ids currently active (always `0` or `1` for
 *     the dry-run trace; future fault-injection traces may flag two
 *     simultaneously).
 *
 * The same shape is what `<JobMap />` reads via `highlightedIds` /
 * `firedIds` props.
 */

import type { Trace, TraceStep } from "./trace.js";

export interface AnimationState {
	currentIndex: number;
	playing: boolean;
	firedIds: Set<string>;
	activeIds: Set<string>;
}

export type AnimationAction =
	| { kind: "play" }
	| { kind: "pause" }
	| { kind: "reset" }
	| { kind: "step_forward" }
	| { kind: "step_back" }
	| { kind: "seek"; index: number };

/** Initial state — nothing has fired yet. */
export function initialAnimationState(): AnimationState {
	return {
		currentIndex: -1,
		playing: false,
		firedIds: new Set<string>(),
		activeIds: new Set<string>(),
	};
}

/**
 * Reduce one action against the current state.
 *
 * The reducer is total (every action × state pair is defined) and
 * never throws. Out-of-range seeks clamp to the trace bounds.
 */
export function animationReducer(
	state: AnimationState,
	action: AnimationAction,
	trace: Trace,
): AnimationState {
	const total = trace.steps.length;
	switch (action.kind) {
		case "play": {
			if (total === 0) {
				return state;
			}
			// If we're already at the end, restart from -1 so the next
			// step kicks the slider forward.
			if (state.currentIndex >= total - 1) {
				return { ...initialAnimationState(), playing: true };
			}
			return { ...state, playing: true };
		}
		case "pause":
			return { ...state, playing: false };
		case "reset":
			return initialAnimationState();
		case "step_forward": {
			if (total === 0 || state.currentIndex >= total - 1) {
				return { ...state, playing: false };
			}
			const nextIndex = state.currentIndex + 1;
			return advanceTo(trace, nextIndex, state.playing);
		}
		case "step_back": {
			if (state.currentIndex <= -1) {
				return state;
			}
			const prevIndex = state.currentIndex - 1;
			return advanceTo(trace, prevIndex, state.playing);
		}
		case "seek": {
			if (total === 0) {
				return state;
			}
			const clamped = Math.max(-1, Math.min(action.index, total - 1));
			return advanceTo(trace, clamped, state.playing);
		}
	}
}

/**
 * Compute fired/active sets for a target step index. `-1` means
 * "before any step has run" (nothing fired, nothing active).
 *
 * Past steps live in `firedIds`; the step at `index` is the active
 * one (also in `firedIds` so the canvas treats it as visited).
 */
function advanceTo(
	trace: Trace,
	index: number,
	playing: boolean,
): AnimationState {
	if (index < 0) {
		return { ...initialAnimationState(), playing };
	}
	const fired = new Set<string>();
	for (let i = 0; i <= index; i++) {
		const step = trace.steps[i];
		if (step !== undefined) {
			fired.add(step.jtbdId);
		}
	}
	const active = new Set<string>();
	const cur = trace.steps[index];
	if (cur !== undefined) {
		active.add(cur.jtbdId);
	}
	return {
		currentIndex: index,
		playing,
		firedIds: fired,
		activeIds: active,
	};
}

/** Convenience: run the trace to completion synchronously. Used by
 * the snapshot tests to assert the final fired set. */
export function runToEnd(trace: Trace): AnimationState {
	const total = trace.steps.length;
	if (total === 0) {
		return initialAnimationState();
	}
	return advanceTo(trace, total - 1, false);
}

/** Pull the human-readable label for a step (id, falling back to
 * `note` when present). */
export function stepLabel(step: TraceStep | undefined): string {
	if (step === undefined) {
		return "";
	}
	return step.note ? `${step.jtbdId} — ${step.note}` : step.jtbdId;
}
