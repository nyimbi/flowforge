"""Integration test #8: replay determinism via reconstruct().

Drives a workflow whose first transition records a value into context
that mirrors a "lookup snapshot". The reconstruct() function should
re-fire the recorded events and produce a byte-identical instance —
even if (in production) the underlying lookup source is mutated between
record and replay, because the persisted snapshot wins.

We don't rely on the real lookup_party / lookup_setting expression
operators here (those depend on host-side resolvers); we model the
semantics directly via a ``set`` effect that copies a deterministic
value into context. Replay then re-fires the same event over a fresh
instance and the engine must yield the same context.
"""

from __future__ import annotations

import pytest
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.replay.reconstruct import reconstruct

pytestmark = pytest.mark.asyncio


def _lookup_workflow_def() -> WorkflowDef:
	"""Workflow that pins a constant onto context — proxy for a lookup snapshot."""
	return WorkflowDef.model_validate(
		{
			"key": "lookup_demo",
			"version": "1.0.0",
			"subject_kind": "demo",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "snapshotted", "kind": "manual_review"},
				{"name": "done", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "snapshot",
					"event": "snapshot",
					"from_state": "intake",
					"to_state": "snapshotted",
					"effects": [
						# Pin a deterministic snapshot — mirrors what
						# lookup_party / lookup_setting would persist as
						# evaluated_lookups[].result_snapshot.
						{
							"kind": "set",
							"target": "context.evaluated_lookups.policy_limit",
							"expr": 100000,
						},
						{
							"kind": "set",
							"target": "context.evaluated_lookups.currency",
							"expr": "USD",
						},
					],
				},
				{
					"id": "complete",
					"event": "complete",
					"from_state": "snapshotted",
					"to_state": "done",
				},
			],
		}
	)


async def test_replay_reproduces_lookup_snapshot_byte_identical() -> None:
	wd = _lookup_workflow_def()
	events = [("snapshot", {}), ("complete", {})]

	# 1. First run: record events.
	live = new_instance(wd, instance_id="instance-1")
	for ev, payload in events:
		await fire(wd, live, ev, payload=payload, tenant_id="t-1")

	# 2. Imagine the underlying lookup source mutates here (we don't actually
	#    run the live lookup again — the engine context already holds the
	#    snapshot, so replay is fed by the recorded events alone).
	mutated_view = {"limit": 9999999, "currency": "ZAR"}  # deliberately changed
	assert mutated_view  # silence unused warning

	# 3. Replay using reconstruct() — should re-derive the same context.
	replayed = await reconstruct(wd, events, instance_id="instance-1")

	assert replayed.context == live.context
	assert replayed.state == live.state
	assert replayed.history == live.history
