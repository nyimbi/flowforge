/**
 * TS↔Python expression parity conformance test (audit-2026 E-43, invariant 5).
 *
 * Loads the canonical cross-runtime fixture at
 * `framework/tests/cross_runtime/fixtures/expr_parity_v2.json` (250 cases:
 * 200 base + 50 `conditional`-tagged show_if cases) and asserts that
 * `@flowforge/renderer`'s evaluator produces the recorded expected output
 * for every case. The Python side runs the same fixture under pytest in
 * `framework/tests/cross_runtime/test_expr_parity.py`.
 *
 * The legacy `expr_parity_200.json` was retired in v0.3.0 W3 once v2
 * stayed green across W1 + W2 (per `docs/v0.3.0-engineering-plan.md`
 * §11.1 / §13 follow-ups).
 *
 * Regenerate the fixture with:
 *   uv run python framework/tests/cross_runtime/generate_fixture.py
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { evaluate } from "@flowforge/renderer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(
	HERE,
	"..",
	"..",
	"tests",
	"cross_runtime",
	"fixtures",
	"expr_parity_v2.json",
);

interface FixtureCase {
	id: string;
	tag: string;
	expr: unknown;
	ctx: Record<string, unknown>;
	expected: unknown;
}

interface FixtureFile {
	schema_version: string;
	description: string;
	cases: FixtureCase[];
}

function loadFixture(): FixtureFile {
	const raw = readFileSync(FIXTURE_PATH, "utf-8");
	return JSON.parse(raw) as FixtureFile;
}

describe("expr parity fixture (audit-2026 E-43)", () => {
	const fixture = loadFixture();

	it("loads exactly 250 cases", () => {
		expect(fixture.cases).toHaveLength(250);
	});

	it("has unique case ids", () => {
		const ids = new Set(fixture.cases.map((c) => c.id));
		expect(ids.size).toBe(fixture.cases.length);
	});

	it("covers required operator breadth", () => {
		const tags = new Set(fixture.cases.map((c) => c.tag));
		const required = [
			"==",
			"!=",
			"logical",
			"membership",
			"if",
			"length",
			"string",
			"arith",
			"var",
			"coalesce",
			"not_null",
			"composite",
			"conditional",
		];
		for (const tag of required) {
			expect(tags.has(tag)).toBe(true);
		}
	});

	// Per-case parametrized assertions. Vitest reports each id individually.
	it.each(fixture.cases.map((c) => [c.id, c]))(
		"%s: TS evaluator matches Python expected",
		(_id, case_) => {
			const c = case_ as FixtureCase;
			const got = evaluate(c.expr, c.ctx);
			expect(got).toStrictEqual(c.expected);
		},
	);
});
