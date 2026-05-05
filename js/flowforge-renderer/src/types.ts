/**
 * Renderer-local form types.
 *
 * The schema-generated `FormSpec` in @flowforge/types only enumerates the
 * 16 kinds declared in `form_spec.schema.json`. The renderer accepts a
 * structurally compatible superset that adds renderer-only kinds
 * (rich_text, multi_select, color, percentage, json, hidden, url,
 * party_picker, document_picker). It also adds optional UI metadata
 * (help, placeholder, conditions, computed expressions).
 *
 * Both the schema-canonical FormSpec and this superset render correctly.
 */

export type FieldKind =
	| "text"
	| "textarea"
	| "number"
	| "money"
	| "date"
	| "datetime"
	| "boolean"
	| "enum"
	| "multi_select"
	| "file"
	| "signature"
	| "rich_text"
	| "party_ref"
	| "party_picker"
	| "document_ref"
	| "document_picker"
	| "address"
	| "phone"
	| "email"
	| "url"
	| "color"
	| "percentage"
	| "json"
	| "hidden"
	| "lookup";

export interface FieldOption {
	v: string;
	label?: string;
}

export interface FieldValidation {
	min?: number;
	max?: number;
	min_length?: number;
	max_length?: number;
	pattern?: string;
	currency?: string;
	max_size_bytes?: number;
	accept?: string[];
	[k: string]: unknown;
}

export interface FieldSource {
	hook?: string;
	arg?: string;
	[k: string]: unknown;
}

export interface ComputedSpec {
	expr: unknown;
}

export interface FormField {
	id: string;
	kind: FieldKind | string;
	label?: string;
	help?: string;
	placeholder?: string;
	required?: boolean;
	pii?: boolean;
	default?: unknown;
	options?: FieldOption[];
	validation?: FieldValidation | Record<string, unknown>;
	source?: FieldSource | Record<string, unknown>;
	visible_if?: unknown;
	required_if?: unknown;
	disabled_if?: unknown;
	computed?: ComputedSpec;
	meta?: Record<string, unknown>;
}

export interface LayoutSection {
	kind: "section";
	title?: string;
	field_ids: string[];
}

export interface RendererFormSpec {
	id: string;
	version: string;
	title: string;
	fields: FormField[];
	layout?: LayoutSection[];
}

export type FormValues = Record<string, unknown>;
export type FormErrors = Record<string, string>;

/**
 * Async lookup hook signature. The renderer wires hooks through the
 * `lookups` prop on FormRenderer; field's `source.hook` selects which one.
 */
export type LookupHook = (input: {
	field: FormField;
	values: FormValues;
	query?: string;
	signal?: AbortSignal;
}) => Promise<FieldOption[]>;

export interface LookupRegistry {
	[hookName: string]: LookupHook;
}
