import { describe, expect, it } from "vitest";
import { buildValidator } from "../src/validators/ajv.js";
import type { RendererFormSpec } from "../src/types.js";

const spec: RendererFormSpec = {
	id: "claim_intake",
	version: "1.0.0",
	title: "Claim intake",
	fields: [
		{ id: "claimant_name", kind: "text", required: true, validation: { min_length: 2 } },
		{ id: "claimant_email", kind: "email", required: true },
		{ id: "amount", kind: "money", required: true, validation: { currency: "USD", min: 1 } },
		{ id: "incident_date", kind: "date", required: true },
		{ id: "category", kind: "enum", required: true, options: [{ v: "auto" }, { v: "home" }] },
		{ id: "tags", kind: "multi_select", options: [{ v: "fire" }, { v: "flood" }] },
		{ id: "agree", kind: "boolean", required: true },
	],
};

describe("buildValidator", () => {
	it("flags every required field when empty", () => {
		const v = buildValidator(spec);
		const errs = v.validate({});
		expect(errs).toMatchObject({
			claimant_name: "Required",
			claimant_email: "Required",
			amount: "Required",
			incident_date: "Required",
			category: "Required",
			agree: "Required",
		});
	});

	it("validates email format", () => {
		const v = buildValidator(spec);
		const errs = v.validate({
			claimant_name: "Ada",
			claimant_email: "not-an-email",
			amount: { amount: 5, currency: "USD" },
			incident_date: "2024-01-01",
			category: "auto",
			agree: true,
		});
		expect(errs.claimant_email).toMatch(/Invalid email/);
	});

	it("accepts a fully valid payload", () => {
		const v = buildValidator(spec);
		const errs = v.validate({
			claimant_name: "Ada",
			claimant_email: "ada@example.com",
			amount: { amount: 5, currency: "USD" },
			incident_date: "2024-01-01",
			category: "auto",
			tags: ["fire"],
			agree: true,
		});
		expect(errs).toEqual({});
	});

	it("rejects out-of-enum values", () => {
		const v = buildValidator(spec);
		const errs = v.validate({
			claimant_name: "Ada",
			claimant_email: "ada@example.com",
			amount: { amount: 5, currency: "USD" },
			incident_date: "2024-01-01",
			category: "ufo",
			agree: true,
		});
		expect(errs.category).toMatch(/Not an allowed value/);
	});
});
