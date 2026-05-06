/**
 * TypeScript projection of the canonical JTBD bundle shape.
 *
 * Mirrors `framework/python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py`
 * (E-1). The editor is a JS package, so we restate the shape here rather
 * than depend on the Python schema at compile time. Field names and
 * enums match exactly so a `JtbdBundle` parsed from JSON validates as
 * a `JtbdBundleView`.
 *
 * Only the fields the editor consumes today are typed; future fields
 * (`metrics`, `compliance`, …) flow through opaquely until a feature
 * needs them.
 */

export type FieldKind =
	| "text"
	| "number"
	| "money"
	| "date"
	| "datetime"
	| "enum"
	| "boolean"
	| "party_ref"
	| "document_ref"
	| "email"
	| "phone"
	| "address"
	| "textarea"
	| "signature"
	| "file";

export type EdgeCaseHandle =
	| "branch"
	| "reject"
	| "escalate"
	| "compensate"
	| "loop";

export type ApprovalPolicy =
	| "1_of_1"
	| "2_of_2"
	| "n_of_m"
	| "authority_tier";

export type NotificationTrigger =
	| "state_enter"
	| "state_exit"
	| "sla_warn"
	| "sla_breach"
	| "approved"
	| "rejected"
	| "escalated";

export type NotificationChannel =
	| "email"
	| "sms"
	| "slack"
	| "webhook"
	| "in_app";

export type TenancyMode = "none" | "single" | "multi";

export type DataSensitivity = "PII" | "PHI" | "PCI" | "secrets" | "regulated";

export type ComplianceRegime =
	| "GDPR"
	| "SOX"
	| "HIPAA"
	| "PCI-DSS"
	| "ISO27001"
	| "SOC2"
	| "NIST-800-53"
	| "CCPA";

export type JtbdSpecStatus =
	| "draft"
	| "in_review"
	| "published"
	| "deprecated"
	| "archived";

export interface JtbdActor {
	role: string;
	department?: string;
	external?: boolean;
}

export interface JtbdField {
	id: string;
	kind: FieldKind;
	label?: string;
	required?: boolean;
	pii?: boolean;
	sensitivity?: DataSensitivity[];
}

export interface JtbdEdgeCase {
	id: string;
	condition: string;
	handle: EdgeCaseHandle;
	branch_to?: string;
}

export interface JtbdApproval {
	role: string;
	policy: ApprovalPolicy;
	n?: number;
	tier?: number;
}

export interface JtbdSla {
	warn_pct?: number;
	breach_seconds?: number;
}

export interface JtbdNotification {
	trigger: NotificationTrigger;
	channel: NotificationChannel;
	audience: string;
}

export interface JtbdSpec {
	id: string;
	title?: string;
	version?: string;
	spec_hash?: string;
	parent_version_id?: string | null;
	replaced_by?: string | null;
	status?: JtbdSpecStatus;
	actor: JtbdActor;
	situation: string;
	motivation: string;
	outcome: string;
	success_criteria: string[];
	edge_cases?: JtbdEdgeCase[];
	data_capture?: JtbdField[];
	approvals?: JtbdApproval[];
	sla?: JtbdSla | null;
	notifications?: JtbdNotification[];
	requires?: string[];
	compliance?: ComplianceRegime[];
	data_sensitivity?: DataSensitivity[];
}

export interface JtbdProject {
	name: string;
	package: string;
	domain: string;
	tenancy?: TenancyMode;
	languages?: string[];
	currencies?: string[];
}

export interface JtbdShared {
	roles?: string[];
	permissions?: string[];
}

export interface JtbdBundle {
	project: JtbdProject;
	shared?: JtbdShared;
	jtbds: JtbdSpec[];
}
