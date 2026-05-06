import type { JtbdBundle } from "./types.js";

/**
 * Worked example used by tests + Storybook (when wired in E-7).
 * Three actors, four JTBDs with non-trivial dependency edges spanning
 * lanes, exercising every layout branch (lane grouping, depth, cross-
 * lane edge).
 */
export const sampleBundle = (): JtbdBundle => ({
	project: {
		name: "claims-intake",
		package: "claims_intake",
		domain: "insurance",
		tenancy: "multi",
	},
	shared: {
		roles: ["intake_clerk", "triage_officer", "claims_supervisor"],
	},
	jtbds: [
		{
			id: "claim_intake",
			title: "Submit a new motor claim",
			actor: { role: "intake_clerk", department: "claims" },
			situation: "A policyholder calls in after an accident.",
			motivation: "Open claim quickly so adjuster can triage within SLA.",
			outcome: "A triage-ready claim record exists.",
			success_criteria: ["Required documents uploaded.", "Loss amount captured."],
		},
		{
			id: "claim_triage",
			title: "Triage a fresh claim",
			actor: { role: "triage_officer" },
			situation: "Fresh claim arrives in queue.",
			motivation: "Route within SLA.",
			outcome: "Assignee set, severity tagged.",
			success_criteria: ["Severity assigned"],
			requires: ["claim_intake"],
		},
		{
			id: "claim_assign",
			title: "Assign to claims handler",
			actor: { role: "triage_officer" },
			situation: "Triaged claim awaits assignment.",
			motivation: "Match severity with handler skill.",
			outcome: "Claim has owner.",
			success_criteria: ["Handler selected"],
			requires: ["claim_triage"],
		},
		{
			id: "claim_approve",
			title: "Approve claim payout",
			actor: { role: "claims_supervisor" },
			situation: "Handler proposes a payout figure.",
			motivation: "Authorise within authority tier.",
			outcome: "Payout approved or escalated.",
			success_criteria: ["Authority tier honoured"],
			requires: ["claim_assign"],
		},
	],
});
