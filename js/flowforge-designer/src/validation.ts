import type { ValidationIssue, WorkflowDef } from "./types.js";

/**
 * Static validator for workflow definitions.
 *
 * Mirrors the rules that `flowforge.compiler.validator` enforces server-side
 * so the designer can show the same problems while editing. The validator
 * is intentionally pure — pass in a workflow, get back issues.
 */
export const validateWorkflow = (wf: WorkflowDef): ValidationIssue[] => {
	const issues: ValidationIssue[] = [];

	if (!wf.id) {
		issues.push({
			severity: "error",
			path: "id",
			message: "Workflow id is required",
			code: "WF_ID_MISSING",
		});
	}
	if (!wf.name) {
		issues.push({
			severity: "warning",
			path: "name",
			message: "Workflow name is empty",
			code: "WF_NAME_EMPTY",
		});
	}

	const stateIds = new Set<string>();
	for (const s of wf.states) {
		if (stateIds.has(s.id)) {
			issues.push({
				severity: "error",
				path: `states/${s.id}`,
				message: `Duplicate state id "${s.id}"`,
				code: "STATE_DUP",
			});
		}
		stateIds.add(s.id);
	}

	if (wf.states.length > 0) {
		if (!wf.initial_state) {
			issues.push({
				severity: "error",
				path: "initial_state",
				message: "Workflow has states but no initial_state",
				code: "WF_NO_INITIAL",
			});
		} else if (!stateIds.has(wf.initial_state)) {
			issues.push({
				severity: "error",
				path: "initial_state",
				message: `initial_state "${wf.initial_state}" does not match any state`,
				code: "WF_INITIAL_UNKNOWN",
			});
		}
	}

	for (const term of wf.terminal_states) {
		if (!stateIds.has(term)) {
			issues.push({
				severity: "error",
				path: `terminal_states/${term}`,
				message: `terminal_state "${term}" does not match any state`,
				code: "WF_TERMINAL_UNKNOWN",
			});
		}
	}

	const transitionIds = new Set<string>();
	for (const t of wf.transitions) {
		if (transitionIds.has(t.id)) {
			issues.push({
				severity: "error",
				path: `transitions/${t.id}`,
				message: `Duplicate transition id "${t.id}"`,
				code: "TRANS_DUP",
			});
		}
		transitionIds.add(t.id);
		if (!stateIds.has(t.from)) {
			issues.push({
				severity: "error",
				path: `transitions/${t.id}/from`,
				message: `Transition "${t.id}" from unknown state "${t.from}"`,
				code: "TRANS_FROM_UNKNOWN",
			});
		}
		if (!stateIds.has(t.to)) {
			issues.push({
				severity: "error",
				path: `transitions/${t.id}/to`,
				message: `Transition "${t.id}" to unknown state "${t.to}"`,
				code: "TRANS_TO_UNKNOWN",
			});
		}
		if (!t.event) {
			issues.push({
				severity: "warning",
				path: `transitions/${t.id}/event`,
				message: `Transition "${t.id}" has no event name`,
				code: "TRANS_EVENT_EMPTY",
			});
		}
	}

	// Reachability: states with no incoming transitions (other than the initial)
	// and no outgoing transitions (other than terminal) are likely orphaned.
	const incoming = new Map<string, number>();
	const outgoing = new Map<string, number>();
	for (const t of wf.transitions) {
		incoming.set(t.to, (incoming.get(t.to) ?? 0) + 1);
		outgoing.set(t.from, (outgoing.get(t.from) ?? 0) + 1);
	}
	const terminalSet = new Set(wf.terminal_states);
	for (const s of wf.states) {
		const hasIn = (incoming.get(s.id) ?? 0) > 0 || s.id === wf.initial_state;
		const hasOut = (outgoing.get(s.id) ?? 0) > 0 || terminalSet.has(s.id);
		if (!hasIn) {
			issues.push({
				severity: "warning",
				path: `states/${s.id}`,
				message: `State "${s.id}" is unreachable (no incoming transitions)`,
				code: "STATE_UNREACHABLE",
			});
		}
		if (!hasOut) {
			issues.push({
				severity: "warning",
				path: `states/${s.id}`,
				message: `State "${s.id}" is a dead end (no outgoing transitions and not terminal)`,
				code: "STATE_DEAD_END",
			});
		}
	}

	return issues;
};
