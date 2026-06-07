"""E3 debugger acceptance tests.

Covers:
- GATE_FAIL causes guard to block a transition that would otherwise pass
- SLA_BREACH injects fault context into a simulation
- WorkflowDiffer detects an added state
- WorkflowDiffer detects a removed transition
- simulate() with a fault returns no-match on the target state
- tutorial --domain insurance smoke (no ImportError)
"""

from __future__ import annotations

import sys
import importlib
from pathlib import Path

import pytest

from flowforge.dsl.workflow_def import WorkflowDef
from flowforge.compiler.diff import diff_workflows
from flowforge.replay.fault import FaultInjector, FaultMode, FaultSpec
from flowforge.replay.simulator import simulate


# ---------------------------------------------------------------------------
# Helpers — minimal WorkflowDef factories
# ---------------------------------------------------------------------------

def _make_wf(
	key: str = "test_wf",
	states: list[dict] | None = None,
	transitions: list[dict] | None = None,
) -> WorkflowDef:
	"""Build a minimal WorkflowDef for testing.

	State kinds must be from the canonical StateKind literal:
	  manual_review, automatic, parallel_fork, parallel_join,
	  timer, signal_wait, subworkflow, terminal_success, terminal_fail
	"""
	return WorkflowDef.model_validate({
		"key": key,
		"version": "1.0.0",
		"subject_kind": "TestSubject",
		"initial_state": "draft",
		"states": states or [
			{"name": "draft", "kind": "manual_review"},
			{"name": "review", "kind": "automatic"},
			{"name": "done", "kind": "terminal_success"},
		],
		"transitions": transitions or [
			{
				"id": "submit",
				"event": "submit",
				"from_state": "draft",
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


# ---------------------------------------------------------------------------
# Test 1: GATE_FAIL blocks a transition that would otherwise pass
# ---------------------------------------------------------------------------

async def test_gate_fail_blocks_transition():
	"""FaultMode.gate_fail on state='draft' should block the submit event."""
	wd = _make_wf()

	# Without fault: submit should advance to "review"
	result_clean = await simulate(wd, events=[("submit", {})])
	assert result_clean.terminal_state == "review", (
		f"Expected 'review' without fault, got {result_clean.terminal_state!r}"
	)

	# With gate_fail on 'draft': submit should be blocked (stay in 'draft')
	fault = FaultSpec(mode=FaultMode.gate_fail, target_state="draft")
	result_faulted = await simulate(wd, events=[("submit", {})], faults=[fault])
	assert result_faulted.terminal_state == "draft", (
		f"Expected 'draft' with gate_fail, got {result_faulted.terminal_state!r}"
	)

	# Verify a fault audit event was emitted
	fault_kinds = [ae.kind for ae in result_faulted.audit_events]
	assert any(k.startswith("wf.fault.") for k in fault_kinds), (
		f"Expected wf.fault.* audit event, got: {fault_kinds}"
	)


# ---------------------------------------------------------------------------
# Test 2: SLA_BREACH injects ctx
# ---------------------------------------------------------------------------

async def test_sla_breach_injects_context():
	"""FaultMode.sla_breach should block the transition and emit an audit event."""
	wd = _make_wf()

	fault = FaultSpec(mode=FaultMode.sla_breach, target_state="draft")
	injector = FaultInjector([fault])
	result = await injector.simulate(wd, events=[("submit", {})])

	# SLA breach is blocking — should stay in draft
	assert result.terminal_state == "draft", (
		f"Expected 'draft' with sla_breach, got {result.terminal_state!r}"
	)
	# Fault log should record the breach
	assert len(result.fault_log) >= 1
	assert result.fault_log[0].mode == FaultMode.sla_breach

	# apply_to_context injects sla-specific keys
	ctx = injector.apply_to_context({}, fault)
	assert ctx["__fault__"]["mode"] == "sla_breach"
	assert ctx["__fault__"]["sla_seconds_remaining"] == 0
	assert ctx["__fault__"]["sla_breached"] is True


# ---------------------------------------------------------------------------
# Test 3: WorkflowDiffer detects an added state
# ---------------------------------------------------------------------------

def test_differ_detects_added_state():
	old_wd = _make_wf(key="wf", states=[
		{"name": "draft", "kind": "manual_review"},
		{"name": "done", "kind": "terminal_success"},
	], transitions=[])

	new_wd = _make_wf(key="wf", states=[
		{"name": "draft", "kind": "manual_review"},
		{"name": "review", "kind": "automatic"},   # new
		{"name": "done", "kind": "terminal_success"},
	], transitions=[])

	diff = diff_workflows(old_wd, new_wd)
	assert "review" in diff.added_states, f"Expected 'review' in added_states: {diff.added_states}"
	assert not diff.removed_states
	assert not diff.is_empty()


# ---------------------------------------------------------------------------
# Test 4: WorkflowDiffer detects a removed transition
# ---------------------------------------------------------------------------

def test_differ_detects_removed_transition():
	base_states = [
		{"name": "draft", "kind": "manual_review"},
		{"name": "review", "kind": "automatic"},
		{"name": "done", "kind": "terminal_success"},
	]
	old_wd = _make_wf(key="wf", states=base_states, transitions=[
		{
			"id": "submit",
			"event": "submit",
			"from_state": "draft",
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
	])
	new_wd = _make_wf(key="wf", states=base_states, transitions=[
		{
			"id": "submit",
			"event": "submit",
			"from_state": "draft",
			"to_state": "review",
			"priority": 0,
			"guards": [],
			"gates": [],
			"effects": [],
		},
		# "approve" removed
	])

	diff = diff_workflows(old_wd, new_wd)
	assert "approve" in diff.removed_transitions, (
		f"Expected 'approve' in removed_transitions: {diff.removed_transitions}"
	)
	assert not diff.added_transitions
	assert not diff.is_empty()


# ---------------------------------------------------------------------------
# Test 5: simulate with fault returns no-match on target state
# ---------------------------------------------------------------------------

async def test_simulate_fault_no_match_on_target_state():
	"""gate_fail on 'review' should not block 'submit' (draft → review),
	but should block 'approve' (review → done)."""
	wd = _make_wf()

	fault = FaultSpec(mode=FaultMode.gate_fail, target_state="review")
	result = await simulate(
		wd,
		events=[("submit", {}), ("approve", {})],
		faults=[fault],
	)

	# submit (from draft) is not affected — should advance to review
	assert result.fire_results[0].matched_transition_id == "submit", (
		f"Expected submit to match, got {result.fire_results[0].matched_transition_id!r}"
	)

	# approve (from review) should be blocked — no matched transition
	assert result.fire_results[1].matched_transition_id is None, (
		f"Expected no match on 'approve' with gate_fail on review, "
		f"got {result.fire_results[1].matched_transition_id!r}"
	)
	# final state should be 'review' (approve was blocked)
	assert result.terminal_state == "review", (
		f"Expected terminal_state='review', got {result.terminal_state!r}"
	)


# ---------------------------------------------------------------------------
# Test 6: tutorial --domain insurance smoke (no ImportError)
#
# flowforge-jtbd-insurance has package=false (E-46 gate not yet passed), so
# it is not installed as a wheel. We test the load_bundle() helper directly
# by inserting the source tree onto sys.path, which is the same lookup the
# tutorial command does after installation.
# ---------------------------------------------------------------------------

def test_tutorial_domain_insurance_no_import_error(tmp_path):
	"""load_bundle() from flowforge-jtbd-insurance must not raise ImportError."""
	insurance_src = Path(
		"/Users/nyimbiodero/src/pjs/flowforge/python/flowforge-jtbd-insurance/src"
	)
	# Temporarily add the source tree to sys.path so the uninstalled package
	# can be imported. Remove afterwards to avoid polluting other tests.
	sys.path.insert(0, str(insurance_src))
	try:
		# Clear any cached failed import
		for mod_name in list(sys.modules.keys()):
			if "flowforge_jtbd_insurance" in mod_name:
				del sys.modules[mod_name]
		mod = importlib.import_module("flowforge_jtbd_insurance")
		assert hasattr(mod, "load_bundle"), "load_bundle() not found on module"
		bundle = mod.load_bundle()
		assert isinstance(bundle, dict), f"Expected dict, got {type(bundle)}"
		assert "jtbds" in bundle or "project" in bundle, (
			f"Bundle missing expected top-level keys: {list(bundle.keys())}"
		)
	finally:
		sys.path.remove(str(insurance_src))


# ---------------------------------------------------------------------------
# Additional: FaultInjector.should_inject and apply_to_context unit tests
# ---------------------------------------------------------------------------

def test_should_inject_returns_matching_spec():
	spec = FaultSpec(mode=FaultMode.gate_fail, target_state="review")
	injector = FaultInjector([spec])

	# matches when state matches
	result = injector.should_inject("review")
	assert result is spec

	# no match for different state
	result2 = injector.should_inject("draft")
	assert result2 is None


def test_should_inject_with_transition_id():
	spec = FaultSpec(
		mode=FaultMode.partner_404,
		target_state="review",
		target_transition_id="approve",
	)
	injector = FaultInjector([spec])

	# matches state + transition
	assert injector.should_inject("review", "approve") is spec
	# wrong transition
	assert injector.should_inject("review", "reject") is None
	# wrong state
	assert injector.should_inject("draft", "approve") is None


def test_apply_to_context_gate_fail():
	injector = FaultInjector([])
	spec = FaultSpec(mode=FaultMode.gate_fail, target_state="review")
	ctx = {"user": "alice"}
	result = injector.apply_to_context(ctx, spec)
	# original not mutated
	assert "__fault__" not in ctx
	assert result["__fault__"]["mode"] == "gate_fail"
	assert result["__fault__"]["__gate_forced_fail__"] is True
	assert result["user"] == "alice"


def test_register_appends_spec():
	injector = FaultInjector([])
	spec = FaultSpec(mode=FaultMode.doc_missing)
	injector.register(spec)
	assert spec in injector.specs


def test_workflow_diff_summary_contains_added():
	old_wd = _make_wf(key="wf", states=[
		{"name": "draft", "kind": "manual_review"},
		{"name": "done", "kind": "terminal_success"},
	], transitions=[])
	new_wd = _make_wf(key="wf", states=[
		{"name": "draft", "kind": "manual_review"},
		{"name": "review", "kind": "automatic"},
		{"name": "done", "kind": "terminal_success"},
	], transitions=[])
	diff = diff_workflows(old_wd, new_wd)
	summary = diff.summary()
	assert "+ state  review" in summary
