"""E-74p1 — Instance.tokens snapshot field.

Adds TokenSet to the Instance dataclass and keeps it consistent through
snapshot/restore and shallow-clone (copy-on-read) paths.

R-2 mitigation: tokens are NOT included in the canonical audit body —
they travel in snapshot metadata only, preserving E-37 invariant 7.
"""

from __future__ import annotations

from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import (
	Instance,
	_restore_instance,
	_snapshot_instance,
	new_instance,
)
from flowforge.engine.snapshots import InMemorySnapshotStore
from flowforge.engine.tokens import Token, TokenSet
from flowforge._uuid7 import uuid7str


# ---------------------------------------------------------------------------
# Minimal WorkflowDef fixture
# ---------------------------------------------------------------------------

def _simple_wd() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "e74p1",
			"version": "1.0.0",
			"subject_kind": "item",
			"initial_state": "pending",
			"states": [
				{"name": "pending", "kind": "manual_review"},
				{"name": "done", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "t1",
					"from_state": "pending",
					"to_state": "done",
					"event": "finish",
					"priority": 0,
					"guards": [],
					"effects": [],
				}
			],
		}
	)


def _two_tokens() -> tuple[Token, Token]:
	t1 = Token(id=uuid7str(), region="branch_a", state="running", context={"x": 1})
	t2 = Token(id=uuid7str(), region="branch_b", state="waiting", context={"y": 2})
	return t1, t2


# ---------------------------------------------------------------------------
# test_E_74p1_instance_tokens_field
# ---------------------------------------------------------------------------


def test_E_74p1_instance_tokens_field() -> None:
	"""new_instance() produces an instance with an empty TokenSet."""
	wd = _simple_wd()
	inst = new_instance(wd)
	assert isinstance(inst.tokens, TokenSet)
	assert inst.tokens.list() == []


# ---------------------------------------------------------------------------
# test_E_74p1_snapshot_round_trip_empty_tokens
# ---------------------------------------------------------------------------


def test_E_74p1_snapshot_round_trip_empty_tokens() -> None:
	"""Snapshot + restore with no tokens preserves empty TokenSet."""
	wd = _simple_wd()
	inst = new_instance(wd)

	snap = _snapshot_instance(inst)
	assert snap["tokens"] == []

	# mutate to confirm restore resets
	inst.tokens.add(Token(id=uuid7str(), region="r", state="s", context={}))
	_restore_instance(inst, snap)

	assert isinstance(inst.tokens, TokenSet)
	assert inst.tokens.list() == []


# ---------------------------------------------------------------------------
# test_E_74p1_snapshot_round_trip_with_tokens
# ---------------------------------------------------------------------------


def test_E_74p1_snapshot_round_trip_with_tokens() -> None:
	"""Snapshot captures tokens; restore reconstructs them with identical fields."""
	wd = _simple_wd()
	inst = new_instance(wd)

	t1, t2 = _two_tokens()
	inst.tokens.add(t1)
	inst.tokens.add(t2)

	snap = _snapshot_instance(inst)
	assert len(snap["tokens"]) == 2

	# Wipe tokens on the live instance to prove restore re-builds them.
	inst.tokens = TokenSet()

	_restore_instance(inst, snap)

	restored = {t.id: t for t in inst.tokens.list()}
	assert len(restored) == 2

	r1 = restored[t1.id]
	assert r1.region == t1.region
	assert r1.state == t1.state
	assert r1.context == t1.context

	r2 = restored[t2.id]
	assert r2.region == t2.region
	assert r2.state == t2.state
	assert r2.context == t2.context


# ---------------------------------------------------------------------------
# test_E_74p1_shallow_clone_isolates_tokens
# ---------------------------------------------------------------------------


def test_E_74p1_shallow_clone_isolates_tokens() -> None:
	"""Tokens in a stored snapshot are isolated from the caller's copy."""
	import asyncio

	async def _run() -> None:
		wd = _simple_wd()
		inst = new_instance(wd)

		t1, t2 = _two_tokens()
		inst.tokens.add(t1)
		inst.tokens.add(t2)

		store = InMemorySnapshotStore()
		await store.put(inst)

		# get() returns a shallow clone
		clone = await store.get(inst.id)
		assert clone is not None
		assert len(clone.tokens.list()) == 2

		# mutate the clone — should NOT bleed back into the stored copy
		extra = Token(id=uuid7str(), region="branch_c", state="new", context={})
		clone.tokens.add(extra)
		assert len(clone.tokens.list()) == 3

		# fetch again from store — still 2 tokens
		fresh = await store.get(inst.id)
		assert fresh is not None
		assert len(fresh.tokens.list()) == 2

	loop = asyncio.get_event_loop()
	loop.run_until_complete(_run())


# ---------------------------------------------------------------------------
# test_invariant_3_replay_determinism — engine import chain intact
# ---------------------------------------------------------------------------


def test_invariant_3_tokens_field_does_not_break_engine_import() -> None:
	"""Smoke-check: importing the engine after the tokens field addition
	succeeds and Instance still round-trips through new_instance() cleanly.

	The full conformance/replay-determinism invariant suite runs under
	``make audit-2026-conformance``; this test just pins that the engine
	module is importable and structurally sound post-change.
	"""
	from flowforge.engine import fire as fire_mod
	from flowforge.engine.fire import Instance

	wd = _simple_wd()
	inst = new_instance(wd)

	# Core fields intact
	assert inst.id
	assert inst.state == "pending"
	# TokenSet field present and empty
	assert isinstance(inst.tokens, TokenSet)
	assert inst.tokens.list() == []
	# Instance is a dataclass — fields include "tokens"
	import dataclasses
	field_names = {f.name for f in dataclasses.fields(inst)}
	assert "tokens" in field_names
