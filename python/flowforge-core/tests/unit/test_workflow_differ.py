"""Tests for flowforge.compiler.diff — E-13 WorkflowDiffer."""

from __future__ import annotations

from typing import Any

import pytest

from flowforge.compiler.diff import (
	StateChange,
	TransitionChange,
	WorkflowDiff,
	diff_workflow_dicts,
	diff_workflows,
)
from flowforge.dsl.workflow_def import WorkflowDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_wf(**overrides: Any) -> dict[str, Any]:
	"""Minimal valid workflow definition."""
	wf: dict[str, Any] = {
		"key": "claim_intake",
		"version": "1.0.0",
		"subject_kind": "claim",
		"initial_state": "intake",
		"states": [
			{"name": "intake", "kind": "manual_review"},
			{"name": "review", "kind": "manual_review"},
			{"name": "done", "kind": "terminal_success"},
		],
		"transitions": [
			{
				"id": "submit",
				"event": "submit",
				"from_state": "intake",
				"to_state": "review",
				"priority": 0,
				"guards": [],
				"gates": [{"kind": "permission", "permission": "claim.submit"}],
				"effects": [],
			},
			{
				"id": "approve",
				"event": "approve",
				"from_state": "review",
				"to_state": "done",
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			},
		],
	}
	wf.update(overrides)
	return wf


def _wf(data: dict[str, Any]) -> WorkflowDef:
	return WorkflowDef.model_validate(data)


# ---------------------------------------------------------------------------
# Identity diff
# ---------------------------------------------------------------------------


def test_identical_workflow_is_empty() -> None:
	data = _base_wf()
	diff = diff_workflow_dicts(data, data)
	assert diff.is_empty()
	assert diff.summary().endswith("(no structural changes)")


def test_version_bump_only_is_empty() -> None:
	"""Changing only version/key metadata doesn't affect structural diff."""
	old = _base_wf(version="1.0.0")
	new = _base_wf(version="1.1.0")
	diff = diff_workflow_dicts(old, new)
	# The diff records old/new versions but structure is the same.
	assert diff.old_version == "1.0.0"
	assert diff.new_version == "1.1.0"
	assert diff.is_empty()


# ---------------------------------------------------------------------------
# State-level diffs
# ---------------------------------------------------------------------------


def test_added_state_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	new["states"].append({"name": "rescinded", "kind": "terminal_fail"})
	diff = diff_workflow_dicts(old, new)

	assert "rescinded" in diff.added_states
	assert diff.removed_states == ()
	assert not diff.is_empty()
	assert "+ state  rescinded" in diff.summary()


def test_removed_state_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	new["states"] = [s for s in new["states"] if s["name"] != "review"]
	new["transitions"] = []  # remove transitions referencing review too
	diff = diff_workflow_dicts(old, new)

	assert "review" in diff.removed_states
	assert "- state  review" in diff.summary()


def test_changed_state_kind_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	# Change 'intake' from manual_review → automatic
	new["states"] = [
		{"name": "intake", "kind": "automatic"} if s["name"] == "intake" else s
		for s in new["states"]
	]
	diff = diff_workflow_dicts(old, new)

	assert len(diff.changed_states) == 1
	sc = diff.changed_states[0]
	assert sc.name == "intake"
	assert "kind" in sc.changed_fields
	assert sc.changed_fields["kind"] == ("manual_review", "automatic")
	assert "intake.kind" in diff.summary()


def test_unchanged_state_not_in_changed() -> None:
	old = _base_wf()
	new = _base_wf()
	new["states"].append({"name": "new_state", "kind": "automatic"})
	diff = diff_workflow_dicts(old, new)

	# Only new_state added; existing states unchanged
	existing = {sc.name for sc in diff.changed_states}
	assert "intake" not in existing
	assert "review" not in existing


# ---------------------------------------------------------------------------
# Transition-level diffs
# ---------------------------------------------------------------------------


def test_added_transition_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	new["transitions"].append({
		"id": "reject",
		"event": "reject",
		"from_state": "review",
		"to_state": "done",
		"priority": 10,
		"guards": [],
		"gates": [],
		"effects": [],
	})
	diff = diff_workflow_dicts(old, new)

	assert "reject" in diff.added_transitions
	assert "+ transition  reject" in diff.summary()


def test_removed_transition_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	new["transitions"] = [t for t in new["transitions"] if t["id"] != "approve"]
	diff = diff_workflow_dicts(old, new)

	assert "approve" in diff.removed_transitions
	assert "- transition  approve" in diff.summary()


def test_changed_transition_to_state_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	new["states"].append({"name": "escalated", "kind": "manual_review"})
	new["transitions"] = [
		{**t, "to_state": "escalated"} if t["id"] == "submit" else t
		for t in new["transitions"]
	]
	diff = diff_workflow_dicts(old, new)

	tr_ids = {tc.id for tc in diff.changed_transitions}
	assert "submit" in tr_ids
	tc = next(tc for tc in diff.changed_transitions if tc.id == "submit")
	assert "to_state" in tc.changed_fields
	assert tc.changed_fields["to_state"] == ("review", "escalated")


def test_changed_transition_gates_detected() -> None:
	old = _base_wf()
	new = _base_wf()
	# Add a second gate to the submit transition.
	new["transitions"] = [
		{**t, "gates": t["gates"] + [{"kind": "documents_complete"}]}
		if t["id"] == "submit" else t
		for t in new["transitions"]
	]
	diff = diff_workflow_dicts(old, new)

	tc_ids = {tc.id for tc in diff.changed_transitions}
	assert "submit" in tc_ids


# ---------------------------------------------------------------------------
# Initial state change
# ---------------------------------------------------------------------------


def test_initial_state_change_detected() -> None:
	old = _base_wf(initial_state="intake")
	new = _base_wf(initial_state="review")
	diff = diff_workflow_dicts(old, new)

	assert diff.initial_state_changed
	assert diff.old_initial_state == "intake"
	assert diff.new_initial_state == "review"
	assert "initial_state" in diff.summary()


def test_same_initial_state_not_flagged() -> None:
	data = _base_wf(initial_state="intake")
	diff = diff_workflow_dicts(data, data)
	assert not diff.initial_state_changed


# ---------------------------------------------------------------------------
# diff_workflows (model input)
# ---------------------------------------------------------------------------


def test_diff_workflows_accepts_model_instances() -> None:
	old = _wf(_base_wf())
	new = _wf(_base_wf())
	diff = diff_workflows(old, new)
	assert diff.is_empty()


def test_diff_workflows_rejects_non_model() -> None:
	with pytest.raises(AssertionError):
		diff_workflows({"not": "a model"}, _wf(_base_wf()))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# diff_workflow_dicts (dict input)
# ---------------------------------------------------------------------------


def test_diff_workflow_dicts_validates_schema() -> None:
	bad = {"key": "x"}  # missing required fields
	with pytest.raises(Exception):  # pydantic.ValidationError
		diff_workflow_dicts(bad, bad)


# ---------------------------------------------------------------------------
# summary output
# ---------------------------------------------------------------------------


def test_summary_contains_key_and_version() -> None:
	old = _base_wf(key="wf_a", version="1.0.0")
	new = _base_wf(key="wf_a", version="2.0.0")
	diff = diff_workflow_dicts(old, new)
	summary = diff.summary()
	assert "wf_a" in summary
	assert "1.0.0" in summary
	assert "2.0.0" in summary


def test_summary_multiple_changes() -> None:
	old = _base_wf()
	new = _base_wf()
	new["states"].append({"name": "flagged", "kind": "manual_review"})
	new["transitions"] = [t for t in new["transitions"] if t["id"] != "approve"]
	diff = diff_workflow_dicts(old, new)

	summary = diff.summary()
	assert "+ state  flagged" in summary
	assert "- transition  approve" in summary
