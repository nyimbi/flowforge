"""Tests for the workflow replay debugger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flowforge.dsl import WorkflowDef
from flowforge.engine.replay import ReplayResult, ReplayStep, replay_from_events, replay_summary
from flowforge.ports.types import AuditEvent


def _approval_wd() -> WorkflowDef:
	return WorkflowDef.model_validate({
		"key": "approval",
		"version": "1.0.0",
		"subject_kind": "request",
		"initial_state": "pending",
		"states": [
			{"name": "pending", "kind": "signal_wait"},
			{"name": "approved", "kind": "terminal_success"},
			{"name": "rejected", "kind": "terminal_fail"},
		],
		"transitions": [
			{"id": "a", "event": "approve", "from_state": "pending", "to_state": "approved", "priority": 0},
			{"id": "r", "event": "reject", "from_state": "pending", "to_state": "rejected", "priority": 0},
		],
	})


def _event(kind: str, subject_id: str, payload: dict, offset_secs: int = 0) -> AuditEvent:
	return AuditEvent(
		kind=kind,
		subject_kind="request",
		subject_id=subject_id,
		tenant_id="default",
		actor_user_id="user1",
		payload=payload,
		occurred_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_secs),
	)


def test_replay_single_step():
	wd = _approval_wd()
	events = [
		_event("wf.approval.transitioned", "inst1", {
			"event": "approve", "from_state": "pending", "to_state": "approved"
		}),
	]
	result = replay_from_events(wd, events, instance_id="inst1")
	assert result.is_consistent
	assert len(result.steps) == 1
	assert result.steps[0].from_state == "pending"
	assert result.steps[0].to_state == "approved"
	assert result.steps[0].event == "approve"
	assert result.final_state == "approved"


def test_replay_multiple_steps_ordered_by_time():
	wd = WorkflowDef.model_validate({
		"key": "multi",
		"version": "1.0.0",
		"subject_kind": "x",
		"initial_state": "a",
		"states": [
			{"name": "a", "kind": "automatic"},
			{"name": "b", "kind": "automatic"},
			{"name": "c", "kind": "terminal_success"},
		],
		"transitions": [
			{"id": "t1", "event": "go_b", "from_state": "a", "to_state": "b", "priority": 0},
			{"id": "t2", "event": "go_c", "from_state": "b", "to_state": "c", "priority": 0},
		],
	})
	# Add events out of order — should be sorted by occurred_at
	events = [
		_event("wf.multi.transitioned", "i1", {"event": "go_c", "from_state": "b", "to_state": "c"}, offset_secs=2),
		_event("wf.multi.transitioned", "i1", {"event": "go_b", "from_state": "a", "to_state": "b"}, offset_secs=1),
	]
	result = replay_from_events(wd, events, instance_id="i1")
	assert result.is_consistent
	assert result.steps[0].event == "go_b"
	assert result.steps[1].event == "go_c"
	assert result.final_state == "c"


def test_replay_detects_state_inconsistency():
	wd = _approval_wd()
	events = [
		_event("wf.approval.transitioned", "i2", {
			"event": "approve", "from_state": "wrong_state", "to_state": "approved"
		}),
	]
	result = replay_from_events(wd, events, instance_id="i2")
	assert not result.is_consistent
	assert len(result.errors) >= 1


def test_replay_detects_unknown_state():
	wd = _approval_wd()
	events = [
		_event("wf.approval.transitioned", "i3", {
			"event": "approve", "from_state": "pending", "to_state": "ghost_state"
		}),
	]
	result = replay_from_events(wd, events, instance_id="i3")
	assert not result.is_consistent
	assert any("ghost_state" in e for e in result.errors)


def test_replay_skips_non_transition_events():
	wd = _approval_wd()
	events = [
		_event("wf.approval.created", "i4", {"msg": "instance created"}),
		_event("wf.approval.transitioned", "i4", {
			"event": "approve", "from_state": "pending", "to_state": "approved"
		}, offset_secs=1),
		_event("wf.approval.audited", "i4", {"actor": "bob"}),
	]
	result = replay_from_events(wd, events, instance_id="i4")
	assert len(result.steps) == 1
	assert result.is_consistent


def test_replay_skips_events_for_other_workflows():
	wd = _approval_wd()
	events = [
		_event("wf.other_flow.transitioned", "i5", {
			"event": "go", "from_state": "start", "to_state": "end"
		}),
		_event("wf.approval.transitioned", "i5", {
			"event": "approve", "from_state": "pending", "to_state": "approved"
		}, offset_secs=1),
	]
	result = replay_from_events(wd, events, instance_id="i5")
	assert len(result.steps) == 1


def test_replay_empty_events():
	wd = _approval_wd()
	result = replay_from_events(wd, [], instance_id="i6")
	assert result.steps == []
	assert result.is_consistent
	assert result.final_state == "pending"  # initial state


def test_replay_infers_instance_id_from_event():
	wd = _approval_wd()
	events = [
		_event("wf.approval.transitioned", "inferred-id", {
			"event": "approve", "from_state": "pending", "to_state": "approved"
		}),
	]
	result = replay_from_events(wd, events)  # no instance_id
	assert result.instance_id == "inferred-id"


def test_replay_summary_returns_string():
	wd = _approval_wd()
	events = [
		_event("wf.approval.transitioned", "s1", {
			"event": "reject", "from_state": "pending", "to_state": "rejected"
		}),
	]
	result = replay_from_events(wd, events, instance_id="s1")
	summary = replay_summary(result)
	assert "s1" in summary
	assert "pending" in summary
	assert "rejected" in summary


def test_state_after_step():
	wd = WorkflowDef.model_validate({
		"key": "seq",
		"version": "1.0.0",
		"subject_kind": "x",
		"initial_state": "a",
		"states": [
			{"name": "a", "kind": "automatic"},
			{"name": "b", "kind": "automatic"},
			{"name": "c", "kind": "terminal_success"},
		],
		"transitions": [
			{"id": "t1", "event": "go_b", "from_state": "a", "to_state": "b", "priority": 0},
			{"id": "t2", "event": "go_c", "from_state": "b", "to_state": "c", "priority": 0},
		],
	})
	events = [
		_event("wf.seq.transitioned", "x", {"event": "go_b", "from_state": "a", "to_state": "b"}, 1),
		_event("wf.seq.transitioned", "x", {"event": "go_c", "from_state": "b", "to_state": "c"}, 2),
	]
	result = replay_from_events(wd, events, instance_id="x")
	assert result.state_after_step(0) == "b"
	assert result.state_after_step(1) == "c"
