import type {
	SimulationResult,
	SimulationStep,
	WorkflowDef,
} from "./types.js";

export interface SimulationInput {
	/** Ordered list of events to fire from the initial state. */
	events: string[];
	/** Cap on iterations to prevent infinite loops in cyclic workflows. */
	maxSteps?: number;
}

/**
 * Linear simulator: walks a workflow def by firing events one at a time,
 * picking the first matching transition out of the current state.
 *
 * Mirrors `flowforge.replay.simulator` semantics for the lightweight cases
 * the designer needs (smoke-testing a draft before publish). Guard
 * expressions are not evaluated here — that requires the full
 * `flowforge.expr` evaluator and a context object.
 */
export const simulate = (
	wf: WorkflowDef,
	input: SimulationInput,
): SimulationResult => {
	const trace: SimulationStep[] = [];
	const max = input.maxSteps ?? 256;
	const terminalSet = new Set(wf.terminal_states);

	let current = wf.initial_state;
	if (!current) {
		return { trace: [], terminated: false, final_state: null };
	}

	for (let i = 0; i < input.events.length; i++) {
		if (trace.length >= max) break;
		const event = input.events[i];
		const next = wf.transitions.find(
			(t) => t.from === current && t.event === event,
		);
		if (!next) {
			// Event does not match any transition out of the current state — stop.
			break;
		}
		trace.push({ from: current, to: next.to, event, at: i });
		current = next.to;
		if (terminalSet.has(current)) {
			return { trace, terminated: true, final_state: current };
		}
	}

	return {
		trace,
		terminated: terminalSet.has(current),
		final_state: current,
	};
};
