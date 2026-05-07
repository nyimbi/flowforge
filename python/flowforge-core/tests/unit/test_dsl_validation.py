"""DSL parsing + compiler validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowforge.compiler import validate
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
