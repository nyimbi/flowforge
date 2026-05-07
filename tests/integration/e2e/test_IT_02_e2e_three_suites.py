"""E-45 / IT-02 — E2E suite (3 flows).

Audit reference: framework/docs/audit-fix-plan.md §7 E-45.

Three end-to-end flows must be green together:

1. **fire → audit → verify_chain** — wire ``PgAuditSink`` (sqlite stand-in)
   into ``_config.audit``, fire workflow transitions, assert each fire
   appended a hash-chained audit row and ``verify_chain()`` succeeds.

2. **fire → outbox-dispatch → handler → ack** — register a notify-handler
   on the outbox, fire a transition that emits a notify effect, assert
   the handler ran and an ack envelope was recorded by the host.

3. **fork → migrate → replay-determinism** — snapshot an instance, run
   the same event sequence on the original and a restored snapshot,
   assert byte-identical resulting state and history. (Replay
   determinism in the absence of a real workflow-fork primitive.)

Per plan §5.2 the production variant runs against ``pytest-postgresql`` /
``testcontainers``; in CI we use the sqlite+aiosqlite stand-in, which
exercises the same Python code paths (``PgAuditSink``, fire two-phase
commit, outbox dispatch, snapshot-store).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from flowforge import config as _config
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.engine.snapshots import InMemorySnapshotStore, _shallow_clone
from flowforge.ports.types import OutboxEnvelope, Principal
from flowforge.testing.port_fakes import InMemoryAuditSink, InMemoryOutbox
from flowforge_audit_pg import PgAuditSink, create_tables


_async = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Workflow definition shared by all three flows.
# ---------------------------------------------------------------------------


def _claim_intake_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake_e2e",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "triage", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "triage",
					"effects": [{"kind": "notify", "template": "claim.submitted"}],
				},
				{
					"id": "approve",
					"event": "approve",
					"from_state": "triage",
					"to_state": "approved",
					"effects": [{"kind": "notify", "template": "claim.approved"}],
				},
			],
		}
	)


# ---------------------------------------------------------------------------
# Flow 1 — fire → audit → verify_chain
# ---------------------------------------------------------------------------


@_async
async def test_IT_02_flow_1_fire_audit_verify_chain() -> None:
	"""Each fire writes a hash-chained audit row; verify_chain stays green."""
	tmp = tempfile.NamedTemporaryFile(prefix="e2e_flow1_", suffix=".db", delete=False)
	tmp.close()
	engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
	try:
		async with engine.begin() as conn:
			await create_tables(conn)
		audit_sink = PgAuditSink(engine)

		_config.reset_to_fakes()
		_config.audit = audit_sink

		wd = _claim_intake_def()
		inst = new_instance(
			wd, initial_context={"intake": {"policy_id": "p-1", "tenant_id": "t-1"}}
		)
		principal = Principal(user_id="u-1", is_system=True)

		# Fire two transitions; engine.fire calls _config.audit.record(...) for
		# every emitted AuditEvent during phase-2 commit, so the chained sink
		# already holds the rows when fire returns.
		await fire(wd, inst, "submit", principal=principal)
		await fire(wd, inst, "approve", principal=principal)

		# Hash chain verifies clean.
		verdict = await audit_sink.verify_chain()
		assert verdict.ok is True, (
			f"chain broke after e2e: bad_id={verdict.first_bad_event_id}"
		)
		assert verdict.checked_count >= 2

		# Final state matches the DSL.
		assert inst.state == "approved"
	finally:
		await engine.dispose()
		Path(tmp.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Flow 2 — fire → outbox-dispatch → handler → ack
# ---------------------------------------------------------------------------


@_async
async def test_IT_02_flow_2_fire_outbox_handler_ack() -> None:
	"""A registered notify handler runs and emits an ack envelope."""
	acks: list[OutboxEnvelope] = []

	class _AckingOutbox(InMemoryOutbox):
		"""Records every dispatched envelope; a registered handler emits a follow-up ack."""

	outbox = _AckingOutbox()

	# The engine emits ``OutboxEnvelope(kind="wf.notify", body={...,
	# template: "claim.submitted"})`` for each ``notify`` effect; we register
	# a handler on that kind which captures + emits an ack envelope. In
	# production this would be a separate subscriber on a topic.
	async def _notify_handler(envelope: OutboxEnvelope) -> None:
		body = getattr(envelope, "body", {}) or {}
		ack = OutboxEnvelope(
			kind=f"{body.get('template', 'wf.notify')}.ack",
			tenant_id=envelope.tenant_id,
			body={
				"original_kind": envelope.kind,
				"original_template": body.get("template"),
				"correlation_id": getattr(envelope, "correlation_id", None),
			},
		)
		acks.append(ack)

	outbox.register("wf.notify", _notify_handler)

	_config.reset_to_fakes()
	_config.outbox = outbox
	audit = InMemoryAuditSink()
	_config.audit = audit

	wd = _claim_intake_def()
	inst = new_instance(
		wd, initial_context={"intake": {"policy_id": "p-2", "tenant_id": "t-2"}}
	)
	r = await fire(wd, inst, "submit", principal=Principal(user_id="u-2", is_system=True))

	# fire emitted a wf.notify envelope, which dispatch() routed to the
	# registered handler, which captured an ack.
	notify_envs = [env for env in outbox.dispatched if env.kind == "wf.notify"]
	assert notify_envs, (
		f"outbox dispatcher did not see a wf.notify envelope; saw {[e.kind for e in outbox.dispatched]!r}"
	)
	# The submit transition's notify carried template="claim.submitted".
	templates = [(getattr(e, "body", {}) or {}).get("template") for e in notify_envs]
	assert "claim.submitted" in templates, (
		f"wf.notify envelopes missing claim.submitted template; got {templates}"
	)
	assert len(acks) == 1, f"handler did not ack exactly once: {len(acks)}"
	assert acks[0].kind == "claim.submitted.ack"
	assert acks[0].body["original_template"] == "claim.submitted"
	# The audit sink saw the underlying state-transition event.
	assert any(
		ev.kind.startswith("wf.claim_intake_e2e") for ev in audit.events
	), f"audit log missing transition event: {[e.kind for e in audit.events]}"
	# Final state matches.
	assert inst.state == "triage"
	assert r.matched_transition_id == "submit"


# ---------------------------------------------------------------------------
# Flow 3 — fork → migrate → replay-determinism
# ---------------------------------------------------------------------------


@_async
async def test_IT_02_flow_3_fork_migrate_replay_determinism() -> None:
	"""Two replays of the same event sequence on equal initial snapshots converge."""
	store = InMemorySnapshotStore()
	_config.reset_to_fakes()

	wd = _claim_intake_def()
	inst_a = new_instance(
		wd, initial_context={"intake": {"policy_id": "p-3", "tenant_id": "t-3"}}
	)
	# Snapshot the initial state — this is the "fork" point.
	await store.put(inst_a)
	# Restore a clone — semantic of "fork+migrate to a new instance node":
	# the migration is a no-op DSL bump in this scaffold, but the replay
	# determinism property must hold even before any real DSL diff.
	restored = await store.get(inst_a.id)
	assert restored is not None
	inst_b = _shallow_clone(restored)
	# Give B a distinct id so the snapshot store can hold both.
	inst_b.id = f"{inst_a.id}-fork"
	# Sanity: clones start equal.
	assert inst_a.state == inst_b.state
	assert inst_a.context == inst_b.context

	principal = Principal(user_id="u-3", is_system=True)

	# Replay the same event sequence on both branches.
	for event in ("submit", "approve"):
		await fire(wd, inst_a, event, principal=principal)
		await fire(wd, inst_b, event, principal=principal)

	# Replay-determinism: byte-identical state + context + history.
	assert inst_a.state == inst_b.state == "approved"
	assert inst_a.context == inst_b.context
	assert inst_a.history == inst_b.history

	# Save the post-replay snapshot — proving the snapshot store round-trips
	# Instance shape unchanged across the fork.
	await store.put(inst_a)
	round_tripped = await store.get(inst_a.id)
	assert round_tripped is not None
	assert round_tripped.state == inst_a.state
	assert round_tripped.context == inst_a.context


# ---------------------------------------------------------------------------
# Coverage gate — 3 flows present
# ---------------------------------------------------------------------------


def test_IT_02_three_flows_present() -> None:
	"""Single-pane gate that all three E2E flows are declared."""
	import sys

	module_tests = [
		name
		for name in dir(sys.modules[__name__])
		if name.startswith("test_IT_02_flow_")
	]
	flows = sorted({name.split("_")[4] for name in module_tests})
	assert flows == ["1", "2", "3"], (
		f"audit-2026 IT-02 requires 3 e2e flows; got {flows}"
	)
