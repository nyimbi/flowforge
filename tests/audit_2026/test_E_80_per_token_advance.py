"""E-80: per-token advance in fire() via token_id parameter.

Acceptance criteria:
  - fire("ready") into fork_point → 2 tokens created.
  - fire("a_done", token_id=tokens[0].id) → token 0 advances to "join".
  - fire with nonexistent token_id → TokenAlreadyConsumedError + metric emitted.
  - primary fire (no token_id) while tokens live → RegionStillForkedError.
  - All 8 audit-2026 conformance invariants remain green (import smoke).
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from flowforge import config as _config
from flowforge.dsl import WorkflowDef
from flowforge.engine._fork import RegionStillForkedError, TokenAlreadyConsumedError
from flowforge.engine.fire import Instance, fire, new_instance
from flowforge.testing.port_fakes import InMemoryAuditSink, InMemoryOutbox


# ---------------------------------------------------------------------------
# Shared fixture: reuse the fork workflow from E-79 tests
# ---------------------------------------------------------------------------

def _fork_workflow_def(*, with_engine_features: bool = True) -> WorkflowDef:
	meta: dict = {}
	if with_engine_features:
		meta = {"engine_features": ["parallel_fork"]}
	return WorkflowDef.model_validate(
		{
			"key": "e80_fork_test",
			"version": "1.0.0",
			"subject_kind": "e80_subject",
			"initial_state": "triage",
			"metadata": meta,
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


# ---------------------------------------------------------------------------
# test_E_80_per_token_advance
# ---------------------------------------------------------------------------

def test_E_80_per_token_advance(monkeypatch) -> None:
	"""fire("ready") → fork creates 2 tokens.
	fire("a_done", token_id=<branch_a token>) → that token advances to "join".
	Token for branch_b remains unchanged."""

	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "1")
	_config.reset_to_fakes()

	wd = _fork_workflow_def(with_engine_features=True)
	inst = new_instance(wd)

	# Step 1: fire "ready" → fork_point → 2 tokens
	result1 = _run(fire(wd, inst, "ready"))
	assert result1.matched_transition_id == "triage_to_fork"
	assert inst.state == "fork_point"

	tokens = inst.tokens.list()
	assert len(tokens) == 2, f"expected 2 tokens, got {tokens}"
	assert all(t.region == "fork_point" for t in tokens)
	token_by_state = {t.state: t for t in tokens}
	assert set(token_by_state.keys()) == {"branch_a", "branch_b"}

	token_a = token_by_state["branch_a"]
	token_b = token_by_state["branch_b"]

	# Step 2: advance branch_a token with "a_done"
	result2 = _run(fire(wd, inst, "a_done", token_id=token_a.id))
	assert result2.matched_transition_id == "a_to_join"

	# token_a lands on a parallel_join state → E-81 consumes it immediately.
	# After E-81 consume, token_a must NOT be in the live set (consumed).
	# token_b must still be present and untouched.
	updated_tokens = {t.id: t for t in inst.tokens.list()}
	assert token_a.id not in updated_tokens, (
		f"expected token_a to be consumed by join barrier, but still present: {updated_tokens}"
	)
	assert token_b.id in updated_tokens, (
		f"expected token_b still live, but missing from: {updated_tokens}"
	)
	assert updated_tokens[token_b.id].state == "branch_b"

	# Primary instance state unchanged (still at fork_point)
	assert inst.state == "fork_point"

	# An audit event for the token advance must be present
	token_audits = [e for e in result2.audit_events if e.kind == "wf.e80_fork_test.token_advanced"]
	assert len(token_audits) == 1
	ta = token_audits[0]
	assert ta.payload["token_id"] == token_a.id
	assert ta.payload["from_state"] == "branch_a"
	assert ta.payload["to_state"] == "join"
	assert ta.payload["event"] == "a_done"

	# History entry for the token advance
	assert any(f"token:{token_a.id}" in h for h in inst.history), (
		f"expected token history entry, got {inst.history}"
	)


# ---------------------------------------------------------------------------
# test_E_80_unknown_token_raises
# ---------------------------------------------------------------------------

def test_E_80_unknown_token_raises(monkeypatch) -> None:
	"""fire with a nonexistent token_id raises TokenAlreadyConsumedError
	and emits the flowforge_token_unknown_advance_total metric."""

	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "1")
	_config.reset_to_fakes()

	# reset_to_fakes() sets up InMemoryMetrics on config.metrics already
	from flowforge.testing.port_fakes import InMemoryMetrics
	import flowforge.config as _cfg_mod
	metrics_sink = InMemoryMetrics()
	_cfg_mod.metrics = metrics_sink

	wd = _fork_workflow_def(with_engine_features=True)
	inst = new_instance(wd)

	# Fork first so the instance has a sane state
	_run(fire(wd, inst, "ready"))

	with pytest.raises(TokenAlreadyConsumedError):
		_run(fire(wd, inst, "a_done", token_id="does-not-exist"))

	# Check metric was emitted (stored in .points as (name, value, labels))
	emitted_names = [m[0] for m in metrics_sink.points]
	assert "flowforge_token_unknown_advance_total" in emitted_names, (
		f"expected metric not found; emitted={emitted_names}"
	)


# ---------------------------------------------------------------------------
# test_E_80_primary_blocked_while_forked
# ---------------------------------------------------------------------------

def test_E_80_primary_blocked_while_forked(monkeypatch) -> None:
	"""After fork, a primary fire (no token_id) raises RegionStillForkedError."""

	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "1")
	_config.reset_to_fakes()

	wd = _fork_workflow_def(with_engine_features=True)
	inst = new_instance(wd)

	# Fork
	_run(fire(wd, inst, "ready"))
	assert len(inst.tokens.list()) == 2

	# Primary fire without token_id must be rejected
	with pytest.raises(RegionStillForkedError):
		_run(fire(wd, inst, "a_done"))


# ---------------------------------------------------------------------------
# test_E_80_all_8_invariants_green
# ---------------------------------------------------------------------------

def test_E_80_all_8_invariants_green() -> None:
	"""Smoke: conformance suite is importable; E-80 additions don't break imports."""

	conf_path = (
		pathlib.Path(__file__).resolve().parents[1] / "conformance" / "test_arch_invariants.py"
	)
	assert conf_path.exists(), f"conformance suite missing: {conf_path}"

	# All E-80 symbols must be importable.
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
		_has_token,
		consume_token,
		make_fork_tokens,
	)
	from flowforge.engine.fork_config import forks_enabled, workflow_declares_fork  # noqa: F401
	from flowforge.engine.tokens import Token, TokenSet  # noqa: F401
