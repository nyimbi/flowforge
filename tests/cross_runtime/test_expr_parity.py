"""TS↔Python expression-parity conformance test (audit-2026 E-43, invariant 5).

Loads the cross-runtime fixture and asserts that the Python evaluator
produces the recorded expected output for every case. The TypeScript side
runs the same fixture under vitest in
``framework/js/flowforge-integration-tests/expr-parity.test.ts``.

The fixture moved from ``expr_parity_200.json`` (200 base cases) to
``expr_parity_v2.json`` (250 cases) in v0.3.0 W1 / item 13. The 50 new
``conditional``-tagged cases exercise ``show_if``-shaped expressions
emitted by the ``form_renderer = "real"`` Step.tsx path. The legacy v1
file remains in-tree until W3 retires it (per the engineering plan
§13 follow-ups).

Regenerate the fixture with::

	uv run python framework/tests/cross_runtime/_build_fixture_v2.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from flowforge.expr import evaluate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "expr_parity_v2.json"


def _load_fixture() -> list[dict[str, Any]]:
	data = json.loads(FIXTURE_PATH.read_text())
	cases = data["cases"]
	assert isinstance(cases, list)
	return cases


def test_fixture_has_250_cases() -> None:
	cases = _load_fixture()
	assert len(cases) == 250, f"expected 250 cases, got {len(cases)}"


def test_fixture_ids_are_unique() -> None:
	cases = _load_fixture()
	ids = [c["id"] for c in cases]
	assert len(ids) == len(set(ids)), "duplicate ids in fixture"


def test_fixture_covers_minimum_operator_breadth() -> None:
	"""Cross-runtime parity is meaningless if we only exercise one op."""

	cases = _load_fixture()
	tags = {c["tag"] for c in cases}
	# Each is a class of operator the evaluator must handle identically.
	required = {
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
	}
	missing = required - tags
	assert not missing, f"fixture missing tags: {missing}"


@pytest.mark.parametrize("case", _load_fixture(), ids=lambda c: c["id"])
def test_python_evaluator_matches_fixture(case: dict[str, Any]) -> None:
	"""Each fixture case: Python evaluate(expr, ctx) == case.expected."""

	got = evaluate(case["expr"], case["ctx"])
	assert got == case["expected"], (
		f"{case['id']}: tag={case['tag']} expr={case['expr']!r} "
		f"ctx={case['ctx']!r} expected={case['expected']!r} got={got!r}"
	)
