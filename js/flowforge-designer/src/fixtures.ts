import type { FormSpec, WorkflowDef } from "./types.js";

/**
 * Three-state demo workflow used by tests, the simulator smoke check, and the
 * package README example.
 */
export const sampleWorkflow = (): WorkflowDef => ({
	id: "wf-claim-intake",
	name: "Claim intake",
	version: 1,
	description: "Submit → review → close",
	initial_state: "submitted",
	terminal_states: ["closed"],
	states: [
		// audit-2026 JS-05: kinds aligned with the Python DSL union.
		{ id: "submitted", name: "Submitted", kind: "automatic" },
		{
			id: "in_review",
			name: "In review",
			kind: "manual_review",
			assignee_role: "reviewer",
			form_id: "claim-review",
			checklist: [{ id: "chk-id", label: "Identity verified", required: true }],
			required_documents: ["claim_form.pdf"],
			escalation: { after: "PT24H", to: "supervisor" },
			delegation: { allowed_roles: ["reviewer", "supervisor"], require_reason: true },
		},
		{ id: "closed", name: "Closed", kind: "terminal_success" },
	],
	transitions: [
		{ id: "t1", from: "submitted", to: "in_review", event: "begin_review" },
		{ id: "t2", from: "in_review", to: "closed", event: "approve" },
		{
			id: "t3",
			from: "in_review",
			to: "submitted",
			event: "request_changes",
			required_role: "reviewer",
		},
	],
});

export const sampleForm = (): FormSpec => ({
	id: "claim-review",
	name: "Claim review",
	version: 1,
	fields: [
		{ id: "claim_id", label: "Claim id", kind: "text", required: true },
		{ id: "amount", label: "Amount", kind: "money", required: true },
		{
			id: "category",
			label: "Category",
			kind: "enum",
			options: [
				{ value: "auto", label: "Auto" },
				{ value: "home", label: "Home" },
			],
		},
		{ id: "notes", label: "Notes", kind: "textarea" },
	],
});
