"""Tests for the DMN decision table evaluator."""

from __future__ import annotations

import pytest

from flowforge.dmn import (
	DmnCondition,
	DmnRule,
	DmnTable,
	HitPolicy,
	evaluate_dmn,
	evaluate_dmn_single,
)
from flowforge.dmn.evaluator import DmnEvaluationError
from flowforge.dmn.models import CompareOp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule(id: str, conditions: list[dict], outputs: dict) -> DmnRule:
	return DmnRule(
		id=id,
		conditions=[DmnCondition(**c) for c in conditions],
		outputs=outputs,
	)


def _table(rules: list[DmnRule], hit_policy: HitPolicy = HitPolicy.FIRST) -> DmnTable:
	return DmnTable(id="test_table", name="Test", hit_policy=hit_policy, rules=rules)


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------

def test_eq_match():
	table = _table([_rule("r1", [{"field": "status", "op": "eq", "value": "active"}], {"eligible": True})])
	assert evaluate_dmn(table, {"status": "active"}) == [{"eligible": True}]


def test_eq_no_match():
	table = _table([_rule("r1", [{"field": "status", "op": "eq", "value": "active"}], {"eligible": True})])
	assert evaluate_dmn(table, {"status": "inactive"}) == []


def test_ne_match():
	table = _table([_rule("r1", [{"field": "x", "op": "ne", "value": 0}], {"ok": True})])
	assert evaluate_dmn(table, {"x": 5}) == [{"ok": True}]
	assert evaluate_dmn(table, {"x": 0}) == []


def test_lt_le_gt_ge():
	rules = [
		_rule("r1", [{"field": "score", "op": "ge", "value": 700}], {"tier": "A"}),
		_rule("r2", [{"field": "score", "op": "ge", "value": 600}, {"field": "score", "op": "lt", "value": 700}], {"tier": "B"}),
		_rule("r3", [{"field": "score", "op": "lt", "value": 600}], {"tier": "C"}),
	]
	table = _table(rules, HitPolicy.FIRST)
	assert evaluate_dmn(table, {"score": 750}) == [{"tier": "A"}]
	assert evaluate_dmn(table, {"score": 650}) == [{"tier": "B"}]
	assert evaluate_dmn(table, {"score": 500}) == [{"tier": "C"}]


def test_in_op():
	table = _table([_rule("r1", [{"field": "role", "op": "in", "value": ["admin", "manager"]}], {"access": True})])
	assert evaluate_dmn(table, {"role": "admin"}) == [{"access": True}]
	assert evaluate_dmn(table, {"role": "guest"}) == []


def test_not_in_op():
	table = _table([_rule("r1", [{"field": "role", "op": "not_in", "value": ["banned"]}], {"access": True})])
	assert evaluate_dmn(table, {"role": "user"}) == [{"access": True}]
	assert evaluate_dmn(table, {"role": "banned"}) == []


def test_contains_op():
	table = _table([_rule("r1", [{"field": "tags", "op": "contains", "value": "vip"}], {"vip": True})])
	assert evaluate_dmn(table, {"tags": ["vip", "premium"]}) == [{"vip": True}]
	assert evaluate_dmn(table, {"tags": ["standard"]}) == []


def test_starts_with_ends_with():
	table = _table([
		_rule("r1", [{"field": "email", "op": "ends_with", "value": "@acme.com"}], {"internal": True}),
	])
	assert evaluate_dmn(table, {"email": "alice@acme.com"}) == [{"internal": True}]
	assert evaluate_dmn(table, {"email": "alice@other.com"}) == []


def test_null_not_null():
	t1 = _table([_rule("r1", [{"field": "x", "op": "null"}], {"missing": True})])
	t2 = _table([_rule("r1", [{"field": "x", "op": "not_null"}], {"present": True})])
	assert evaluate_dmn(t1, {"x": None}) == [{"missing": True}]
	assert evaluate_dmn(t1, {"x": 1}) == []
	assert evaluate_dmn(t2, {"x": 42}) == [{"present": True}]
	assert evaluate_dmn(t2, {}) == []


def test_between_op():
	table = _table([_rule("r1", [{"field": "age", "op": "between", "value": [18, 65]}], {"eligible": True})])
	assert evaluate_dmn(table, {"age": 30}) == [{"eligible": True}]
	assert evaluate_dmn(table, {"age": 18}) == [{"eligible": True}]  # inclusive
	assert evaluate_dmn(table, {"age": 65}) == [{"eligible": True}]  # inclusive
	assert evaluate_dmn(table, {"age": 10}) == []
	assert evaluate_dmn(table, {"age": 70}) == []


def test_between_requires_two_element_list():
	with pytest.raises(ValueError):
		DmnCondition(field="x", op=CompareOp.BETWEEN, value=[1])


# ---------------------------------------------------------------------------
# Nested field paths
# ---------------------------------------------------------------------------

def test_nested_path():
	table = _table([
		_rule("r1", [{"field": "applicant.credit_score", "op": "ge", "value": 700}], {"approved": True})
	])
	assert evaluate_dmn(table, {"applicant": {"credit_score": 720}}) == [{"approved": True}]
	assert evaluate_dmn(table, {"applicant": {"credit_score": 600}}) == []
	assert evaluate_dmn(table, {}) == []  # missing path → None → no match


def test_deeply_nested_path():
	table = _table([
		_rule("r1", [{"field": "a.b.c", "op": "eq", "value": 1}], {"hit": True})
	])
	assert evaluate_dmn(table, {"a": {"b": {"c": 1}}}) == [{"hit": True}]
	assert evaluate_dmn(table, {"a": {"b": {"c": 2}}}) == []


# ---------------------------------------------------------------------------
# Hit policies
# ---------------------------------------------------------------------------

def test_hit_policy_first_returns_first_match():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"label": "r1"}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"label": "r2"}),
	]
	table = _table(rules, HitPolicy.FIRST)
	# x=10 matches both, but FIRST returns r1
	assert evaluate_dmn(table, {"x": 10}) == [{"label": "r1"}]


def test_hit_policy_unique_ok():
	rules = [
		_rule("r1", [{"field": "x", "op": "eq", "value": 1}], {"v": "one"}),
		_rule("r2", [{"field": "x", "op": "eq", "value": 2}], {"v": "two"}),
	]
	table = _table(rules, HitPolicy.UNIQUE)
	assert evaluate_dmn(table, {"x": 1}) == [{"v": "one"}]
	assert evaluate_dmn(table, {"x": 99}) == []


def test_hit_policy_unique_raises_on_multiple():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"v": "a"}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"v": "b"}),
	]
	table = _table(rules, HitPolicy.UNIQUE)
	with pytest.raises(DmnEvaluationError, match="UNIQUE"):
		evaluate_dmn(table, {"x": 10})


def test_hit_policy_any_ok():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"eligible": True}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"eligible": True}),
	]
	table = _table(rules, HitPolicy.ANY)
	# Both match and agree → ok
	assert evaluate_dmn(table, {"x": 10}) == [{"eligible": True}]


def test_hit_policy_any_raises_on_conflict():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"v": "a"}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"v": "b"}),
	]
	table = _table(rules, HitPolicy.ANY)
	with pytest.raises(DmnEvaluationError, match="ANY"):
		evaluate_dmn(table, {"x": 10})


def test_hit_policy_all():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"tag": "positive"}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"tag": "big"}),
	]
	table = _table(rules, HitPolicy.ALL)
	results = evaluate_dmn(table, {"x": 10})
	assert len(results) == 2
	assert {"tag": "positive"} in results
	assert {"tag": "big"} in results


def test_hit_policy_collect():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"v": 1}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"v": 2}),
	]
	table = _table(rules, HitPolicy.COLLECT)
	results = evaluate_dmn(table, {"x": 10})
	assert len(results) == 2


# ---------------------------------------------------------------------------
# evaluate_dmn_single
# ---------------------------------------------------------------------------

def test_evaluate_dmn_single_returns_merged():
	rules = [
		_rule("r1", [{"field": "x", "op": "gt", "value": 0}], {"a": 1}),
		_rule("r2", [{"field": "x", "op": "gt", "value": 5}], {"b": 2}),
	]
	table = _table(rules, HitPolicy.ALL)
	merged = evaluate_dmn_single(table, {"x": 10})
	assert merged == {"a": 1, "b": 2}


def test_evaluate_dmn_single_empty():
	table = _table([_rule("r1", [{"field": "x", "op": "eq", "value": 99}], {"v": 1})])
	assert evaluate_dmn_single(table, {"x": 0}) == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_rules_returns_empty():
	table = DmnTable(id="empty", name="Empty", rules=[])
	assert evaluate_dmn(table, {"x": 1}) == []


def test_missing_field_does_not_crash():
	table = _table([_rule("r1", [{"field": "nonexistent", "op": "eq", "value": 1}], {"v": True})])
	assert evaluate_dmn(table, {}) == []


def test_type_mismatch_does_not_raise():
	# Comparing string > int should fail gracefully → no match
	table = _table([_rule("r1", [{"field": "x", "op": "gt", "value": 5}], {"v": True})])
	assert evaluate_dmn(table, {"x": "hello"}) == []


def test_multiple_conditions_all_must_match():
	table = _table([_rule("r1", [
		{"field": "a", "op": "ge", "value": 10},
		{"field": "b", "op": "eq", "value": "yes"},
	], {"ok": True})])
	assert evaluate_dmn(table, {"a": 10, "b": "yes"}) == [{"ok": True}]
	assert evaluate_dmn(table, {"a": 10, "b": "no"}) == []
	assert evaluate_dmn(table, {"a": 5, "b": "yes"}) == []
