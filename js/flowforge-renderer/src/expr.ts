/**
 * Tiny whitelisted expression evaluator used by FormRenderer for
 * `visible_if` / `required_if` / `disabled_if` / `computed.expr` clauses.
 *
 * Mirrors the operator subset declared in flowforge-core's expr/evaluator.py
 * to keep frontend + backend behavior aligned.
 *
 * Forms supported:
 *   - bare literals: string, number, boolean, null, array, object
 *   - "$.field.path"     -> read from values
 *   - { op: [arg1, arg2, ...] }
 *
 * Unknown operators throw — never silently return a value.
 */

import type { FormValues } from "./types.js";

const PATH_PREFIX = "$.";

const OPS = new Set([
	"==",
	"!=",
	">",
	">=",
	"<",
	"<=",
	"and",
	"or",
	"not",
	"in",
	"contains",
	"not_null",
	"is_null",
	"if",
	"length",
	"lower",
	"upper",
	"+",
	"-",
	"*",
	"/",
	"%",
	"var",
	"concat",
	"coalesce",
]);

function readPath(values: FormValues, path: string): unknown {
	if (!path.startsWith(PATH_PREFIX)) return undefined;
	const trimmed = path.slice(PATH_PREFIX.length);
	if (trimmed === "") return values;
	const segments = trimmed.split(".");
	let cur: unknown = values;
	for (const seg of segments) {
		if (cur == null || typeof cur !== "object") return undefined;
		cur = (cur as Record<string, unknown>)[seg];
	}
	return cur;
}

function isPathRef(value: unknown): value is string {
	return typeof value === "string" && value.startsWith(PATH_PREFIX);
}

function toNumber(v: unknown): number {
	if (typeof v === "number") return v;
	if (typeof v === "string" && v.trim() !== "") {
		const n = Number(v);
		if (!Number.isNaN(n)) return n;
	}
	if (typeof v === "boolean") return v ? 1 : 0;
	return Number.NaN;
}

export function evaluate(expr: unknown, values: FormValues): unknown {
	if (expr == null) return expr;
	if (isPathRef(expr)) return readPath(values, expr);
	if (typeof expr !== "object") return expr;
	if (Array.isArray(expr)) return expr.map((e) => evaluate(e, values));

	const obj = expr as Record<string, unknown>;
	const keys = Object.keys(obj);
	if (keys.length !== 1) {
		// Plain object literal (e.g. address sub-fields). Return as-is.
		return obj;
	}
	const op = keys[0]!;
	if (!OPS.has(op)) {
		throw new Error(`flowforge.expr: unknown operator "${op}"`);
	}
	const raw = obj[op];
	const args = Array.isArray(raw) ? raw.map((a) => evaluate(a, values)) : [evaluate(raw, values)];

	switch (op) {
		case "==":
			return args[0] === args[1] || (args[0] == null && args[1] == null);
		case "!=":
			return !(args[0] === args[1] || (args[0] == null && args[1] == null));
		case ">":
			return toNumber(args[0]) > toNumber(args[1]);
		case ">=":
			return toNumber(args[0]) >= toNumber(args[1]);
		case "<":
			return toNumber(args[0]) < toNumber(args[1]);
		case "<=":
			return toNumber(args[0]) <= toNumber(args[1]);
		case "and":
			return args.every(Boolean);
		case "or":
			return args.some(Boolean);
		case "not":
			return !args[0];
		case "in":
			if (Array.isArray(args[1])) return args[1].includes(args[0]);
			if (typeof args[1] === "string" && typeof args[0] === "string") return args[1].includes(args[0]);
			return false;
		case "contains":
			if (Array.isArray(args[0])) return args[0].includes(args[1]);
			if (typeof args[0] === "string" && typeof args[1] === "string") return args[0].includes(args[1]);
			return false;
		case "not_null":
			return args[0] !== null && args[0] !== undefined && args[0] !== "";
		case "is_null":
			return args[0] === null || args[0] === undefined || args[0] === "";
		case "if":
			return args[0] ? args[1] : args[2];
		case "length": {
			const v = args[0];
			if (Array.isArray(v) || typeof v === "string") return v.length;
			return 0;
		}
		case "lower":
			return typeof args[0] === "string" ? (args[0] as string).toLowerCase() : args[0];
		case "upper":
			return typeof args[0] === "string" ? (args[0] as string).toUpperCase() : args[0];
		case "+":
			return args.reduce<number>((acc, v) => acc + toNumber(v), 0);
		case "-":
			if (args.length === 1) return -toNumber(args[0]);
			return toNumber(args[0]) - toNumber(args[1]);
		case "*":
			return args.reduce<number>((acc, v) => acc * toNumber(v), 1);
		case "/":
			return toNumber(args[0]) / toNumber(args[1]);
		case "%":
			return toNumber(args[0]) % toNumber(args[1]);
		case "var":
			return typeof args[0] === "string" ? readPath(values, `${PATH_PREFIX}${args[0]}`) : undefined;
		case "concat":
			return args.map((a) => (a == null ? "" : String(a))).join("");
		case "coalesce":
			return args.find((a) => a !== null && a !== undefined && a !== "") ?? null;
		default:
			throw new Error(`flowforge.expr: unhandled operator "${op}"`);
	}
}

export function evaluateBoolean(expr: unknown, values: FormValues, fallback = true): boolean {
	if (expr === undefined || expr === null) return fallback;
	const out = evaluate(expr, values);
	return Boolean(out);
}
