"""Expression evaluator + operator coverage.

Covers audit-2026 E-35:

* C-06 — operator registry is frozen at module init; post-import
  ``register_op`` raises :class:`RegistryFrozenError`.
* C-07 — every op declares arity; wrong-arity calls raise
  :class:`ArityMismatchError` (compile-time via ``check_arity``,
  runtime fallback in ``evaluate``).
"""

from __future__ import annotations

import pytest

from flowforge.expr import (
	ArityMismatchError,
	EvaluationError,
	RegistryFrozenError,
	check_arity,
	evaluate,
	ops_registry,
	register_op,
)
from flowforge.expr.evaluator import _OPS, _test_only_unfreeze, get_op_spec


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


def test_var_resolves_list_indexes_and_rejects_bad_indexes() -> None:
	ctx = {"rows": [{"name": "first"}, {"name": "second"}]}
	assert evaluate({"var": "rows.1.name"}, ctx) == "second"
	assert evaluate({"var": "rows.nope.name"}, ctx) is None
	assert evaluate({"var": "rows.4.name"}, ctx) is None


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


def test_remaining_builtin_operator_semantics() -> None:
	assert evaluate({"!=": [1, 2]}, {}) is True
	assert evaluate({">=": [2, 2]}, {}) is True
	assert evaluate({"<": [1, 2]}, {}) is True
	assert evaluate({"<=": [2, 2]}, {}) is True
	assert evaluate({"+": []}, {}) == 0
	assert evaluate({"-": [7, 3]}, {}) == 4
	assert evaluate({"*": [2, 3, 4]}, {}) == 24
	assert evaluate({"*": []}, {}) == 1
	assert evaluate({"/": [8, 2]}, {}) == 4
	assert evaluate({"%": [7, 3]}, {}) == 1
	assert evaluate({"in": ["x", ["x", "y"]]}, {}) is True
	assert evaluate({"in": ["x", None]}, {}) is False
	assert evaluate({"length": None}, {}) == 0
	assert evaluate({"coalesce": [None, None, "first"]}, {}) == "first"
	assert evaluate({"coalesce": []}, {}) is None
	assert evaluate({"is_empty": None}, {}) is True
	assert evaluate({"is_empty": {"var": "empty"}}, {"empty": []}) is True
	assert evaluate({"is_empty": 123}, {}) is False
	assert evaluate({"starts_with": ["claim-123", "claim"]}, {}) is True
	assert evaluate({"ends_with": ["claim-123", "123"]}, {}) is True


def test_operator_failure_wraps_as_evaluation_error() -> None:
	with pytest.raises(EvaluationError, match="operator `/` failed"):
		evaluate({"/": [1, 0]}, {})


def test_evaluation_error_for_bad_var() -> None:
	with pytest.raises(EvaluationError):
		evaluate({"var": 123}, {})


def test_register_op_extends_under_test_only_unfreeze() -> None:
	"""Production runs see a frozen registry. Tests can register inside a
	scoped unfreeze that restores prior state on exit (audit-2026 E-35)."""

	with _test_only_unfreeze():
		register_op("double", lambda x: x * 2, arity=1)
		assert evaluate({"double": 4}, {}) == 8
	# After exit, the test-registered op is gone — registry restored.
	assert evaluate({"double": 4}, {}) == {"double": 4}


def test_register_op_infers_default_and_variadic_arity_under_test_unfreeze() -> None:
	def defaulted(a: int, b: int = 10) -> int:
		return a + b

	def variadic(prefix: str, *items: object) -> str:
		return f"{prefix}:{len(items)}"

	def keyword_only(a: int, *, flag: bool = False, **kwargs: object) -> tuple[int, bool, dict[str, object]]:
		return a, flag, kwargs

	with _test_only_unfreeze():
		register_op("defaulted", defaulted)
		register_op("variadic", variadic)
		register_op("keyword_only", keyword_only)
		assert evaluate({"defaulted": [2]}, {}) == 12
		assert evaluate({"defaulted": [2, 3]}, {}) == 5
		assert evaluate({"variadic": ["n", 1, 2, 3]}, {}) == "n:3"
		assert evaluate({"keyword_only": 7}, {}) == (7, False, {})
		assert check_arity({"defaulted": []})
		assert check_arity({"defaulted": [1, 2, 3]})
		assert check_arity({"keyword_only": [1, 2]})


def test_register_op_rejects_invalid_arity_declarations_under_test_unfreeze() -> None:
	with _test_only_unfreeze():
		with pytest.raises(ValueError, match="arity_min"):
			register_op("bad_min", lambda: None, arity=(-1, 1))
		with pytest.raises(ValueError, match="cannot be <"):
			register_op("bad_max", lambda: None, arity=(2, 1))


def test_at_least_25_builtins_registered() -> None:
	from flowforge.expr.evaluator import _OPS  # noqa: SLF001

	assert len(_OPS) >= 25, sorted(_OPS.keys())
	assert "and" in _OPS
	assert "definitely_missing" not in _OPS


# ---- C-06 frozen registry ---------------------------------------------


def test_C_06_op_registry_frozen() -> None:
	"""Post-import register_op must raise RegistryFrozenError."""

	with pytest.raises(RegistryFrozenError):
		register_op("never_registered", lambda: None, arity=0)


def test_C_06_ops_view_is_immutable() -> None:
	"""The exported _OPS mapping is read-only (no __setitem__)."""

	with pytest.raises((TypeError, AttributeError)):
		_OPS["mut"] = lambda: None  # type: ignore[index]


def test_C_06_ops_registry_view_is_immutable_and_exposes_specs() -> None:
	registry = ops_registry()
	assert registry["if"].arity_min == 2
	assert registry["if"].arity_max == 3
	with pytest.raises(TypeError):
		registry["mut"] = registry["if"]  # type: ignore[index]


def test_C_06_legacy_ops_mapping_exposes_registered_functions() -> None:
	assert callable(_OPS["if"])
	assert list(iter(_OPS))
	assert len(_OPS) == len(ops_registry())
	assert get_op_spec("if") == ops_registry()["if"]
	assert get_op_spec("definitely_missing") is None


def test_C_06_replay_determinism_invariant() -> None:
	"""Architecture invariant 3 — same DSL + ctx → byte-identical results.

	Frozen registry guarantees this by construction; this test pins the
	invariant against future regression. Repeats over many DSL shapes so
	any non-determinism leaks via diff."""

	cases = [
		(
			{
				"and": [
					{">": [{"var": "amount"}, 100]},
					{"==": [{"var": "currency"}, "USD"]},
					{"not_null": {"var": "tenant"}},
				]
			},
			{"amount": 250, "currency": "USD", "tenant": "t-1"},
			True,
		),
		(
			{"or": [{"==": [{"var": "x"}, 1]}, {"==": [{"var": "x"}, 2]}]},
			{"x": 2},
			True,
		),
		(
			{"if": [{">": [{"var": "n"}, 0]}, "pos", "non-pos"]},
			{"n": -3},
			"non-pos",
		),
		(
			{"between": [{"var": "n"}, 1, 10]},
			{"n": 5},
			True,
		),
	]
	for expr_dsl, ctx, want in cases:
		# Run each case 16x — frozen registry implies a constant function
		# of (expr, ctx). Any drift means determinism has been broken.
		results = [evaluate(expr_dsl, ctx) for _ in range(16)]
		assert all(r == want for r in results), (expr_dsl, results, want)


# ---- C-07 arity enforcement -------------------------------------------


def test_C_07_op_arity_mismatch_runtime_too_many() -> None:
	"""Binary op called with 3 args raises ArityMismatchError."""

	with pytest.raises(ArityMismatchError) as exc_info:
		evaluate({"==": [1, 2, 3]}, {})
	assert "==" in str(exc_info.value)
	assert "got 3" in str(exc_info.value)


def test_C_07_op_arity_mismatch_runtime_too_few() -> None:
	"""``between`` requires 3 args; 2 raises."""

	with pytest.raises(ArityMismatchError):
		evaluate({"between": [1, 2]}, {})


def test_C_07_unary_op_with_zero_args_raises() -> None:
	"""Unary op given a zero-length list raises arity error."""

	with pytest.raises(ArityMismatchError):
		evaluate({"not_null": []}, {})


def test_C_07_check_arity_walker_flags_bad_op() -> None:
	"""The compile-time walker reports arity violations without running ops."""

	bad = {"and": [{"==": [1]}]}  # ``==`` is binary
	errors = check_arity(bad)
	assert errors, "expected at least one error"
	assert any("'=='" in e for e in errors)
	assert any("got 1" in e for e in errors)


def test_C_07_check_arity_walker_passes_good_expr() -> None:
	"""Well-formed expressions yield no errors."""

	good = {
		"and": [
			{"==": [1, 1]},
			{"not_null": {"var": "x"}},
			{"between": [{"var": "amount"}, 0, 100]},
		]
	}
	assert check_arity(good) == []


def test_C_07_unknown_op_is_not_flagged() -> None:
	"""Unknown ops are treated as literal dicts (cross-runtime semantics
	in audit-2026 E-43); the arity walker leaves them alone."""

	expr = {"unknown_op": [1, 2, 3]}
	assert check_arity(expr) == []


def test_C_07_unknown_op_payload_is_still_walked_for_nested_known_ops() -> None:
	expr = {"unknown_op": {"==": [1]}}
	errors = check_arity(expr)
	assert any("$.unknown_op" in error for error in errors)


def test_C_07_variadic_ops_accept_any_arity() -> None:
	"""``and`` / ``+`` / ``coalesce`` are variadic and accept 0..N args."""

	assert check_arity({"and": []}) == []
	assert check_arity({"+": [1]}) == []
	assert check_arity({"coalesce": [1, 2, 3, 4, 5]}) == []
