/**
 * AJV-backed validator for FormSpec values.
 *
 * Compiles a per-spec JSON schema from FormField declarations and surfaces
 * field-keyed error strings the renderer renders inline.
 */

import Ajv2020, { type ErrorObject } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import type { FormErrors, FormField, FormValues, RendererFormSpec } from "../types.js";

type AjvInstance = InstanceType<typeof Ajv2020>;

function buildAjv(): AjvInstance {
	const ajv = new Ajv2020({ allErrors: true, strict: false, useDefaults: false, coerceTypes: false });
	(addFormats as unknown as (a: AjvInstance) => void)(ajv);
	return ajv;
}

function fieldSchema(field: FormField): Record<string, unknown> {
	const v = (field.validation ?? {}) as Record<string, unknown>;
	const min = typeof v.min === "number" ? (v.min as number) : undefined;
	const max = typeof v.max === "number" ? (v.max as number) : undefined;
	const minLength = typeof v.min_length === "number" ? (v.min_length as number) : undefined;
	const maxLength = typeof v.max_length === "number" ? (v.max_length as number) : undefined;
	const pattern = typeof v.pattern === "string" ? (v.pattern as string) : undefined;

	const base: Record<string, unknown> = {};
	switch (field.kind) {
		case "text":
		case "textarea":
		case "rich_text":
		case "signature":
		case "address":
		case "color":
		case "hidden":
			base.type = "string";
			if (minLength !== undefined) base.minLength = minLength;
			if (maxLength !== undefined) base.maxLength = maxLength;
			if (pattern !== undefined) base.pattern = pattern;
			break;
		case "email":
			base.type = "string";
			base.format = "email";
			break;
		case "url":
			base.type = "string";
			base.format = "uri";
			break;
		case "phone":
			base.type = "string";
			base.pattern = pattern ?? "^[+0-9 ()-]{4,}$";
			break;
		case "number":
		case "percentage":
			base.type = "number";
			if (min !== undefined) base.minimum = min;
			if (max !== undefined) base.maximum = max;
			break;
		case "money": {
			// Money values can be entered as a bare number or as a
			// `{ amount, currency }` object — accept either shape.
			const numberShape: Record<string, unknown> = { type: "number" };
			if (min !== undefined) numberShape.minimum = min;
			if (max !== undefined) numberShape.maximum = max;
			const objectShape: Record<string, unknown> = {
				type: "object",
				required: ["amount"],
				properties: {
					amount: { type: "number", ...(min !== undefined ? { minimum: min } : {}), ...(max !== undefined ? { maximum: max } : {}) },
					currency: { type: "string" },
				},
			};
			base.oneOf = [numberShape, objectShape];
			break;
		}
		case "boolean":
			base.type = "boolean";
			break;
		case "date":
			base.type = "string";
			base.format = "date";
			break;
		case "datetime":
			base.type = "string";
			base.format = "date-time";
			break;
		case "enum":
		case "party_ref":
		case "party_picker":
		case "document_ref":
		case "document_picker":
		case "lookup":
			base.type = "string";
			if (Array.isArray(field.options) && field.options.length > 0) {
				base.enum = field.options.map((o) => o.v);
			}
			break;
		case "multi_select":
			base.type = "array";
			base.items =
				Array.isArray(field.options) && field.options.length > 0
					? { type: "string", enum: field.options.map((o) => o.v) }
					: { type: "string" };
			if (min !== undefined) base.minItems = min;
			if (max !== undefined) base.maxItems = max;
			break;
		case "file":
			base.type = "object";
			break;
		case "json":
			break;
		default:
			base.type = "string";
	}
	return base;
}

function specSchema(spec: RendererFormSpec): Record<string, unknown> {
	const props: Record<string, unknown> = {};
	const required: string[] = [];
	for (const f of spec.fields) {
		const s = fieldSchema(f);
		if (!f.required) {
			props[f.id] = { anyOf: [s, { type: "null" }] };
		} else {
			props[f.id] = s;
			required.push(f.id);
		}
	}
	return {
		$schema: "https://json-schema.org/draft/2020-12/schema",
		type: "object",
		properties: props,
		required,
		additionalProperties: true,
	};
}

export interface ValidatorBundle {
	validate: (values: FormValues) => FormErrors;
	rawErrors: () => ErrorObject[] | null | undefined;
}

export function buildValidator(spec: RendererFormSpec): ValidatorBundle {
	const ajv = buildAjv();
	const schema = specSchema(spec);
	const fn = ajv.compile(schema);
	return {
		validate(values: FormValues): FormErrors {
			fn(values);
			const errors: FormErrors = {};
			for (const err of fn.errors ?? []) {
				let key = "";
				if (err.instancePath) {
					key = err.instancePath.replace(/^\//, "").split("/")[0] ?? "";
				}
				if (!key && err.keyword === "required") {
					key = (err.params as { missingProperty?: string }).missingProperty ?? "";
				}
				if (!key) key = "_form";
				if (!errors[key]) {
					errors[key] = humanize(err);
				}
			}
			return errors;
		},
		rawErrors() {
			return fn.errors;
		},
	};
}

function humanize(err: ErrorObject): string {
	switch (err.keyword) {
		case "required":
			return "Required";
		case "type":
			return `Expected ${(err.params as { type?: string }).type}`;
		case "minLength":
			return `Must be at least ${(err.params as { limit?: number }).limit} characters`;
		case "maxLength":
			return `Must be at most ${(err.params as { limit?: number }).limit} characters`;
		case "minimum":
			return `Must be at least ${(err.params as { limit?: number }).limit}`;
		case "maximum":
			return `Must be at most ${(err.params as { limit?: number }).limit}`;
		case "pattern":
			return "Invalid format";
		case "format":
			return `Invalid ${(err.params as { format?: string }).format}`;
		case "enum":
			return "Not an allowed value";
		case "minItems":
			return `Select at least ${(err.params as { limit?: number }).limit}`;
		case "maxItems":
			return `Select at most ${(err.params as { limit?: number }).limit}`;
		default:
			return err.message ?? "Invalid";
	}
}
