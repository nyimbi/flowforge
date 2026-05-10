"""Generate the TS↔Python expression-parity conformance fixture (v2).

audit-2026 E-43, architecture invariant 5: 250 (expr, ctx, expected) tuples
that both evaluators must produce byte-identical outputs for. The Python
evaluator is the source of truth — we materialise expected outputs by
running it, serialise to JSON, and the JS test loads the same file.

The fixture only exercises the operator subset that has deterministic
JSON-input parity between flowforge-core (Python) and flowforge-renderer
(TS). Operators with runtime-specific coercion (`+` on strings,
`length` on non-strings, `lower`/`upper` on non-strings, JS-only
`concat` / `is_null`, Python-only `between` / `starts_with` /
`ends_with` / `is_empty`) are excluded.

The 200-case base layer mirrors what was the legacy ``expr_parity_200.json``
fixture (retired in v0.3.0 W3 per ``docs/v0.3.0-engineering-plan.md``
§11.1). The 50 ``conditional``-tagged cases were added in v0.3.0 W1
(item 13) to cover ``show_if``-shaped expressions emitted by the
``form_renderer = "real"`` Step.tsx path. No new operators are exercised
by the conditional layer — ``var``, ``and``, ``or``, ``not``, ``if``,
``==``, ``!=``, ``>``, ``>=``, ``<``, ``<=``, ``in``, ``not_null``,
``coalesce`` only.

Run::

	uv run python framework/tests/cross_runtime/generate_fixture.py

The fixture is checked in. Regenerate when the operator catalogue changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowforge.expr import evaluate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "expr_parity_v2.json"


def _id(prefix: str, n: int) -> str:
	return f"{prefix}-{n:03d}"


def _eq_cases() -> list[dict[str, Any]]:
	"""Strict equality across JSON types (audit-2026 JS-02 parity)."""

	cases: list[tuple[Any, Any, bool]] = [
		(1, 1, True),
		(1, 2, False),
		(0, 0, True),
		(-1, -1, True),
		(1.5, 1.5, True),
		(1.5, 1.6, False),
		("a", "a", True),
		("a", "b", False),
		("", "", True),
		(True, True, True),
		(False, False, True),
		(True, False, False),
		(None, None, True),
	]
	out: list[dict[str, Any]] = []
	for i, (a, b, expected) in enumerate(cases, start=1):
		out.append(
			{
				"id": _id("eq", i),
				"tag": "==",
				"expr": {"==": [a, b]},
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _ne_cases() -> list[dict[str, Any]]:
	cases: list[tuple[Any, Any, bool]] = [
		(1, 2, True),
		(1, 1, False),
		("a", "b", True),
		("a", "a", False),
		(None, None, False),
		(True, False, True),
		(0, 0, False),
		(0, 1, True),
	]
	return [
		{
			"id": _id("ne", i),
			"tag": "!=",
			"expr": {"!=": [a, b]},
			"ctx": {},
			"expected": expected,
		}
		for i, (a, b, expected) in enumerate(cases, start=1)
	]


def _cmp_cases() -> list[dict[str, Any]]:
	"""Same-type numeric / string comparisons. Mixed types excluded — JS coerces, Python raises."""

	out: list[dict[str, Any]] = []
	tests = [
		(">", 5, 3, True),
		(">", 3, 5, False),
		(">", 0, 0, False),
		(">=", 5, 5, True),
		(">=", 4, 5, False),
		(">=", 6, 5, True),
		("<", 3, 5, True),
		("<", 5, 3, False),
		("<", 5, 5, False),
		("<=", 5, 5, True),
		("<=", 6, 5, False),
		("<=", 4, 5, True),
		(">", "b", "a", True),
		("<", "a", "b", True),
		(">=", "abc", "abc", True),
		("<=", "abc", "abd", True),
	]
	for i, (op, a, b, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id(f"cmp_{op}", i),
				"tag": f"cmp:{op}",
				"expr": {op: [a, b]},
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _logical_cases() -> list[dict[str, Any]]:
	out: list[dict[str, Any]] = []
	tests = [
		({"and": [True, True]}, True),
		({"and": [True, False]}, False),
		({"and": [True, True, True]}, True),
		({"and": [True, True, False]}, False),
		({"and": []}, True),
		({"or": [False, False]}, False),
		({"or": [False, True]}, True),
		({"or": [False, False, True]}, True),
		({"or": []}, False),
		({"not": True}, False),
		({"not": False}, True),
		({"not": [True]}, False),
		({"and": [{"not": False}, {"or": [False, True]}]}, True),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("logic", i),
				"tag": "logical",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _membership_cases() -> list[dict[str, Any]]:
	out: list[dict[str, Any]] = []
	tests = [
		({"in": ["a", ["a", "b", "c"]]}, True),
		({"in": ["d", ["a", "b", "c"]]}, False),
		({"in": [1, [1, 2, 3]]}, True),
		({"in": [4, [1, 2, 3]]}, False),
		({"in": ["ell", "hello"]}, True),
		({"in": ["zzz", "hello"]}, False),
		({"contains": [["a", "b", "c"], "b"]}, True),
		({"contains": [["a", "b", "c"], "z"]}, False),
		({"contains": ["hello world", "world"]}, True),
		({"contains": ["hello world", "zzz"]}, False),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("membership", i),
				"tag": "membership",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _if_cases() -> list[dict[str, Any]]:
	out: list[dict[str, Any]] = []
	tests = [
		({"if": [True, "yes", "no"]}, "yes"),
		({"if": [False, "yes", "no"]}, "no"),
		({"if": [{"==": [1, 1]}, "eq", "neq"]}, "eq"),
		({"if": [{"==": [1, 2]}, "eq", "neq"]}, "neq"),
		({"if": [True, 100, 200]}, 100),
		({"if": [False, 100, 200]}, 200),
		({"if": [{">": [5, 3]}, {"+": [10, 5]}, {"+": [1, 1]}]}, 15),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("if", i),
				"tag": "if",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _length_cases() -> list[dict[str, Any]]:
	"""Length on strings + arrays (parity domain).

	Array values come via ``var`` because the ``{"length": [...]}`` shape
	is interpreted as a multi-arg call by both runtimes (the audit-2026
	E-35 arity check now rejects this in Python).
	"""

	ctx = {
		"three": [1, 2, 3],
		"empty_arr": [],
		"matrix": [[1, 2], [3, 4], [5, 6]],
		"nested": ["a", "b"],
	}
	out: list[dict[str, Any]] = []
	tests: list[tuple[dict[str, Any], dict[str, Any], Any]] = [
		({}, {"length": "hello"}, 5),
		({}, {"length": ""}, 0),
		(ctx, {"length": {"var": "three"}}, 3),
		(ctx, {"length": {"var": "empty_arr"}}, 0),
		(ctx, {"length": {"var": "matrix"}}, 3),
		({}, {"length": "a"}, 1),
		(ctx, {"length": {"var": "nested"}}, 2),
	]
	for i, (case_ctx, expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("length", i),
				"tag": "length",
				"expr": expr,
				"ctx": case_ctx,
				"expected": expected,
			}
		)
	return out


def _string_cases() -> list[dict[str, Any]]:
	"""lower/upper on string inputs only (non-string semantics differ)."""

	out: list[dict[str, Any]] = []
	tests = [
		({"lower": "ABC"}, "abc"),
		({"lower": "abc"}, "abc"),
		({"lower": "Hello World"}, "hello world"),
		({"lower": ""}, ""),
		({"upper": "abc"}, "ABC"),
		({"upper": "ABC"}, "ABC"),
		({"upper": "Hello"}, "HELLO"),
		({"upper": ""}, ""),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("string", i),
				"tag": "string",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _arith_cases() -> list[dict[str, Any]]:
	"""Numeric arithmetic only — strings would diverge (JS coerces)."""

	out: list[dict[str, Any]] = []
	tests = [
		({"+": [1, 2]}, 3),
		({"+": [1, 2, 3, 4]}, 10),
		({"+": [0]}, 0),
		({"+": [-1, 1]}, 0),
		({"+": [1.5, 2.5]}, 4.0),
		({"-": [10, 4]}, 6),
		({"-": [0, 5]}, -5),
		({"-": [3.5, 1.5]}, 2.0),
		({"*": [2, 3]}, 6),
		({"*": [2, 3, 4]}, 24),
		({"*": [0, 100]}, 0),
		({"*": [1.5, 2]}, 3.0),
		({"/": [10, 2]}, 5.0),
		({"/": [9, 3]}, 3.0),
		({"/": [1, 2]}, 0.5),
		({"%": [10, 3]}, 1),
		({"%": [9, 3]}, 0),
		({"%": [7, 5]}, 2),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("arith", i),
				"tag": "arith",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _var_cases() -> list[dict[str, Any]]:
	"""var paths over a shared ctx — both runtimes resolve identically."""

	ctx = {
		"user": {"id": 42, "name": "Ada", "active": True},
		"items": ["a", "b", "c"],
		"score": 87.5,
		"zero": 0,
		"empty": "",
		"null_field": None,
	}
	out: list[dict[str, Any]] = []
	tests = [
		({"var": "user.id"}, 42),
		({"var": "user.name"}, "Ada"),
		({"var": "user.active"}, True),
		({"var": "score"}, 87.5),
		({"var": "zero"}, 0),
		({"var": "empty"}, ""),
		({"var": "null_field"}, None),
		({"var": "missing"}, None),
		({"var": "user.missing"}, None),
		({">": [{"var": "score"}, 80]}, True),
		({"==": [{"var": "user.name"}, "Ada"]}, True),
		({"and": [{"var": "user.active"}, {">": [{"var": "user.id"}, 0]}]}, True),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("var", i),
				"tag": "var",
				"expr": expr,
				"ctx": ctx,
				"expected": expected,
			}
		)
	return out


def _coalesce_cases() -> list[dict[str, Any]]:
	"""coalesce skipping null only — empty strings excluded (JS skips them too)."""

	out: list[dict[str, Any]] = []
	tests = [
		({"coalesce": [None, "a"]}, "a"),
		({"coalesce": [None, None, "fallback"]}, "fallback"),
		({"coalesce": ["first", None, "second"]}, "first"),
		({"coalesce": [None, 0, 1]}, 0),
		({"coalesce": [None, False, True]}, False),
		({"coalesce": [1, 2, 3]}, 1),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("coalesce", i),
				"tag": "coalesce",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _not_null_cases() -> list[dict[str, Any]]:
	"""not_null on inputs where JS extras (empty-string→falsy) don't differ."""

	ctx = {"x": 1, "s": "hello", "n": None, "arr": [1, 2]}
	out: list[dict[str, Any]] = []
	tests = [
		({"not_null": {"var": "x"}}, True),
		({"not_null": {"var": "s"}}, True),
		({"not_null": {"var": "n"}}, False),
		({"not_null": {"var": "arr"}}, True),
		({"not_null": {"var": "missing"}}, False),
		({"not_null": 0}, True),
		({"not_null": False}, True),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("not_null", i),
				"tag": "not_null",
				"expr": expr,
				"ctx": ctx,
				"expected": expected,
			}
		)
	return out


def _composite_cases() -> list[dict[str, Any]]:
	"""Realistic guard expressions — combinations of the above."""

	ctx = {
		"order": {
			"amount": 250,
			"currency": "USD",
			"status": "approved",
			"items": [
				{"sku": "ABC", "qty": 2},
				{"sku": "XYZ", "qty": 1},
			],
		},
		"user": {"role": "admin", "tier": 3, "verified": True},
		"flags": {"beta": True, "throttle": False},
		"limits": {"daily": 1000, "weekly": 5000},
	}
	out: list[dict[str, Any]] = []
	tests = [
		(
			{
				"and": [
					{">": [{"var": "order.amount"}, 100]},
					{"==": [{"var": "order.currency"}, "USD"]},
				]
			},
			True,
		),
		(
			{
				"and": [
					{">": [{"var": "order.amount"}, 100]},
					{"==": [{"var": "order.currency"}, "EUR"]},
				]
			},
			False,
		),
		(
			{"or": [{"==": [{"var": "user.role"}, "admin"]}, {"var": "flags.beta"}]},
			True,
		),
		(
			{"if": [{"var": "user.verified"}, "approved", "pending"]},
			"approved",
		),
		(
			{"if": [{">": [{"var": "user.tier"}, 2]}, "premium", "basic"]},
			"premium",
		),
		(
			{"length": {"var": "order.items"}},
			2,
		),
		(
			{
				"and": [
					{"<=": [{"var": "order.amount"}, {"var": "limits.daily"}]},
					{"<=": [{"var": "order.amount"}, {"var": "limits.weekly"}]},
				]
			},
			True,
		),
		(
			{"not": {"var": "flags.throttle"}},
			True,
		),
		(
			{
				"and": [
					{"not_null": {"var": "user.role"}},
					{"in": [{"var": "user.role"}, ["admin", "manager"]]},
				]
			},
			True,
		),
		(
			{
				"or": [
					{"==": [{"var": "order.status"}, "approved"]},
					{"==": [{"var": "order.status"}, "shipped"]},
				]
			},
			True,
		),
		(
			{"+": [{"var": "order.amount"}, 100, 50]},
			400,
		),
		(
			{"-": [{"var": "limits.daily"}, {"var": "order.amount"}]},
			750,
		),
		(
			{"coalesce": [{"var": "order.discount"}, 0]},
			0,
		),
		(
			{"coalesce": [None, {"var": "order.currency"}]},
			"USD",
		),
		(
			{"if": [{"and": [{"var": "user.verified"}, {">": [{"var": "user.tier"}, 1]}]}, "ok", "deny"]},
			"ok",
		),
	]
	for i, (expr, expected) in enumerate(tests, start=1):
		out.append(
			{
				"id": _id("composite", i),
				"tag": "composite",
				"expr": expr,
				"ctx": ctx,
				"expected": expected,
			}
		)
	return out


def _filler_cases(target: int) -> list[dict[str, Any]]:
	"""Fill remaining slots up to *target* with quick mechanical variations."""

	out: list[dict[str, Any]] = []
	for i in range(1, target + 1):
		# Cycle through a few simple shapes — exercise int range + composition.
		if i % 4 == 0:
			expr: dict[str, Any] = {"==": [i, i]}
			expected: Any = True
		elif i % 4 == 1:
			expr = {"+": [i, 1]}
			expected = i + 1
		elif i % 4 == 2:
			expr = {"if": [{">": [i, 0]}, "p", "n"]}
			expected = "p"
		else:
			expr = {"and": [{">": [i, 0]}, {"<": [i, 1000]}]}
			expected = True
		out.append(
			{
				"id": _id("filler", i),
				"tag": "filler",
				"expr": expr,
				"ctx": {},
				"expected": expected,
			}
		)
	return out


def _cond_id(n: int) -> str:
	return f"cond-{n:03d}"


def _conditional_cases() -> list[dict[str, Any]]:
	"""``show_if``-shaped expressions for the W1 ``form_renderer = "real"`` path.

	No new operators; only ``var``, ``and``, ``or``, ``not``, ``if``,
	``==``, ``!=``, ``>``, ``>=``, ``<``, ``<=``, ``in``, ``not_null``,
	``coalesce`` are exercised. Originally introduced in v0.3.0 W1
	(item 13) via ``_build_fixture_v2.py`` — folded into this builder
	when v1 was retired in W3.
	"""

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
				"id": _cond_id(i),
				"tag": "conditional",
				"expr": expr,
				"ctx": ctx,
				"expected": expected,
			}
		)
	return out


def build_cases(target: int = 250) -> list[dict[str, Any]]:
	cases: list[dict[str, Any]] = []
	cases.extend(_eq_cases())
	cases.extend(_ne_cases())
	cases.extend(_cmp_cases())
	cases.extend(_logical_cases())
	cases.extend(_membership_cases())
	cases.extend(_if_cases())
	cases.extend(_length_cases())
	cases.extend(_string_cases())
	cases.extend(_arith_cases())
	cases.extend(_var_cases())
	cases.extend(_coalesce_cases())
	cases.extend(_not_null_cases())
	cases.extend(_composite_cases())
	# Top up the 200-case base layer with mechanical filler if needed,
	# then append the 50 conditional cases on top.
	base_target = target - 50
	if len(cases) < base_target:
		cases.extend(_filler_cases(base_target - len(cases)))
	cases = cases[:base_target]
	cases.extend(_conditional_cases())

	# Recompute expected via the Python evaluator — single source of truth.
	# This catches authoring drift between the hand-written expected and what
	# the live evaluator yields. JS must match the recomputed values.
	for case in cases:
		got = evaluate(case["expr"], case["ctx"])
		# Floating-point: keep author's expected to avoid 5.0 vs 5 surprise.
		# But sanity-check equality.
		assert got == case["expected"], (
			f"author/python drift in {case['id']}: expected={case['expected']!r} got={got!r}"
		)
	return cases


def main() -> None:
	cases = build_cases(250)
	assert len(cases) == 250, len(cases)
	FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
	# Stable sort by id so diffs are readable.
	cases.sort(key=lambda c: c["id"])
	# Verify all ids unique.
	ids = [c["id"] for c in cases]
	assert len(set(ids)) == len(ids), "duplicate ids"
	# Verify exactly 50 conditional cases.
	cond = [c for c in cases if c["tag"] == "conditional"]
	assert len(cond) == 50, f"expected 50 conditional cases, got {len(cond)}"
	FIXTURE_PATH.write_text(
		json.dumps(
			{
				"schema_version": "2.0",
				"description": (
					"audit-2026 E-43 / v0.3.0 W1 (item 13) cross-runtime expression conformance fixture; "
					"250 (expr, ctx, expected) tuples that flowforge.expr (Python) and "
					"@flowforge/renderer (TS) must agree on byte-for-byte. The 200 base cases "
					"mirror the legacy `expr_parity_200.json` (retired in v0.3.0 W3); the 50 "
					"`conditional`-tagged cases exercise show_if-shaped expressions emitted by "
					"the W1 form_renderer='real' path. Regenerate via "
					"`uv run python framework/tests/cross_runtime/generate_fixture.py`."
				),
				"cases": cases,
			},
			indent="\t",
			ensure_ascii=False,
		)
		+ "\n"
	)
	print(f"wrote {len(cases)} cases to {FIXTURE_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
	main()
