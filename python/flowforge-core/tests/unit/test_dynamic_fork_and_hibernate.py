"""Tests for dynamic_fork and hibernate modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.dsl.workflow_def import State
from flowforge.engine import (
	WakeScheduler,
	begin_fork,
	begin_hibernate,
	clear_fork,
	collect_branch_result,
	collect_fork_results,
	compact_history,
	fire,
	is_due_for_wake,
	is_fork_complete,
	new_instance,
)
from flowforge.engine.dynamic_fork import DynamicForkError, ForkState


# ---------------------------------------------------------------------------
# Dynamic Fork
# ---------------------------------------------------------------------------

def _map_state(name: str = "process_items") -> State:
	return State(name=name, kind="parallel_map", fork_items_expr="items")


def test_begin_fork_reads_context_list():
	from uuid6 import uuid7
	context = {"items": ["a", "b", "c"]}
	fork = begin_fork(context, _map_state(), fork_id=str(uuid7()))
	assert len(fork.branches) == 3
	assert fork.items == ["a", "b", "c"]
	assert all(b.status == "pending" for b in fork.branches)
	assert "__fork__" in context


def test_begin_fork_raises_if_no_expr():
	state = State(name="s", kind="parallel_map")  # no fork_items_expr
	with pytest.raises(DynamicForkError, match="fork_items_expr"):
		begin_fork({}, state, fork_id="x")


def test_begin_fork_raises_if_not_list():
	state = _map_state()
	with pytest.raises(DynamicForkError, match="list"):
		begin_fork({"items": "not_a_list"}, state, fork_id="x")


def test_begin_fork_empty_list():
	state = _map_state()
	fork = begin_fork({"items": []}, state, fork_id="x")
	assert fork.branches == []
	assert is_fork_complete({"items": [], "__fork__": fork.to_dict()})


def test_collect_branch_result_complete():
	state = _map_state()
	context: dict = {"items": [1, 2]}
	begin_fork(context, state, fork_id="f1")
	collect_branch_result(context, 0, result={"score": 10})
	fork = ForkState.from_context(context)
	assert fork is not None
	assert fork.branches[0].status == "complete"
	assert fork.branches[0].result == {"score": 10}
	assert fork.branches[1].status == "pending"


def test_collect_branch_result_failed():
	state = _map_state()
	context: dict = {"items": [1]}
	begin_fork(context, state, fork_id="f2")
	collect_branch_result(context, 0, error="timeout")
	fork = ForkState.from_context(context)
	assert fork is not None
	assert fork.branches[0].status == "failed"
	assert fork.branches[0].error == "timeout"


def test_collect_branch_raises_no_fork():
	with pytest.raises(DynamicForkError, match="no active fork"):
		collect_branch_result({}, 0)


def test_collect_branch_raises_out_of_range():
	state = _map_state()
	context: dict = {"items": [1]}
	begin_fork(context, state, fork_id="f3")
	with pytest.raises(DynamicForkError, match="out of range"):
		collect_branch_result(context, 5)


def test_is_fork_complete_all_policy():
	state = _map_state()
	context: dict = {"items": [1, 2, 3]}
	begin_fork(context, state, fork_id="f4", policy="all_complete")
	assert not is_fork_complete(context)

	collect_branch_result(context, 0, result=1)
	collect_branch_result(context, 1, result=2)
	assert not is_fork_complete(context)

	collect_branch_result(context, 2, result=3)
	assert is_fork_complete(context)


def test_is_fork_complete_any_policy():
	state = _map_state()
	context: dict = {"items": [1, 2, 3]}
	begin_fork(context, state, fork_id="f5", policy="any_complete")
	assert not is_fork_complete(context)

	collect_branch_result(context, 0, result=1)
	assert is_fork_complete(context)  # only one needed


def test_collect_fork_results_ordered():
	state = _map_state()
	context: dict = {"items": ["x", "y", "z"]}
	begin_fork(context, state, fork_id="f6")
	collect_branch_result(context, 2, result="result_z")
	collect_branch_result(context, 0, result="result_x")
	collect_branch_result(context, 1, result="result_y")
	results = collect_fork_results(context)
	assert results == ["result_x", "result_y", "result_z"]


def test_clear_fork_removes_key():
	state = _map_state()
	context: dict = {"items": [1]}
	begin_fork(context, state, fork_id="f7")
	assert "__fork__" in context
	clear_fork(context)
	assert "__fork__" not in context


def test_no_active_fork_returns_false():
	assert not is_fork_complete({})


# ---------------------------------------------------------------------------
# Hibernate
# ---------------------------------------------------------------------------

def _hibernate_def() -> WorkflowDef:
	return WorkflowDef.model_validate({
		"key": "hibernate_flow",
		"version": "1.0.0",
		"subject_kind": "job",
		"initial_state": "active",
		"states": [
			{"name": "active", "kind": "automatic"},
			{"name": "sleeping", "kind": "hibernate", "hibernate_seconds": 3600},
			{"name": "resumed", "kind": "automatic"},
			{"name": "done", "kind": "terminal_success"},
		],
		"transitions": [
			{"id": "t1", "event": "pause", "from_state": "active", "to_state": "sleeping", "priority": 0},
			{"id": "t2", "event": "wake", "from_state": "sleeping", "to_state": "resumed", "priority": 0},
			{"id": "t3", "event": "complete", "from_state": "resumed", "to_state": "done", "priority": 0},
		],
	})


def test_begin_hibernate_writes_record():
	wd = _hibernate_def()
	state_def = next(s for s in wd.states if s.name == "sleeping")
	instance = new_instance(wd)
	now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
	record = begin_hibernate(instance, state_def, now=now)
	assert record.hibernate_seconds == 3600
	assert record.wake_at is not None
	assert record.wake_at == now + timedelta(seconds=3600)
	assert "__hibernate__" in instance.context


def test_begin_hibernate_no_wake_time_when_zero_seconds():
	state = State(name="sleep", kind="hibernate", hibernate_seconds=0)
	wd = _hibernate_def()
	instance = new_instance(wd)
	record = begin_hibernate(instance, state)
	assert record.wake_at is None


def test_is_due_for_wake_false_before_time():
	wd = _hibernate_def()
	state_def = next(s for s in wd.states if s.name == "sleeping")
	instance = new_instance(wd)
	now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
	begin_hibernate(instance, state_def, now=now)
	assert not is_due_for_wake(instance, now=now + timedelta(seconds=1800))


def test_is_due_for_wake_true_after_time():
	wd = _hibernate_def()
	state_def = next(s for s in wd.states if s.name == "sleeping")
	instance = new_instance(wd)
	now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
	begin_hibernate(instance, state_def, now=now)
	assert is_due_for_wake(instance, now=now + timedelta(seconds=4000))


def test_is_due_for_wake_false_with_no_hibernate_context():
	wd = _hibernate_def()
	instance = new_instance(wd)
	assert not is_due_for_wake(instance)


async def test_wake_scheduler_fires_wake_on_due_instance():
	config.reset_to_fakes()
	wd = _hibernate_def()
	instance = new_instance(wd)
	# advance to sleeping state
	await fire(wd, instance, "pause", dispatch_ports=False)
	assert instance.state == "sleeping"

	state_def = next(s for s in wd.states if s.name == "sleeping")
	now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
	begin_hibernate(instance, state_def, now=now)

	from flowforge.engine.hibernate import HibernationCandidate
	scheduler = WakeScheduler()
	# before due time — no wake
	results = await scheduler.check_hibernations(
		[HibernationCandidate(instance=instance, wd=wd)],
		now=now + timedelta(seconds=1800),
		dispatch_ports=False,
	)
	assert results == []

	# after due time — fires wake
	results = await scheduler.check_hibernations(
		[HibernationCandidate(instance=instance, wd=wd)],
		now=now + timedelta(seconds=4000),
		dispatch_ports=False,
	)
	assert len(results) == 1
	assert results[0].fired is True
	assert instance.state == "resumed"


def test_compact_history_reduces_long_history():
	wd = _hibernate_def()
	instance = new_instance(wd)
	instance.history = [f"step_{i}" for i in range(200)]
	removed = compact_history(instance, keep=20)
	assert removed == 180
	assert len(instance.history) == 21  # 1 summary + 20 kept
	assert "[compacted" in instance.history[0]


def test_compact_history_does_nothing_for_short_history():
	wd = _hibernate_def()
	instance = new_instance(wd)
	instance.history = ["a", "b", "c"]
	removed = compact_history(instance)
	assert removed == 0
	assert instance.history == ["a", "b", "c"]
