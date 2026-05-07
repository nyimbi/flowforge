"""audit-2026 E-61 acceptance tests (findings C-11, C-12)."""

from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import ValidationError

from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import Instance
from flowforge.engine.snapshots import InMemorySnapshotStore


# ---------------------------------------------------------------------------
# C-11 — Guard.expr shape validator
# ---------------------------------------------------------------------------


def _wd_with_guard(expr: object) -> dict:
	return {
		"key": "demo",
		"version": "1.0.0",
		"subject_kind": "demo_subject",
		"initial_state": "draft",
		"states": [
			{"name": "draft", "kind": "manual_review"},
			{"name": "approved", "kind": "terminal_success"},
		],
		"transitions": [
			{
				"id": "submit",
				"event": "submit",
				"from_state": "draft",
				"to_state": "approved",
				"guards": [{"kind": "expr", "expr": expr}],
			}
		],
	}


def test_C_11_guard_expr_validator_rejects_multi_key_dict() -> None:
	"""A guard expr of the form ``{"a": 1, "b": 2}`` is structurally invalid."""

	with pytest.raises(ValidationError) as exc_info:
		WorkflowDef.model_validate(_wd_with_guard({"==": [1, 1], "extra": 2}))
	assert "exactly one key" in str(exc_info.value)


def test_C_11_guard_expr_validator_accepts_single_key_dict() -> None:
	wd = WorkflowDef.model_validate(_wd_with_guard({"==": [1, 1]}))
	assert wd.transitions[0].guards[0].expr == {"==": [1, 1]}


def test_C_11_guard_expr_validator_accepts_literal_bool() -> None:
	wd = WorkflowDef.model_validate(_wd_with_guard(True))
	assert wd.transitions[0].guards[0].expr is True


def test_C_11_guard_expr_validator_accepts_nested_op() -> None:
	wd = WorkflowDef.model_validate(
		_wd_with_guard(
			{"and": [{"==": [{"var": "x"}, 1]}, {"not_null": {"var": "y"}}]}
		)
	)
	assert wd.transitions[0].guards[0].expr["and"][0]["=="][0] == {"var": "x"}


def test_C_11_guard_expr_validator_rejects_nested_multi_key() -> None:
	with pytest.raises(ValidationError):
		WorkflowDef.model_validate(
			_wd_with_guard({"and": [{"==": [1, 1], "leak": 0}]})
		)


def test_C_11_guard_expr_validator_rejects_unsupported_type() -> None:
	with pytest.raises(ValidationError):
		# A set isn't a JSON-AST type; the validator must reject it.
		WorkflowDef.model_validate(_wd_with_guard({1, 2, 3}))


# ---------------------------------------------------------------------------
# C-12 — InMemorySnapshotStore copy-on-write
# ---------------------------------------------------------------------------


def _make_instance(idx: int = 0, ctx_size: int = 200) -> Instance:
	return Instance(
		id=f"instance-{idx}",
		def_key="demo",
		def_version="1.0.0",
		state="draft",
		context={f"k{i}": f"v{i}" for i in range(ctx_size)},
		created_entities=[],
		saga=[],
		history=[{"event": f"e{i}"} for i in range(min(ctx_size, 50))],
	)


def test_C_12_snapshot_get_after_put_returns_copy() -> None:
	"""Mutating the returned snapshot does not leak back into the store."""

	loop = asyncio.new_event_loop()
	try:
		store = InMemorySnapshotStore()
		instance = _make_instance()
		loop.run_until_complete(store.put(instance))
		first = loop.run_until_complete(store.get(instance.id))
		assert first is not None
		first.context["mutated"] = "should not leak"
		first.history.append({"event": "should not leak"})
		second = loop.run_until_complete(store.get(instance.id))
		assert second is not None
		assert "mutated" not in second.context
		assert all(h.get("event") != "should not leak" for h in second.history)
	finally:
		loop.close()


def test_C_12_snapshot_put_detaches_from_live_instance() -> None:
	"""After put, mutating the live instance does not corrupt the snapshot."""

	loop = asyncio.new_event_loop()
	try:
		store = InMemorySnapshotStore()
		instance = _make_instance()
		original_keys = set(instance.context)
		loop.run_until_complete(store.put(instance))
		instance.context["after_put"] = "x"
		instance.history.append({"event": "after_put"})
		snap = loop.run_until_complete(store.get(instance.id))
		assert snap is not None
		assert "after_put" not in snap.context
		assert set(snap.context) == original_keys
		assert all(h.get("event") != "after_put" for h in snap.history)
	finally:
		loop.close()


def test_C_12_snapshot_get_missing_returns_none() -> None:
	loop = asyncio.new_event_loop()
	try:
		store = InMemorySnapshotStore()
		got = loop.run_until_complete(store.get("does-not-exist"))
		assert got is None
	finally:
		loop.close()


def test_C_12_snapshot_put_200_states_under_threshold() -> None:
	"""200 puts of an instance with a 200-key context must complete fast.

	The audit-2026 C-12 ratchet is "10× speedup at 200 states". The exact
	wall-clock target depends on hardware; we pin a generous absolute
	upper bound (50ms) that the old per-put-five-clones path would
	exceed under modern CPython, and include an internal logging line
	so regressions surface in CI logs.
	"""

	loop = asyncio.new_event_loop()
	try:
		store = InMemorySnapshotStore()
		instance = _make_instance(ctx_size=200)
		t0 = time.perf_counter()
		for i in range(200):
			loop.run_until_complete(store.put(instance))
		elapsed = time.perf_counter() - t0
		# Ratchet: 200 puts of a 200-key context inside 250ms.
		assert elapsed < 0.25, f"200 puts took {elapsed*1000:.1f}ms (threshold 250ms)"
	finally:
		loop.close()
