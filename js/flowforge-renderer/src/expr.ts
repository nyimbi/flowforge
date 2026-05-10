/**
 * Tiny whitelisted expression evaluator used by FormRenderer for
 * `visible_if` / `required_if` / `disabled_if` / `computed.expr` clauses.
 *
 * Mirrors the operator subset declared in flowforge-core's expr/evaluator.py
 * to keep frontend + backend behavior aligned. The cross-runtime conformance
 * fixture at `framework/tests/cross_runtime/fixtures/expr_parity_v2.json`
 * (250 cases) exercises both runtimes with byte-identical expected outputs
 * (audit-2026 E-43, architecture invariant 5). The legacy 200-case
 * `expr_parity_200.json` was retired in v0.3.0 W3.
 *
 * Forms supported:
 *   - bare literals: string, number, boolean, null, array, object
 *   - "$.field.path"     -> read from values
 *   - { op: [arg1, arg2, ...] }
 *
 * Unknown operator semantics (audit-2026 JS-01, post-fix):
 *   - return false. Fail-safe — guards using `evaluateBoolean` collapse
 *     to false rather than throwing into a UI render path.
 *
 * Equality semantics (audit-2026 JS-02, post-fix):
 *   - strict equality only (`===` / `!==`). Loose null-equality removed
 *     so JSON-typed inputs compare identically to the Python `_eq` op.
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
	if (!path.startsWith(PATH_PREFIX)) return null;
	const trimmed = path.slice(PATH_PREFIX.length);
	if (trimmed === "") return values;
	const segments = trimmed.split(".");
	let cur: unknown = values;
	for (const seg of segments) {
		if (cur == null || typeof cur !== "object") return null;
		const next = (cur as Record<string, unknown>)[seg];
		if (next === undefined) return null; // audit-2026 E-43: null parity with Python None
		cur = next;
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

/**
 * Same-type ordered compare. Strings → lexicographic, numbers → numeric.
 * Mixed types fall back to numeric coercion (matches the legacy JS surface
 * but diverges from Python; the cross-runtime fixture avoids mixed types).
 *
 * Returns the sign: -1 if a<b, 0 if equal, 1 if a>b.
 */
function orderedCompare(a: unknown, b: unknown): number {
	if (typeof a === "string" && typeof b === "string") {
		if (a < b) return -1;
		if (a > b) return 1;
		return 0;
	}
	const na = toNumber(a);
	const nb = toNumber(b);
	if (na < nb) return -1;
	if (na > nb) return 1;
	return 0;
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
		// audit-2026 JS-01: unknown ops fall through to false instead of
		// throwing. Guards (`evaluateBoolean`) collapse to false rather than
		// crashing the render path; this also avoids a parity divergence
		// with the Python evaluator's "literal dict" surface (truthy in JS,
		// truthy in Python).
		return false;
	}
	const raw = obj[op];
	const args = Array.isArray(raw) ? raw.map((a) => evaluate(a, values)) : [evaluate(raw, values)];

	switch (op) {
		case "==":
			// audit-2026 JS-02: strict equality only. Loose null-equality
			// removed so JSON-typed inputs match the Python `_eq` operator.
			return args[0] === args[1];
		case "!=":
			return args[0] !== args[1];
		case ">":
			return orderedCompare(args[0], args[1]) > 0;
		case ">=":
			return orderedCompare(args[0], args[1]) >= 0;
		case "<":
			return orderedCompare(args[0], args[1]) < 0;
		case "<=":
			return orderedCompare(args[0], args[1]) <= 0;
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
