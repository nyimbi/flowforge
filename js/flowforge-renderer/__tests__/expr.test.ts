import { describe, expect, it } from "vitest";
import { evaluate, evaluateBoolean } from "../src/expr.js";

describe("expr.evaluate", () => {
	const v = { age: 30, name: "Ada", tags: ["x", "y"], nested: { ok: true } };

	it("reads a path ref", () => {
		expect(evaluate("$.age", v)).toBe(30);
		expect(evaluate("$.nested.ok", v)).toBe(true);
		expect(evaluate("$.missing", v)).toBeUndefined();
	});

	it("supports comparison ops", () => {
		expect(evaluate({ "==": ["$.age", 30] }, v)).toBe(true);
		expect(evaluate({ "!=": ["$.age", 31] }, v)).toBe(true);
		expect(evaluate({ ">": ["$.age", 18] }, v)).toBe(true);
		expect(evaluate({ ">=": ["$.age", 30] }, v)).toBe(true);
		expect(evaluate({ "<": ["$.age", 100] }, v)).toBe(true);
		expect(evaluate({ "<=": ["$.age", 30] }, v)).toBe(true);
	});

	it("supports logical ops", () => {
		expect(evaluate({ and: [true, { ">": ["$.age", 18] }] }, v)).toBe(true);
		expect(evaluate({ or: [false, false] }, v)).toBe(false);
		expect(evaluate({ not: false }, v)).toBe(true);
	});

	it("supports membership ops", () => {
		expect(evaluate({ in: ["x", "$.tags"] }, v)).toBe(true);
		expect(evaluate({ contains: ["$.tags", "y"] }, v)).toBe(true);
		expect(evaluate({ contains: ["$.name", "Ad"] }, v)).toBe(true);
	});

	it("not_null + is_null + if + length", () => {
		expect(evaluate({ not_null: "$.name" }, v)).toBe(true);
		expect(evaluate({ is_null: "$.missing" }, v)).toBe(true);
		expect(evaluate({ if: [true, "yes", "no"] }, v)).toBe("yes");
		expect(evaluate({ length: "$.tags" }, v)).toBe(2);
	});

	it("string + arithmetic ops", () => {
		expect(evaluate({ lower: "ABC" }, v)).toBe("abc");
		expect(evaluate({ upper: "abc" }, v)).toBe("ABC");
		expect(evaluate({ "+": [1, 2, 3] }, v)).toBe(6);
		expect(evaluate({ "-": [10, 4] }, v)).toBe(6);
		expect(evaluate({ "*": [2, 3, 4] }, v)).toBe(24);
		expect(evaluate({ "/": [10, 2] }, v)).toBe(5);
		expect(evaluate({ "%": [10, 3] }, v)).toBe(1);
		expect(evaluate({ concat: ["a", "$.name"] }, v)).toBe("aAda");
		expect(evaluate({ coalesce: [null, "", "$.name"] }, v)).toBe("Ada");
	});

	it("rejects unknown operators", () => {
		expect(() => evaluate({ "$$danger": [1] }, v)).toThrow(/unknown operator/);
	});

	it("evaluateBoolean falls back when expr is undefined", () => {
		expect(evaluateBoolean(undefined, v, true)).toBe(true);
		expect(evaluateBoolean(undefined, v, false)).toBe(false);
		expect(evaluateBoolean({ "==": ["$.age", 30] }, v)).toBe(true);
	});
});
