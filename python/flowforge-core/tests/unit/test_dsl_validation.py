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
