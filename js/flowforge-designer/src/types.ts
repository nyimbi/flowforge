/**
 * Local DSL types for the designer.
 *
 * These mirror the shapes that will eventually live in `@flowforge/types`
 * (U14). Until that package ships, the designer keeps a local copy so it
 * can build and test independently. The shapes track
 * `framework/python/flowforge-core/.../dsl/workflow_def.py` and
 * `form_spec.py` so they round-trip with the Python compiler.
 */

/**
 * Workflow state kinds, mirrored from the Python DSL
 * (`framework/python/flowforge-core/src/flowforge/dsl/workflow_def.py`
 * `StateKind`). audit-2026 JS-05 aligned this union with the canonical
 * server-side enumeration; the legacy `start` / `task` / `review` /
 * `decision` / `wait` / `end` aliases are gone.
 */
export type WorkflowStateKind =
	| "manual_review"
	| "automatic"
	| "parallel_fork"
	| "parallel_join"
	| "timer"
	| "signal_wait"
	| "subworkflow"
	| "terminal_success"
	| "terminal_fail";

export interface EscalationPolicy {
	/** ISO 8601 duration (e.g. `PT24H`). */
	after: string;
	/** Role or named principal to escalate to. */
	to: string;
	notify?: string[];
}

export interface DelegationPolicy {
	allowed_roles: string[];
	require_reason?: boolean;
}

export interface WorkflowState {
	id: string;
	name: string;
	kind: WorkflowStateKind;
	description?: string;
	assignee_role?: string;
	form_id?: string;
	checklist?: ChecklistItem[];
	required_documents?: string[];
	escalation?: EscalationPolicy;
	delegation?: DelegationPolicy;
	sla?: { due_in: string };
}

export interface ChecklistItem {
	id: string;
	label: string;
	required: boolean;
}

export interface GateCondition {
	/** Expression evaluated by `flowforge.expr`. */
	expr: string;
	description?: string;
}

export interface WorkflowTransition {
	id: string;
	from: string;
	to: string;
	event: string;
	guard?: GateCondition;
	required_role?: string;
	emit_audit?: string;
}

export interface WorkflowDef {
	id: string;
	name: string;
	version: number;
	description?: string;
	states: WorkflowState[];
	transitions: WorkflowTransition[];
	initial_state: string;
	terminal_states: string[];
}

// ---------------------------------------------------------------------------
// Form spec
// ---------------------------------------------------------------------------

export type FieldKind =
	| "text"
	| "textarea"
	| "number"
	| "money"
	| "boolean"
	| "date"
	| "enum"
	| "lookup"
	| "file"
	| "email";

export interface FieldOption {
	value: string;
	label: string;
}

export interface ConditionalRule {
	/** Field id whose value the rule reacts to. */
	when_field: string;
	op: "eq" | "neq" | "gt" | "lt" | "in" | "not_in" | "is_null" | "not_null";
	value?: unknown;
	/** Action to apply when the condition matches. */
	action: "show" | "hide" | "require" | "optional";
}

export interface FieldDef {
	id: string;
	label: string;
	kind: FieldKind;
	required?: boolean;
	help?: string;
	placeholder?: string;
	default?: unknown;
	options?: FieldOption[];
	pii?: boolean;
	min?: number;
	max?: number;
	pattern?: string;
	rules?: ConditionalRule[];
}

export interface FormSpec {
	id: string;
	name: string;
	version: number;
	fields: FieldDef[];
}

// ---------------------------------------------------------------------------
// Validation + simulation
// ---------------------------------------------------------------------------

export interface ValidationIssue {
	severity: "error" | "warning";
	path: string;
	message: string;
	code: string;
}

export interface SimulationStep {
	from: string;
	to: string;
	event: string;
	at: number;
}

export interface SimulationResult {
	trace: SimulationStep[];
	terminated: boolean;
	final_state: string | null;
}

// ---------------------------------------------------------------------------
// Diff
// ---------------------------------------------------------------------------

export type DiffChangeKind = "added" | "removed" | "modified";

export interface DiffEntry {
	kind: DiffChangeKind;
	path: string;
	before?: unknown;
	after?: unknown;
}
