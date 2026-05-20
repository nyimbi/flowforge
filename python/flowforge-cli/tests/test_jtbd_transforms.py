"""Focused tests for JTBD transform helper edge cases."""

from __future__ import annotations

from typing import Any

from flowforge_cli.jtbd import transforms as T


def _jtbd(**overrides: Any) -> dict[str, Any]:
	base: dict[str, Any] = {
		"id": "claim_intake",
		"title": "File a claim",
		"actor": {"role": "policyholder"},
		"success_criteria": ["queued"],
		"data_capture": [],
		"edge_cases": [],
		"approvals": [],
	}
	base.update(overrides)
	return base


def test_pascal_case_empty_value_falls_back_to_x() -> None:
	assert T.pascal_case("") == "X"


def test_derive_states_skips_duplicate_branch_target() -> None:
	states = T.derive_states(
		_jtbd(
			edge_cases=[
				{"id": "already_review", "handle": "branch", "branch_to": "review"},
				{"id": "manual_queue", "handle": "branch", "branch_to": "manual_queue"},
			]
		)
	)

	names = [state["name"] for state in states]
	assert names.count("review") == 1
	assert "manual_queue" in names


def test_derive_transitions_skips_branch_without_target_state() -> None:
	jtbd = _jtbd(
		edge_cases=[
			{"id": "missing_target", "handle": "branch", "branch_to": "manual_queue"}
		]
	)
	states = [
		{"name": "intake", "kind": "manual_review"},
		{"name": "review", "kind": "manual_review"},
		{"name": "done", "kind": "terminal_success"},
	]

	transitions = T.derive_transitions(jtbd, states)

	assert {transition["id"] for transition in transitions} == {
		"claim_intake_submit",
		"claim_intake_approve",
	}


def test_loop_edge_derives_transition_and_audit_topic() -> None:
	jtbd = _jtbd(edge_cases=[{"id": "more_info", "handle": "loop"}])
	states = T.derive_states(jtbd)
	transitions = T.derive_transitions(jtbd, states)

	loop = next(transition for transition in transitions if transition["event"] == "request_more_info")
	assert loop["id"] == "claim_intake_more_info_loop"
	assert loop["from_state"] == "review"
	assert loop["to_state"] == "intake"
	assert loop["effects"] == [
		{"kind": "audit", "template": "claim_intake.more_info_returned"}
	]
	assert "claim_intake.more_info_returned" in T.derive_audit_topics(jtbd)


def test_field_column_helpers_use_unknown_kind_defaults() -> None:
	field = {"id": "custom_value", "kind": "custom", "required": True}

	assert T.field_to_sa_column(field) == ("custom_value", "String(255)", False)
	assert T.field_to_sql_column(field) == ("custom_value", "VARCHAR(255)", False)


def test_field_to_form_field_defaults_label_and_preserves_validation() -> None:
	field = {
		"id": "claim_reason",
		"kind": "text",
		"required": True,
		"pii": True,
		"validation": {"min": 3},
	}

	assert T.field_to_form_field({"id": "summary", "kind": "text"}) == {
		"id": "summary",
		"kind": "text",
		"label": "Summary",
		"required": False,
		"pii": False,
	}

	assert T.field_to_form_field(field) == {
		"id": "claim_reason",
		"kind": "text",
		"label": "Claim Reason",
		"required": True,
		"pii": True,
		"validation": {"min": 3},
	}
