"""End-to-end simulator covering all 3 portability §5.3 worked examples."""

from __future__ import annotations

import pytest

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.testing import simulate


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_config():
	config.reset_to_fakes()
	yield


def _claim_def() -> WorkflowDef:
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
				{"name": "rejected", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "triage",
					"guards": [
						{
							"kind": "expr",
							"expr": {">": [{"var": "context.intake.loss_amount"}, 0]},
						}
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
				},
			],
		}
	)


def _hiring_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "candidate_screen",
			"version": "1.0.0",
			"subject_kind": "candidate",
			"initial_state": "inbound",
			"states": [
				{"name": "inbound", "kind": "manual_review"},
				{"name": "shortlisted", "kind": "manual_review"},
				{"name": "rejected", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "shortlist",
					"event": "review",
					"from_state": "inbound",
					"to_state": "shortlisted",
					"guards": [
						{
							"kind": "expr",
							"expr": {">=": [{"var": "context.candidate.years_experience"}, 3]},
						}
					],
				},
				{
					"id": "reject_underqualified",
					"event": "review",
					"from_state": "inbound",
					"to_state": "rejected",
					"priority": 10,
					"guards": [
						{
							"kind": "expr",
							"expr": {"<": [{"var": "context.candidate.years_experience"}, 3]},
						}
					],
				},
			],
		}
	)


def _permit_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "permit_intake",
			"version": "1.0.0",
			"subject_kind": "permit",
			"initial_state": "submitted",
			"states": [
				{"name": "submitted", "kind": "manual_review"},
				{"name": "heritage_review", "kind": "manual_review"},
				{"name": "review", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
				{"name": "rejected", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "to_review",
					"event": "validate",
					"from_state": "submitted",
					"to_state": "review",
				},
				{
					"id": "to_heritage",
					"event": "validate",
					"from_state": "submitted",
					"to_state": "heritage_review",
					"priority": 10,
					"guards": [
						{
							"kind": "expr",
							"expr": {"==": [{"var": "context.parcel.in_heritage_zone"}, True]},
						}
					],
				},
				{"id": "approve", "event": "decide", "from_state": "review", "to_state": "approved"},
				{"id": "approve_h", "event": "decide", "from_state": "heritage_review", "to_state": "approved"},
			],
		}
	)


async def test_claim_happy_path() -> None:
	result = await simulate(
		_claim_def(),
		initial_context={"intake": {"loss_amount": 5000}},
		events=[("submit", {})],
	)
	assert result.terminal_state == "triage"


async def test_claim_large_loss_branches_to_senior() -> None:
	result = await simulate(
		_claim_def(),
		initial_context={"intake": {"loss_amount": 250000}},
		events=[("submit", {})],
	)
	assert result.terminal_state == "senior_triage"


async def test_claim_lapsed_terminates() -> None:
	result = await simulate(
		_claim_def(),
		initial_context={"policy": {"status": "lapsed"}, "intake": {"loss_amount": 100}},
		events=[("policy_check", {})],
	)
	assert result.terminal_state == "rejected"


async def test_hiring_shortlists_qualified() -> None:
	result = await simulate(
		_hiring_def(),
		initial_context={"candidate": {"years_experience": 5}},
		events=[("review", {})],
	)
	assert result.terminal_state == "shortlisted"


async def test_hiring_rejects_underqualified() -> None:
	result = await simulate(
		_hiring_def(),
		initial_context={"candidate": {"years_experience": 1}},
		events=[("review", {})],
	)
	assert result.terminal_state == "rejected"


async def test_permit_default_to_review() -> None:
	result = await simulate(
		_permit_def(),
		initial_context={"parcel": {"in_heritage_zone": False}},
		events=[("validate", {}), ("decide", {})],
	)
	assert result.terminal_state == "approved"
	assert "review" in "->".join(result.history)


async def test_permit_heritage_branch() -> None:
	result = await simulate(
		_permit_def(),
		initial_context={"parcel": {"in_heritage_zone": True}},
		events=[("validate", {}), ("decide", {})],
	)
	assert result.terminal_state == "approved"
	assert "heritage_review" in "->".join(result.history)
