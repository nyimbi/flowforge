"""DSL parsing + compiler validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowforge.compiler import ValidationError, validate
from flowforge.dsl import WorkflowDef


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "src" / "flowforge" / "dsl" / "schema"


def _basic_def() -> dict:
	return {
		"key": "demo",
		"version": "1.0.0",
		"subject_kind": "demo_subject",
		"initial_state": "draft",
		"states": [
			{"name": "draft", "kind": "manual_review"},
			{"name": "approved", "kind": "terminal_success"},
		],
		"transitions": [
			{"id": "submit", "event": "submit", "from_state": "draft", "to_state": "approved"},
		],
	}


def test_pydantic_parse_round_trip() -> None:
	wd = WorkflowDef.model_validate(_basic_def())
	assert wd.key == "demo"
	assert len(wd.states) == 2
	assert len(wd.transitions) == 1


def test_validator_passes_on_basic_def() -> None:
	report = validate(_basic_def())
	assert report.ok, report.errors


def test_validator_flags_unreachable_state() -> None:
	d = _basic_def()
	d["states"].append({"name": "orphan", "kind": "manual_review"})
	report = validate(d)
	assert not report.ok
	assert any("unreachable" in e for e in report.errors), report.errors


def test_validator_flags_dead_end_transition() -> None:
	d = _basic_def()
	d["transitions"].append(
		{"id": "to_nowhere", "event": "x", "from_state": "draft", "to_state": "missing"}
	)
	report = validate(d)
	assert any("missing" in e for e in report.errors), report.errors


def test_validator_flags_missing_initial_and_from_state() -> None:
	d = _basic_def()
	d["initial_state"] = "missing_initial"
	d["transitions"][0]["from_state"] = "missing_from"
	report = validate(d)
	assert any("initial_state 'missing_initial'" in e for e in report.errors), report.errors
	assert any("from_state 'missing_from'" in e for e in report.errors), report.errors


def test_validator_flags_unreachable_terminal_and_subworkflow_cycle() -> None:
	d = _basic_def()
	d["states"].extend(
		[
			{"name": "orphan_done", "kind": "terminal_success"},
			{"name": "self_child", "kind": "subworkflow", "subworkflow_key": "demo"},
		]
	)
	report = validate(d)
	assert any("unreachable terminal 'orphan_done'" in e for e in report.errors), report.errors
	assert any("subworkflow cycle" in e for e in report.errors), report.errors


def test_validator_flags_duplicate_priority() -> None:
	d = _basic_def()
	d["transitions"].append(
		{"id": "submit2", "event": "submit", "from_state": "draft", "to_state": "approved"}
	)
	report = validate(d)
	assert any("duplicate priority" in e for e in report.errors), report.errors


def test_validator_loads_real_schema_for_workflow_def() -> None:
	schema_path = SCHEMA_DIR / "workflow_def.schema.json"
	assert schema_path.exists()
	json.loads(schema_path.read_text())  # parses


def test_validator_schema_loader_falls_back_to_source_tree(monkeypatch: pytest.MonkeyPatch) -> None:
	from flowforge.compiler import validator

	def missing_package_data(_package: str) -> object:
		raise ModuleNotFoundError("package data unavailable")

	monkeypatch.setattr(validator, "_WD_SCHEMA", None)
	monkeypatch.setattr(validator, "files", missing_package_data)

	assert validator._wd_schema()["type"] == "object"


def test_validator_reports_schema_errors_and_strict_raises() -> None:
	bad = _basic_def()
	del bad["key"]
	report = validate(bad)
	assert not report.ok
	assert any("schema at <root>" in e for e in report.errors), report.errors
	with pytest.raises(ValidationError, match="schema at <root>"):
		validate(bad, strict=True)


def test_validator_reports_pydantic_errors_after_schema_passes() -> None:
	d = _basic_def()
	d["transitions"][0]["guards"] = [{"kind": "expr", "expr": {"==": [1], "!=": [2]}}]
	report = validate(d)
	assert any("pydantic:" in e and "exactly one key" in e for e in report.errors), report.errors
	with pytest.raises(ValidationError, match="pydantic:"):
		validate(d, strict=True)


def test_validator_accepts_workflowdef_instance_and_strict_raises_topology() -> None:
	wd = WorkflowDef.model_validate(_basic_def())
	assert validate(wd).ok

	bad = _basic_def()
	bad["transitions"][0]["to_state"] = "missing"
	bad_wd = WorkflowDef.model_validate(bad)
	with pytest.raises(ValidationError, match="to_state"):
		validate(bad_wd, strict=True)


# ---- audit-2026 E-35 / C-07 arity --------------------------------------


def test_C_07_validator_flags_op_arity_mismatch_in_guard() -> None:
	"""A guard with the wrong-arity op must surface in the report (audit-2026 C-07)."""

	d = _basic_def()
	d["transitions"][0]["guards"] = [{"kind": "expr", "expr": {"==": [1, 2, 3]}}]
	report = validate(d)
	assert not report.ok, report.errors
	arity_errs = [e for e in report.errors if "'=='" in e]
	assert arity_errs, report.errors
	assert any("got 3" in e for e in arity_errs)


def test_C_07_validator_flags_op_arity_mismatch_in_effect() -> None:
	"""An effect.expr with the wrong-arity op must surface too."""

	d = _basic_def()
	d["transitions"][0]["effects"] = [
		{"kind": "set", "target": "context.x", "expr": {"between": [1]}}
	]
	report = validate(d)
	assert not report.ok, report.errors
	assert any("'between'" in e for e in report.errors), report.errors


def test_C_07_validator_strict_raises_on_arity() -> None:
	"""Strict mode raises ValidationError on the first arity error."""

	from flowforge.compiler import ValidationError

	d = _basic_def()
	d["transitions"][0]["guards"] = [{"kind": "expr", "expr": {"not_null": []}}]
	with pytest.raises(ValidationError):
		validate(d, strict=True)


def test_C_07_validator_passes_well_formed_expressions() -> None:
	d = _basic_def()
	d["transitions"][0]["guards"] = [
		{"kind": "expr", "expr": {"and": [{"==": [1, 1]}, {"not_null": {"var": "x"}}]}}
	]
	d["transitions"][0]["effects"] = [
		{
			"kind": "set",
			"target": "context.score",
			"expr": {"+": [1, 2, 3]},  # variadic — fine
		}
	]
	report = validate(d)
	assert report.ok, report.errors


def test_lookup_permission_warning_covers_guard_effect_expr_and_http_call() -> None:
	guard_lookup = _basic_def()
	guard_lookup["transitions"][0]["guards"] = [
		{"kind": "expr", "expr": {"var": "lookup.claim.status"}}
	]
	report = validate(guard_lookup)
	assert any("touches a lookup" in w for w in report.warnings), report.warnings

	effect_lookup = _basic_def()
	effect_lookup["transitions"][0]["effects"] = [
		{"kind": "set", "target": "context.x", "expr": {"lookup": "claim-1"}}
	]
	report = validate(effect_lookup)
	assert any("touches a lookup" in w for w in report.warnings), report.warnings

	http_lookup = _basic_def()
	http_lookup["transitions"][0]["effects"] = [{"kind": "http_call", "url": "/lookup/claims"}]
	report = validate(http_lookup)
	assert any("touches a lookup" in w for w in report.warnings), report.warnings

	http_lookup["transitions"][0]["gates"] = [{"kind": "permission", "permission": "claim.read"}]
	assert validate(http_lookup).warnings == []


def test_lookup_permission_ignores_literals_and_walks_multi_key_effect_values() -> None:
	literal_lookup = _basic_def()
	literal_lookup["transitions"][0]["guards"] = [
		{"kind": "expr", "expr": {"contains": ["lookup_failed", "lookup"]}}
	]
	assert validate(literal_lookup).warnings == []

	nested_lookup = _basic_def()
	nested_lookup["transitions"][0]["effects"] = [
		{
			"kind": "audit",
			"expr": {"payload": {"var": "lookup.claim.status"}, "literal": "lookup_failed"},
		}
	]
	report = validate(nested_lookup)
	assert any("touches a lookup" in w for w in report.warnings), report.warnings
