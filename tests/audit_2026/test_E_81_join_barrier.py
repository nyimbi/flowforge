"""E-81: join barrier — collapse instance when all parallel-branch tokens drained.

Acceptance criteria:
  - full fork → advance_a → advance_b cycle: final state is "done" (terminal_success),
    tokens list is empty after collapse.
  - After advance_a only: instance.state still "fork_point" (not collapsed), 1 token remains.
  - The FireResult from the final advance contains a "wf.<key>.join_collapsed" audit event.
  - All 8 audit-2026 conformance invariants remain green (import smoke).
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from flowforge import config as _config
from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import Instance, fire, new_instance


# ---------------------------------------------------------------------------
# Shared workflow definition — same fork/join shape used by E-79 / E-80
# ---------------------------------------------------------------------------

def _fork_workflow_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "e81_fork_test",
			"version": "1.0.0",
			"subject_kind": "e81_subject",
			"initial_state": "triage",
			"metadata": {"engine_features": ["parallel_fork"]},
			"states": [
				{"name": "triage",      "kind": "manual_review"},
				{"name": "fork_point",  "kind": "parallel_fork"},
				{"name": "branch_a",    "kind": "automatic"},
				{"name": "branch_b",    "kind": "automatic"},
				{"name": "join",        "kind": "parallel_join"},
				{"name": "done",        "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "triage_to_fork",
					"event": "ready",
					"from_state": "triage",
					"to_state": "fork_point",
					"priority": 0,
				},
				{
					"id": "fork_to_a",
					"event": "__auto__",
					"from_state": "fork_point",
					"to_state": "branch_a",
					"priority": 1,
				},
				{
					"id": "fork_to_b",
					"event": "__auto__",
					"from_state": "fork_point",
					"to_state": "branch_b",
					"priority": 0,
				},
				{
					"id": "a_to_join",
					"event": "a_done",
					"from_state": "branch_a",
					"to_state": "join",
					"priority": 0,
				},
				{
					"id": "b_to_join",
					"event": "b_done",
					"from_state": "branch_b",
					"to_state": "join",
					"priority": 0,
				},
				{
					"id": "join_to_done",
					"event": "join_complete",
					"from_state": "join",
					"to_state": "done",
					"priority": 0,
				},
			],
		}
	)


def _run(coro):
	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		return loop.run_until_complete(coro)
	finally:
		loop.close()


def _setup_forked_instance(monkeypatch):
	"""Helper: create instance, fire "ready" to produce fork + 2 tokens.

	Returns (wd, inst, token_a, token_b).
	"""
	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "1")
	_config.reset_to_fakes()

	wd = _fork_workflow_def()
	inst = new_instance(wd)

	_run(fire(wd, inst, "ready"))
	assert inst.state == "fork_point"

	tokens = inst.tokens.list()
	assert len(tokens) == 2
	token_by_state = {t.state: t for t in tokens}
	token_a = token_by_state["branch_a"]
	token_b = token_by_state["branch_b"]
	return wd, inst, token_a, token_b


# ---------------------------------------------------------------------------
# test_E_81_join_collapses_when_all_drained
# ---------------------------------------------------------------------------

def test_E_81_join_collapses_when_all_drained(monkeypatch) -> None:
	"""Full cycle: fork → advance_a → advance_b → join collapses → state='done'."""

	wd, inst, token_a, token_b = _setup_forked_instance(monkeypatch)

	# Advance branch_a — join not yet complete (branch_b still alive)
	result_a = _run(fire(wd, inst, "a_done", token_id=token_a.id))
	assert result_a.matched_transition_id == "a_to_join"
	# Primary state must NOT have collapsed yet
	assert inst.state == "fork_point", (
		f"expected state='fork_point' after first advance, got {inst.state!r}"
	)
	assert len(inst.tokens.list()) == 1, "token_a should have been consumed"

	# Advance branch_b — this drains the last token → collapse
	result_b = _run(fire(wd, inst, "b_done", token_id=token_b.id))
	assert result_b.matched_transition_id == "b_to_join"

	# After collapse the instance must be at the terminal state
	assert inst.state == "done", (
		f"expected state='done' after join collapse, got {inst.state!r}"
	)
	assert result_b.new_state == "done"
	assert result_b.terminal is True

	# Token set must be empty — all tokens consumed
	assert inst.tokens.list() == [], (
		f"expected empty token list, got {inst.tokens.list()}"
	)


# ---------------------------------------------------------------------------
# test_E_81_join_blocked_while_tokens_alive
# ---------------------------------------------------------------------------

def test_E_81_join_blocked_while_tokens_alive(monkeypatch) -> None:
	"""After advancing only branch_a: primary state still 'fork_point', 1 token remains."""

	wd, inst, token_a, token_b = _setup_forked_instance(monkeypatch)

	_run(fire(wd, inst, "a_done", token_id=token_a.id))

	# Primary state has NOT collapsed — branch_b token still outstanding
	assert inst.state == "fork_point", (
		f"expected primary state='fork_point', got {inst.state!r}"
	)

	remaining = inst.tokens.list()
	assert len(remaining) == 1, f"expected 1 token outstanding, got {remaining}"
	assert remaining[0].id == token_b.id


# ---------------------------------------------------------------------------
# test_E_81_audit_events_contain_join_collapsed
# ---------------------------------------------------------------------------

def test_E_81_audit_events_contain_join_collapsed(monkeypatch) -> None:
	"""FireResult from the final advance contains a 'wf.<key>.join_collapsed' event."""

	wd, inst, token_a, token_b = _setup_forked_instance(monkeypatch)

	_run(fire(wd, inst, "a_done", token_id=token_a.id))
	result_b = _run(fire(wd, inst, "b_done", token_id=token_b.id))

	join_events = [
		e for e in result_b.audit_events
		if e.kind == "wf.e81_fork_test.join_collapsed"
	]
	assert len(join_events) == 1, (
		f"expected 1 join_collapsed audit event, got {[e.kind for e in result_b.audit_events]}"
	)

	ev = join_events[0]
	assert ev.payload["join_state"] == "join"
	assert ev.payload["final_state"] == "done"
	assert ev.payload["region"] == "fork_point"


# ---------------------------------------------------------------------------
# test_E_81_all_8_invariants_green
# ---------------------------------------------------------------------------

def test_E_81_all_8_invariants_green() -> None:
	"""Smoke: conformance suite importable; E-81 symbols present."""

	conf_path = (
		pathlib.Path(__file__).resolve().parents[1] / "conformance" / "test_arch_invariants.py"
	)
	assert conf_path.exists(), f"conformance suite missing: {conf_path}"

	# All E-81 symbols must be importable without error.
	from flowforge.engine.fire import (  # noqa: F401
		ConcurrentFireRejected,
		Instance,
		OutboxDispatchError,
		fire,
		new_instance,
	)
	from flowforge.engine._fork import (  # noqa: F401
		RegionStillForkedError,
		TokenAlreadyConsumedError,
		all_branches_joined,
		consume_token,
		make_fork_tokens,
	)
	from flowforge.engine.fork_config import forks_enabled, workflow_declares_fork  # noqa: F401
	from flowforge.engine.tokens import Token, TokenSet  # noqa: F401
