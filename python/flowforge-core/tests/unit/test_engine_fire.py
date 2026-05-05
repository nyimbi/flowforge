"""Engine two-phase fire end-to-end."""

from __future__ import annotations

import pytest

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.ports.types import Principal


pytestmark = pytest.mark.asyncio


def _claim_intake_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "triage", "kind": "manual_review"},
				{"name": "senior_triage", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
				{"name": "rejected", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "triage",
					"priority": 0,
					"guards": [
						{
							"kind": "expr",
							"expr": {
								"and": [
									{"not_null": {"var": "context.intake.policy_id"}},
									{">": [{"var": "context.intake.loss_amount"}, 0]},
								]
							},
						}
					],
					"effects": [
						{
							"kind": "create_entity",
							"entity": "claim",
							"values": {
								"policy_id": {"var": "context.intake.policy_id"},
								"loss_amount": {"var": "context.intake.loss_amount"},
							},
						},
						{
							"kind": "set",
							"target": "context.triage.priority",
							"expr": {
								"if": [
									{">": [{"var": "context.intake.loss_amount"}, 100000]},
									"high",
									"normal",
								]
							},
						},
						{"kind": "notify", "template": "claim.submitted"},
					],
				},
				{
					"id": "branch_large_loss",
					"event": "submit",
					"from_state": "intake",
					"to_state": "senior_triage",
					"priority": 10,
					"guards": [
						{
							"kind": "expr",
							"expr": {">": [{"var": "context.intake.loss_amount"}, 100000]},
						}
					],
				},
				{
					"id": "reject_lapsed",
					"event": "policy_check",
					"from_state": "intake",
					"to_state": "rejected",
					"guards": [
						{
							"kind": "expr",
							"expr": {"==": [{"var": "context.policy.status"}, "lapsed"]},
						}
					],
					"effects": [
						{
							"kind": "set",
							"target": "context.rejection_reason",
							"expr": "policy_lapsed",
						}
					],
				},
			],
		}
	)


@pytest.fixture(autouse=True)
def reset_config():
	config.reset_to_fakes()
	yield


async def test_happy_path_lands_in_triage() -> None:
	wd = _claim_intake_def()
	inst = new_instance(
		wd,
		initial_context={"intake": {"policy_id": "p-1", "loss_amount": 5000}},
	)
	result = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert result.matched_transition_id == "submit"
	assert result.new_state == "triage"
	assert inst.context["triage"]["priority"] == "normal"
	assert any(e[0] == "claim" for e in inst.created_entities)


async def test_priority_branch_for_large_loss() -> None:
	wd = _claim_intake_def()
	inst = new_instance(
		wd,
		initial_context={"intake": {"policy_id": "p-1", "loss_amount": 250000}},
	)
	result = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert result.matched_transition_id == "branch_large_loss"
	assert result.new_state == "senior_triage"


async def test_reject_lapsed_policy_terminates() -> None:
	wd = _claim_intake_def()
	inst = new_instance(
		wd,
		initial_context={
			"policy": {"status": "lapsed"},
			"intake": {"policy_id": "p-1", "loss_amount": 100},
		},
	)
	result = await fire(wd, inst, "policy_check", principal=Principal(user_id="u", is_system=True))
	assert result.new_state == "rejected"
	assert result.terminal is True


async def test_no_match_keeps_state() -> None:
	wd = _claim_intake_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": None, "loss_amount": 0}})
	result = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert result.matched_transition_id is None
	assert result.new_state == "intake"
