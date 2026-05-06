"""Tests for flowforge.replay.fault — E-12 FaultInjector (7 fault modes)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from flowforge.dsl.workflow_def import WorkflowDef
from flowforge.replay.fault import (
	FaultInjector,
	FaultMode,
	FaultSimulationResult,
	FaultSpec,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _wf(extra_states: list[dict[str, Any]] | None = None) -> WorkflowDef:
	"""Minimal 3-state workflow: intake → review → done."""
	states: list[dict[str, Any]] = [
		{"name": "intake", "kind": "manual_review"},
		{"name": "review", "kind": "manual_review"},
		{"name": "done", "kind": "terminal_success"},
	]
	if extra_states:
		states.extend(extra_states)
	return WorkflowDef.model_validate({
		"key": "claim",
		"version": "1.0.0",
		"subject_kind": "claim",
		"initial_state": "intake",
		"states": states,
		"transitions": [
			{
				"id": "submit",
				"event": "submit",
				"from_state": "intake",
				"to_state": "review",
				"priority": 0,
				"guards": [],
				"gates": [],
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
	})


def _run(coro: Any) -> Any:
	return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# No-fault baseline
# ---------------------------------------------------------------------------


def test_no_faults_simulation_completes() -> None:
	wd = _wf()
	injector = FaultInjector([])
	result = _run(injector.simulate(wd, events=[("submit", {}), ("approve", {})]))

	assert result.terminal_state == "done"
	assert result.fault_log == []
	assert len(result.fire_results) == 2


# ---------------------------------------------------------------------------
# Blocking modes (transition does NOT fire)
# ---------------------------------------------------------------------------


def test_gate_fail_blocks_transition() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.gate_fail)])
	# With gate_fail active globally, the submit event is blocked.
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	assert result.terminal_state == "intake"  # didn't move
	assert len(result.fault_log) == 1
	assert result.fault_log[0].mode == FaultMode.gate_fail


def test_doc_missing_blocks_and_logs() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.doc_missing, target_event="submit")])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	assert result.terminal_state == "intake"
	assert result.fault_log[0].mode == FaultMode.doc_missing
	assert "doc_missing" in result.fault_log[0].audit_kind


def test_sla_breach_blocks_and_logs() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.sla_breach, target_state="intake")])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	assert result.terminal_state == "intake"
	assert result.fault_log[0].mode == FaultMode.sla_breach
	assert "sla_breach" in result.audit_events[0].kind


def test_delegation_expired_blocks() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.delegation_expired)])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	assert result.terminal_state == "intake"
	assert result.fault_log[0].mode == FaultMode.delegation_expired


def test_partner_404_blocks() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.partner_404)])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	assert result.terminal_state == "intake"
	assert result.fault_log[0].mode == FaultMode.partner_404


# ---------------------------------------------------------------------------
# webhook_5xx — fires transition but adds fault audit event
# ---------------------------------------------------------------------------


def test_webhook_5xx_fires_transition_with_fault_event() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.webhook_5xx, target_event="submit")])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	# Transition fires (webhook_5xx doesn't block)
	assert result.terminal_state == "review"
	assert len(result.fault_log) == 1
	assert result.fault_log[0].mode == FaultMode.webhook_5xx
	# Fault audit event present
	fault_audits = [e for e in result.audit_events if "webhook_5xx" in e.kind]
	assert len(fault_audits) == 1


# ---------------------------------------------------------------------------
# lookup_oracle_bypass — proceeds and logs a bypass event
# ---------------------------------------------------------------------------


def test_lookup_oracle_bypass_fires_and_logs() -> None:
	wd = _wf()
	injector = FaultInjector([
		FaultSpec(mode=FaultMode.lookup_oracle_bypass, target_event="approve")
	])
	result = _run(injector.simulate(wd, events=[("submit", {}), ("approve", {})]))

	assert result.terminal_state == "done"
	assert any(f.mode == FaultMode.lookup_oracle_bypass for f in result.fault_log)


# ---------------------------------------------------------------------------
# Targeting — state and event scoping
# ---------------------------------------------------------------------------


def test_fault_scoped_to_state_only_fires_in_that_state() -> None:
	wd = _wf()
	# Only block 'approve' in 'review' state.
	injector = FaultInjector([FaultSpec(mode=FaultMode.gate_fail, target_state="review")])
	result = _run(injector.simulate(wd, events=[
		("submit", {}),    # should succeed (not in review state yet)
		("approve", {}),   # should be blocked (now in review)
	]))

	# submit fires, approve blocked
	assert result.terminal_state == "review"
	assert len(result.fault_log) == 1
	assert result.fault_log[0].state == "review"


def test_fault_scoped_to_event_only_fires_for_that_event() -> None:
	wd = _wf()
	# Only block 'approve' event, not 'submit'.
	injector = FaultInjector([FaultSpec(mode=FaultMode.gate_fail, target_event="approve")])
	result = _run(injector.simulate(wd, events=[
		("submit", {}),    # not targeted — fires
		("approve", {}),   # targeted — blocked
	]))

	assert result.terminal_state == "review"
	assert len(result.fault_log) == 1
	assert result.fault_log[0].event == "approve"


def test_multiple_specs_first_blocking_wins() -> None:
	wd = _wf()
	injector = FaultInjector([
		FaultSpec(mode=FaultMode.gate_fail),
		FaultSpec(mode=FaultMode.sla_breach),
	])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	# First blocking spec wins; only one fault logged.
	assert result.fault_log[0].mode == FaultMode.gate_fail
	assert len(result.fault_log) == 1


# ---------------------------------------------------------------------------
# FaultSimulationResult shape
# ---------------------------------------------------------------------------


def test_result_contains_audit_events_from_normal_fire() -> None:
	wd = _wf()
	injector = FaultInjector([])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	# Normal fire always emits a transition audit event.
	assert any("transitioned" in e.kind for e in result.audit_events)


def test_blocking_fault_emits_audit_event() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.doc_missing)])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	assert any("doc_missing" in e.kind for e in result.audit_events)


def test_fault_log_has_correct_message() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.sla_breach)])
	result = _run(injector.simulate(wd, events=[("submit", {})]))

	fe = result.fault_log[0]
	assert "SLA" in fe.message or "sla" in fe.message.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_events_no_fault() -> None:
	wd = _wf()
	injector = FaultInjector([FaultSpec(mode=FaultMode.gate_fail)])
	result = _run(injector.simulate(wd, events=[]))

	assert result.terminal_state == "intake"
	assert result.fault_log == []


def test_all_seven_modes_are_distinct() -> None:
	modes = list(FaultMode)
	assert len(modes) == 7
	assert len({m.value for m in modes}) == 7
