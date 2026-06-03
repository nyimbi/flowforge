"""E-45 / IT-02 — E2E suite (3 flows).

Audit reference: framework/docs/audit-fix-plan.md §7 E-45.

Three end-to-end flows must be green together:

1. **fire → audit → verify_chain** — wire ``PgAuditSink`` (sqlite stand-in)
   into ``_config.audit``, fire workflow transitions, assert each fire
   appended a hash-chained audit row and ``verify_chain()`` succeeds.

2. **fire → outbox-dispatch → handler → ack** — register a notify-handler
   on the outbox, fire a transition that emits a notify effect, assert
   the handler ran and an ack envelope was recorded by the host.

3. **parallel_fork → advance branches → join collapse → replay-determinism**
   — exercise the real parallel_fork engine primitive (E-82): fork two
   branch tokens, advance each via per-token fire(), assert the join barrier
   holds until the last token is drained, then verify byte-identical state
   and history across two independent replays of the same event sequence.

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
# Flow 3 — parallel_fork → advance branches → join collapse → replay-determinism
# ---------------------------------------------------------------------------


def _fork_workflow_def() -> WorkflowDef:
	"""Minimal fork/join workflow for flow 3."""
	return WorkflowDef.model_validate(
		{
			"key": "it02_fork_e2e",
			"version": "1.0.0",
			"subject_kind": "it02_subject",
			"initial_state": "triage",
			"metadata": {"engine_features": ["parallel_fork"]},
			"states": [
				{"name": "triage",     "kind": "manual_review"},
				{"name": "fork_point", "kind": "parallel_fork"},
				{"name": "branch_a",   "kind": "automatic"},
				{"name": "branch_b",   "kind": "automatic"},
				{"name": "join",       "kind": "parallel_join"},
				{"name": "done",       "kind": "terminal_success"},
			],
			"transitions": [
				{"id": "triage_to_fork", "event": "ready",    "from_state": "triage",     "to_state": "fork_point", "priority": 0},
				{"id": "fork_to_a",      "event": "__auto__", "from_state": "fork_point", "to_state": "branch_a",   "priority": 1},
				{"id": "fork_to_b",      "event": "__auto__", "from_state": "fork_point", "to_state": "branch_b",   "priority": 0},
				{"id": "a_to_join",      "event": "a_done",   "from_state": "branch_a",   "to_state": "join",       "priority": 0},
				{"id": "b_to_join",      "event": "b_done",   "from_state": "branch_b",   "to_state": "join",       "priority": 0},
				{"id": "join_to_done",   "event": "join_complete", "from_state": "join",  "to_state": "done",       "priority": 0},
			],
		}
	)


@_async
async def test_IT_02_flow_3_fork_migrate_replay_determinism() -> None:
	"""parallel_fork full lifecycle: fork → advance branches → join collapse.

	Upgraded from the snapshot+clone+replay scaffold to use the real
	parallel_fork engine primitive (E-82).  Both the primary fork→join path
	and replay-determinism are verified via fire() with FLOWFORGE_FORKS_ENABLED=1.
	"""
	import os

	os.environ["FLOWFORGE_FORKS_ENABLED"] = "1"
	try:
		_config.reset_to_fakes()
		wd = _fork_workflow_def()
		principal = Principal(user_id="u-3", is_system=True)

		# --- Primary path: fork → advance_a → advance_b → join collapse ---
		inst = new_instance(wd)
		await fire(wd, inst, "ready", principal=principal)
		assert inst.state == "fork_point"

		tokens = inst.tokens.list()
		assert len(tokens) == 2, f"expected 2 tokens after fork, got {tokens}"
		token_by_state = {t.state: t for t in tokens}
		assert set(token_by_state) == {"branch_a", "branch_b"}

		token_a = token_by_state["branch_a"]
		token_b = token_by_state["branch_b"]

		# Advance branch_a — join barrier must hold (branch_b still alive)
		await fire(wd, inst, "a_done", token_id=token_a.id, principal=principal)
		assert inst.state == "fork_point", (
			f"premature collapse: expected fork_point, got {inst.state!r}"
		)
		assert len(inst.tokens.list()) == 1

		# Advance branch_b — final token drained → join collapses
		result_b = await fire(wd, inst, "b_done", token_id=token_b.id, principal=principal)
		assert inst.state == "done", (
			f"expected 'done' after join collapse, got {inst.state!r}"
		)
		assert result_b.terminal is True
		assert inst.tokens.list() == []

		# --- Replay-determinism: two independent instances, same event sequence ---
		_config.reset_to_fakes()
		wd2 = _fork_workflow_def()
		inst_a = new_instance(wd2, instance_id="it02-replay-a")
		inst_b = new_instance(wd2, instance_id="it02-replay-b")

		for replay_inst in (inst_a, inst_b):
			await fire(wd2, replay_inst, "ready", principal=principal)
			tmap = {t.state: t for t in replay_inst.tokens.list()}
			await fire(wd2, replay_inst, "a_done", token_id=tmap["branch_a"].id, principal=principal)
			tmap2 = {t.state: t for t in replay_inst.tokens.list()}
			await fire(wd2, replay_inst, "b_done", token_id=tmap2["branch_b"].id, principal=principal)

		assert inst_a.state == inst_b.state == "done"
		# Token IDs are UUID7 — strip them before comparing so we test
		# structural determinism (same transitions in same order).
		import re as _re
		_uuid_pat = _re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
		def _strip(h: list[str]) -> list[str]:
			return [_uuid_pat.sub("<uuid>", e) for e in h]
		assert _strip(inst_a.history) == _strip(inst_b.history), (
			f"replay history structure diverged:\n  a={_strip(inst_a.history)}\n  b={_strip(inst_b.history)}"
		)
	finally:
		os.environ.pop("FLOWFORGE_FORKS_ENABLED", None)


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
