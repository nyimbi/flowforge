"""One-shot builder for ``expr_parity_v2.json``.

Reads the existing 200 cases from ``expr_parity_200.json``, appends 50
``conditional``-tagged cases that exercise show_if-shaped expressions
(`{var: "context.X"}` patterns plus their composite variants), and
writes ``expr_parity_v2.json``.

The 50 new cases cover:

* truthy / falsy boolean reads (12 cases)
* number comparisons (13 cases)
* string equality (12 cases)
* missing-var → null fallback (13 cases)

Reuses only the existing operator catalogue — no new ops are introduced.
``var``, ``and``, ``or``, ``not``, ``if``, ``==``, ``!=``, ``>``, ``>=``,
``<``, ``<=``, ``in``, ``not_null``, ``coalesce`` are the operators
exercised. ``is_null`` is intentionally excluded (Python-side
unregistered, see audit-2026 E-43 catalogue exclusions).

Run:

    uv run python framework/tests/cross_runtime/_build_fixture_v2.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowforge.expr import evaluate

V1_PATH = Path(__file__).parent / "fixtures" / "expr_parity_200.json"
V2_PATH = Path(__file__).parent / "fixtures" / "expr_parity_v2.json"


def _id(n: int) -> str:
	return f"cond-{n:03d}"


def _conditional_cases() -> list[dict[str, Any]]:
	# (expr, ctx) tuples; ``expected`` is materialised by running the
	# Python evaluator so the file remains the source-of-truth fixture.
	specs: list[tuple[Any, dict[str, Any]]] = []

	# --- truthy / falsy boolean reads (12) ---
	specs += [
		({"var": "active"}, {"active": True}),
		({"var": "active"}, {"active": False}),
		({"var": "context.active"}, {"context": {"active": True}}),
		({"var": "context.active"}, {"context": {"active": False}}),
		({"not": [{"var": "context.disabled"}]}, {"context": {"disabled": False}}),
		({"not": [{"var": "context.disabled"}]}, {"context": {"disabled": True}}),
		({"and": [{"var": "context.a"}, {"var": "context.b"}]}, {"context": {"a": True, "b": True}}),
		({"and": [{"var": "context.a"}, {"var": "context.b"}]}, {"context": {"a": True, "b": False}}),
		({"or": [{"var": "context.a"}, {"var": "context.b"}]}, {"context": {"a": False, "b": True}}),
		({"or": [{"var": "context.a"}, {"var": "context.b"}]}, {"context": {"a": False, "b": False}}),
		({"if": [{"var": "context.flag"}, "on", "off"]}, {"context": {"flag": True}}),
		({"if": [{"var": "context.flag"}, "on", "off"]}, {"context": {"flag": False}}),
	]
	# --- number comparisons (13) ---
	specs += [
		({">": [{"var": "context.amount"}, 100]}, {"context": {"amount": 200}}),
		({">": [{"var": "context.amount"}, 100]}, {"context": {"amount": 50}}),
		({">=": [{"var": "context.amount"}, 100]}, {"context": {"amount": 100}}),
		({"<": [{"var": "context.amount"}, 100]}, {"context": {"amount": 50}}),
		({"<=": [{"var": "context.amount"}, 100]}, {"context": {"amount": 100}}),
		({"==": [{"var": "context.amount"}, 100]}, {"context": {"amount": 100}}),
		({"==": [{"var": "context.amount"}, 100]}, {"context": {"amount": 99}}),
		({"!=": [{"var": "context.amount"}, 100]}, {"context": {"amount": 99}}),
		({">": [{"var": "context.large_loss"}, 100000]}, {"context": {"large_loss": 150000}}),
		({">": [{"var": "context.large_loss"}, 100000]}, {"context": {"large_loss": 50000}}),
		({"<": [{"var": "context.score"}, 0]}, {"context": {"score": -5}}),
		({">": [{"var": "context.score"}, 0]}, {"context": {"score": 0}}),
		({"==": [{"var": "context.tier"}, 2]}, {"context": {"tier": 2}}),
	]
	# --- string equality (12) ---
	specs += [
		({"==": [{"var": "context.status"}, "approved"]}, {"context": {"status": "approved"}}),
		({"==": [{"var": "context.status"}, "approved"]}, {"context": {"status": "pending"}}),
		({"!=": [{"var": "context.status"}, "rejected"]}, {"context": {"status": "approved"}}),
		({"==": [{"var": "context.role"}, "supervisor"]}, {"context": {"role": "supervisor"}}),
		({"==": [{"var": "context.role"}, "supervisor"]}, {"context": {"role": "adjuster"}}),
		({"==": [{"var": "context.country"}, "US"]}, {"context": {"country": "US"}}),
		({"==": [{"var": "context.country"}, "US"]}, {"context": {"country": "CA"}}),
		({"==": [{"var": "context.lane"}, "fast"]}, {"context": {"lane": "fast"}}),
		({"in": [{"var": "context.role"}, ["adjuster", "supervisor"]]}, {"context": {"role": "supervisor"}}),
		({"in": [{"var": "context.role"}, ["adjuster", "supervisor"]]}, {"context": {"role": "claimant"}}),
		({"==": [{"var": "context.empty_string"}, ""]}, {"context": {"empty_string": ""}}),
		({"!=": [{"var": "context.empty_string"}, "x"]}, {"context": {"empty_string": ""}}),
	]
	# --- missing-var → null fallback (13) ---
	specs += [
		({"var": "missing"}, {}),
		({"var": "context.missing"}, {"context": {}}),
		({"var": "context.deeply.nested.missing"}, {"context": {}}),
		({"var": "context.missing"}, {}),
		({"==": [{"var": "context.missing"}, None]}, {"context": {}}),
		({"!=": [{"var": "context.missing"}, "x"]}, {"context": {}}),
		({"!=": [{"var": "context.missing"}, None]}, {"context": {}}),
		({"not_null": [{"var": "context.missing"}]}, {"context": {}}),
		({"not_null": [{"var": "context.present"}]}, {"context": {"present": "x"}}),
		({"coalesce": [{"var": "context.missing"}, "fallback"]}, {"context": {}}),
		({"coalesce": [{"var": "context.present"}, "fallback"]}, {"context": {"present": "value"}}),
		(
			{
				"and": [
					{"not_null": [{"var": "context.x"}]},
					{">": [{"var": "context.x"}, 0]},
				]
			},
			{"context": {"x": 5}},
		),
		(
			{
				"or": [
					{"not_null": [{"var": "context.missing"}]},
					{"==": [{"var": "context.fallback"}, "yes"]},
				]
			},
			{"context": {"fallback": "yes"}},
		),
	]

	assert len(specs) == 50, f"expected 50 conditional specs, got {len(specs)}"

	out: list[dict[str, Any]] = []
	for i, (expr, ctx) in enumerate(specs, start=1):
		expected = evaluate(expr, ctx)
		out.append(
			{
				"id": _id(i),
				"tag": "conditional",
				"expr": expr,
				"ctx": ctx,
				"expected": expected,
			}
		)
	return out


def main() -> None:
	v1 = json.loads(V1_PATH.read_text())
	cases = list(v1["cases"])
	assert len(cases) == 200, len(cases)

	cases.extend(_conditional_cases())
	assert len(cases) == 250, len(cases)

	# Stable sort by id so diffs stay readable. ``cond-NNN`` sorts after
	# every existing prefix because the existing ids use prefixes like
	# ``arith-`` / ``var-`` / ``logical-`` that lexically dominate; sorted
	# yields a clean append-only diff vs v1.
	cases.sort(key=lambda c: c["id"])
	# Verify all ids unique.
	ids = [c["id"] for c in cases]
	assert len(set(ids)) == len(ids), "duplicate ids"
	# Verify every conditional case has tag=='conditional'.
	cond = [c for c in cases if c["tag"] == "conditional"]
	assert len(cond) == 50, f"expected 50 conditional cases, got {len(cond)}"

	V2_PATH.parent.mkdir(parents=True, exist_ok=True)
	V2_PATH.write_text(
		json.dumps(
			{
				"schema_version": "2.0",
				"description": (
					"audit-2026 E-43 / v0.3.0 W1 (item 13) cross-runtime expression conformance fixture; "
					"250 (expr, ctx, expected) tuples that flowforge.expr (Python) and "
					"@flowforge/renderer (TS) must agree on byte-for-byte. The 200 base cases "
					"mirror expr_parity_200.json; the 50 `conditional`-tagged cases exercise "
					"show_if-shaped expressions emitted by the W1 form_renderer='real' path. "
					"Regenerate via `uv run python framework/tests/cross_runtime/_build_fixture_v2.py`."
				),
				"cases": cases,
			},
			indent="\t",
			ensure_ascii=False,
		)
		+ "\n"
	)
	print(f"wrote {len(cases)} cases to {V2_PATH}")


if __name__ == "__main__":
	main()
