"""Expression evaluator + operator coverage."""

from __future__ import annotations

import pytest

from flowforge.expr import EvaluationError, evaluate, register_op


def test_literals_pass_through() -> None:
	assert evaluate(1, {}) == 1
	assert evaluate("a", {}) == "a"
	assert evaluate(None, {}) is None
	assert evaluate(True, {}) is True


def test_var_resolves_dotted_path() -> None:
	ctx = {"a": {"b": {"c": 7}}}
	assert evaluate({"var": "a.b.c"}, ctx) == 7
	assert evaluate({"var": "a.b.missing"}, ctx) is None
	assert evaluate({"var": "missing"}, ctx) is None


def test_basic_operators() -> None:
	ctx = {"x": 5, "y": "hello"}
	assert evaluate({">": [{"var": "x"}, 3]}, ctx) is True
	assert evaluate({"==": ["a", "a"]}, ctx) is True
	assert evaluate({"and": [True, True, True]}, ctx) is True
	assert evaluate({"or": [False, False, True]}, ctx) is True
	assert evaluate({"not": False}, ctx) is True
	assert evaluate({"not_null": {"var": "x"}}, ctx) is True
	assert evaluate({"length": {"var": "y"}}, ctx) == 5
	assert evaluate({"upper": {"var": "y"}}, ctx) == "HELLO"
	assert evaluate({"lower": "FOO"}, ctx) == "foo"
	assert evaluate({"+": [1, 2, 3]}, ctx) == 6
	assert evaluate({"if": [True, "x", "y"]}, ctx) == "x"
	assert evaluate({"between": [5, 1, 10]}, ctx) is True
	assert evaluate({"contains": ["hello", "ell"]}, ctx) is True


def test_evaluation_error_for_bad_var() -> None:
	with pytest.raises(EvaluationError):
		evaluate({"var": 123}, {})


def test_register_op_extends() -> None:
	register_op("double", lambda x: x * 2)
	assert evaluate({"double": 4}, {}) == 8


def test_at_least_25_builtins_registered() -> None:
	from flowforge.expr.evaluator import _OPS  # noqa: SLF001
	assert len(_OPS) >= 25, sorted(_OPS.keys())
