from __future__ import annotations

from typing import Any

import pytest

from flowforge import config
from flowforge.compiler.catalog import build_catalog
from flowforge.dsl import WorkflowDef
from flowforge.engine.signals import Signal, SignalCorrelator
from flowforge.replay.reconstruct import reconstruct
from flowforge.testing.parity import assert_parity


@pytest.fixture(autouse=True)
def reset_config():
	config.reset_to_fakes()
	yield


def _approval_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "expense_approval",
			"version": "1.2.0",
			"subject_kind": "expense",
			"initial_state": "draft",
			"states": [
				{"name": "draft", "kind": "manual_review"},
				{"name": "review", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
				{"name": "rejected", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "draft",
					"to_state": "review",
					"gates": [{"kind": "permission", "permission": "expense.submit"}],
				},
				{
					"id": "approve",
					"event": "decide",
					"from_state": "review",
					"to_state": "approved",
					"priority": 10,
					"guards": [
						{
							"kind": "expr",
							"expr": {"==": [{"var": "event.payload.decision"}, "approve"]},
						}
					],
					"gates": [{"kind": "permission", "permission": "expense.approve"}],
					"effects": [
						{
							"kind": "set",
							"target": "context.approved_by",
							"expr": {"var": "__actor__"},
						}
					],
				},
				{
					"id": "reject",
					"event": "decide",
					"from_state": "review",
					"to_state": "rejected",
					"guards": [
						{
							"kind": "expr",
							"expr": {"==": [{"var": "event.payload.decision"}, "reject"]},
						}
					],
				},
			],
		}
	)


def test_build_catalog_groups_subjects_with_deterministic_lists() -> None:
	other = WorkflowDef.model_validate(
		{
			"key": "invoice_review",
			"version": "0.1.0",
			"subject_kind": "invoice",
			"initial_state": "open",
			"states": [
				{"name": "paid", "kind": "terminal_success"},
				{"name": "open", "kind": "manual_review"},
			],
			"transitions": [],
		}
	)

	catalog = build_catalog([_approval_def(), other])

	assert catalog == {
		"subjects": {
			"expense": {
				"states": ["approved", "draft", "rejected", "review"],
				"permissions": ["expense.approve", "expense.submit"],
				"workflows": [{"key": "expense_approval", "version": "1.2.0"}],
			},
			"invoice": {
				"states": ["open", "paid"],
				"permissions": [],
				"workflows": [{"key": "invoice_review", "version": "0.1.0"}],
			},
		}
	}


@pytest.mark.asyncio
async def test_assert_parity_returns_no_diffs_when_python_runner_matches() -> None:
	scenarios = [
		{
			"initial_context": {"amount": 25},
			"events": [("submit", {}), ("decide", {"decision": "approve"})],
		}
	]

	async def python_runner(sc: dict[str, Any]) -> str:
		assert sc["initial_context"]["amount"] == 25
		return "approved"

	assert await assert_parity(
		_approval_def(),
		scenarios=scenarios,
		python_runner=python_runner,
	) == []


@pytest.mark.asyncio
async def test_assert_parity_reports_scenario_diff_when_runner_disagrees() -> None:
	async def python_runner(_: dict[str, Any]) -> str:
		return "rejected"

	diffs = await assert_parity(
		_approval_def(),
		scenarios=[{"events": [("submit", {}), ("decide", {"decision": "approve"})]}],
		python_runner=python_runner,
	)

	assert len(diffs) == 1
	assert "python=rejected dsl=approved" in diffs[0]


@pytest.mark.asyncio
async def test_assert_parity_without_python_runner_smoke_runs_dsl_only() -> None:
	assert await assert_parity(
		_approval_def(),
		scenarios=[{"events": [("submit", {}), ("decide", {"decision": "reject"})]}],
	) == []


@pytest.mark.asyncio
async def test_reconstruct_replays_until_terminal_and_preserves_instance_inputs() -> None:
	instance = await reconstruct(
		_approval_def(),
		[
			("submit", {}),
			("decide", {"decision": "approve"}),
			("decide", {"decision": "reject"}),
		],
		initial_context={"amount": 50},
		instance_id="expense-1",
		tenant_id="tenant-a",
	)

	assert instance.id == "expense-1"
	assert instance.state == "approved"
	assert instance.context == {"amount": 50, "approved_by": "replay"}
	assert [entry.split(":", 1)[0] for entry in instance.history] == [
		"draft-(submit",
		"review-(approve",
	]


def test_signal_correlator_consumes_fifo_by_signal_and_key() -> None:
	correlator = SignalCorrelator()
	first = Signal("payment_received", "expense-1", {"amount": 50})
	second = Signal("payment_received", "expense-1", {"amount": 75})
	other = Signal("payment_received", "expense-2", {"amount": 100})

	correlator.push(first)
	correlator.push(second)
	correlator.push(other)

	assert correlator.pending_count() == 3
	assert correlator.consume("payment_received", "expense-1") == first
	assert correlator.consume("payment_received", "expense-1") == second
	assert correlator.consume("payment_received", "expense-1") is None
	assert correlator.consume("payment_received", "expense-2") == other
	assert correlator.pending_count() == 0
