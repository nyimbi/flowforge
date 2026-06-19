"""DMN decision table evaluator.

Evaluates :class:`~flowforge.dmn.models.DmnTable` instances against a
context dict, returning a list of matching output dicts.

The evaluator is intentionally safe: it never calls ``eval()``, never
imports user code, and raises :class:`DmnEvaluationError` on any
ambiguity (wrong hit policy, missing required field, etc.).
"""

from __future__ import annotations

import logging
from functools import reduce
from typing import Any

from .models import CompareOp, DmnCondition, DmnRule, DmnTable, HitPolicy

_log = logging.getLogger(__name__)


class DmnEvaluationError(ValueError):
	"""Raised when DMN evaluation fails (policy violation, type error, etc.)."""


# ---------------------------------------------------------------------------
# Field path resolver
# ---------------------------------------------------------------------------

def _get_field(context: dict[str, Any], path: str) -> Any:
	"""Resolve a dot-notation path from *context*.

	Returns ``None`` if any intermediate key is missing.
	"""
	parts = path.split(".")
	try:
		return reduce(lambda d, k: d[k] if isinstance(d, dict) else getattr(d, k, None), parts, context)
	except (KeyError, TypeError, AttributeError):
		return None


# ---------------------------------------------------------------------------
# Condition matcher
# ---------------------------------------------------------------------------

def _matches_condition(cond: DmnCondition, context: dict[str, Any]) -> bool:
	"""Return True if *cond* matches *context*."""
	actual = _get_field(context, cond.field)
	op = cond.op
	expected = cond.value

	if op == CompareOp.NULL:
		return actual is None
	if op == CompareOp.NOT_NULL:
		return actual is not None

	# For all other ops, None never matches
	if actual is None:
		return False

	try:
		if op == CompareOp.EQ:
			return actual == expected
		if op == CompareOp.NE:
			return actual != expected
		if op == CompareOp.LT:
			return actual < expected  # type: ignore[operator]
		if op == CompareOp.LE:
			return actual <= expected  # type: ignore[operator]
		if op == CompareOp.GT:
			return actual > expected  # type: ignore[operator]
		if op == CompareOp.GE:
			return actual >= expected  # type: ignore[operator]
		if op == CompareOp.IN:
			return actual in expected
		if op == CompareOp.NOT_IN:
			return actual not in expected
		if op == CompareOp.CONTAINS:
			return expected in actual
		if op == CompareOp.NOT_CONTAINS:
			return expected not in actual
		if op == CompareOp.STARTS_WITH:
			return str(actual).startswith(str(expected))
		if op == CompareOp.ENDS_WITH:
			return str(actual).endswith(str(expected))
		if op == CompareOp.BETWEEN:
			low, high = expected
			return low <= actual <= high  # type: ignore[operator]
	except (TypeError, AttributeError) as exc:
		_log.debug("DMN condition comparison error field=%r op=%r: %s", cond.field, op, exc)
		return False

	raise DmnEvaluationError(f"Unknown operator {op!r}")


def _matches_rule(rule: DmnRule, context: dict[str, Any]) -> bool:
	"""Return True if ALL conditions in *rule* match *context*."""
	return all(_matches_condition(c, context) for c in rule.conditions)


# ---------------------------------------------------------------------------
# Table evaluator
# ---------------------------------------------------------------------------

def evaluate_dmn(
	table: DmnTable,
	context: dict[str, Any],
) -> list[dict[str, Any]]:
	"""Evaluate *table* against *context* and return a list of output dicts.

	The returned list contains:
	- FIRST: zero or one dict (the first matching rule's outputs)
	- UNIQUE: exactly one dict, or raises DmnEvaluationError
	- ANY: exactly one dict (all matches must agree), or raises
	- ALL / COLLECT: one dict per matching rule

	Args:
		table: The decision table to evaluate.
		context: The input context — typically the workflow instance context.

	Raises:
		DmnEvaluationError: On UNIQUE/ANY policy violations.
	"""
	matching: list[DmnRule] = [r for r in table.rules if _matches_rule(r, context)]

	if table.hit_policy == HitPolicy.FIRST:
		return [matching[0].outputs] if matching else []

	if table.hit_policy == HitPolicy.UNIQUE:
		if len(matching) == 0:
			return []
		if len(matching) > 1:
			ids = [r.id for r in matching]
			raise DmnEvaluationError(
				f"DMN table {table.id!r} hit_policy=UNIQUE: {len(matching)} rules matched {ids}"
			)
		return [matching[0].outputs]

	if table.hit_policy == HitPolicy.ANY:
		if not matching:
			return []
		first = matching[0].outputs
		for rule in matching[1:]:
			if rule.outputs != first:
				raise DmnEvaluationError(
					f"DMN table {table.id!r} hit_policy=ANY: rules {matching[0].id!r} and "
					f"{rule.id!r} produce different outputs"
				)
		return [first]

	if table.hit_policy in (HitPolicy.ALL, HitPolicy.COLLECT):
		return [r.outputs for r in matching]

	raise DmnEvaluationError(f"Unknown hit policy {table.hit_policy!r}")


def evaluate_dmn_single(
	table: DmnTable,
	context: dict[str, Any],
) -> dict[str, Any]:
	"""Like :func:`evaluate_dmn` but returns a single merged output dict.

	For FIRST/UNIQUE/ANY: returns the single matching output or ``{}``.
	For ALL/COLLECT: merges all outputs left-to-right (later rules win on
	key conflicts).
	"""
	results = evaluate_dmn(table, context)
	if not results:
		return {}
	merged: dict[str, Any] = {}
	for r in results:
		merged.update(r)
	return merged


__all__ = ["DmnEvaluationError", "evaluate_dmn", "evaluate_dmn_single"]
