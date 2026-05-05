"""Integration test #2: engine + outbox + audit in one transaction.

A workflow transition that emits a ``notify`` effect must:

* Append an ``AuditEvent`` to the audit-pg sink (with sha256 chain entry).
* Enqueue an ``OutboxEnvelope`` row into the outbox table.

After draining the outbox worker, the dispatched envelope is observed by
the registered handler, and the audit chain verifies cleanly.
"""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest
from flowforge import config as ff_config
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.ports.types import OutboxEnvelope
from flowforge_audit_pg import PgAuditSink, ff_audit_events
from flowforge_outbox_pg import DrainWorker, HandlerRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.asyncio


class _CapturingOutboxAdapter:
	"""Bridges the engine ``config.outbox`` port into the outbox-pg DrainWorker.

	The engine calls ``dispatch(envelope)`` synchronously during fire; we
	insert a row into the outbox table and let the DrainWorker handle the
	rest of the lifecycle (claim/dispatch/retry).
	"""

	def __init__(self, worker: DrainWorker) -> None:
		self._worker = worker
		self.envelopes: list[OutboxEnvelope] = []

	async def dispatch(self, envelope: OutboxEnvelope) -> None:
		self.envelopes.append(envelope)
		await self._worker.enqueue(envelope)


async def _open_outbox_conn() -> aiosqlite.Connection:
	# Default tuple row factory — DrainWorker._parse_row expects positional rows.
	conn = await aiosqlite.connect(":memory:")
	return conn


async def test_transition_writes_audit_and_drains_outbox(
	sqla_engine: AsyncEngine,
) -> None:
	# 1. Wire the audit sink into flowforge.config.
	audit = PgAuditSink(sqla_engine)
	ff_config.audit = audit

	# 2. Spin up a HandlerRegistry + DrainWorker on a separate aiosqlite conn.
	conn = await _open_outbox_conn()
	registry = HandlerRegistry()
	dispatched: list[OutboxEnvelope] = []

	async def notify_handler(env: OutboxEnvelope) -> None:
		dispatched.append(env)

	registry.register("wf.notify", notify_handler, backend="default")

	worker = DrainWorker(conn, registry, sqlite_compat=True)
	await worker.setup()

	# 3. Wire the engine's outbox port to enqueue into the worker's table.
	ff_config.outbox = _CapturingOutboxAdapter(worker)

	# 4. Define a workflow whose ``submit`` transition emits a notify effect.
	# (the engine itself records a wf.*.transitioned audit on every fire)
	wd = WorkflowDef.model_validate(
		{
			"key": "side_effects_demo",
			"version": "1.0.0",
			"subject_kind": "demo",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "submitted", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "submitted",
					"effects": [
						{"kind": "notify", "template": "wf.demo.submitted_email"},
					],
				}
			],
		}
	)

	inst = new_instance(wd)

	# 5. Fire — should write audit + enqueue outbox in the same logical tx.
	fr = await fire(wd, inst, "submit", tenant_id="t-1")
	assert fr.terminal is True
	assert any(e.kind.endswith(".transitioned") for e in fr.audit_events)
	assert any(o.kind == "wf.notify" for o in fr.outbox_envelopes)

	# 6. Audit row visible in ff_audit_events with chain populated.
	async with sqla_engine.connect() as ac:
		audit_rows = (
			await ac.execute(select(ff_audit_events).order_by(ff_audit_events.c.occurred_at.asc()))
		).fetchall()
	assert len(audit_rows) == 1  # only the engine-level transitioned event
	for r in audit_rows:
		assert r.row_sha256 is not None and len(r.row_sha256) == 64

	# 7. Drain the outbox; worker should pick up the row and dispatch it.
	result = await worker.run_once()
	assert result.dispatched == 1
	assert len(dispatched) == 1
	assert dispatched[0].kind == "wf.notify"
	assert dispatched[0].body["template"] == "wf.demo.submitted_email"

	# 8. Audit chain verifies green end-to-end.
	verdict = await audit.verify_chain()
	assert verdict.ok is True
	# The Verdict model exposes either `examined` or `checked_count`; tolerate both.
	count = getattr(verdict, "examined", None) or getattr(verdict, "checked_count", None)
	assert count == 1

	# Cleanup
	await conn.close()


async def test_failed_handler_is_retried_then_dies(sqla_engine: AsyncEngine) -> None:
	"""When a handler keeps raising, DrainWorker pushes the row to DLQ."""
	conn = await _open_outbox_conn()
	registry = HandlerRegistry()
	calls = 0

	async def flaky_handler(env: OutboxEnvelope) -> None:
		nonlocal calls
		calls += 1
		raise RuntimeError("deliberate")

	registry.register("wf.notify", flaky_handler, backend="default")
	worker = DrainWorker(
		conn,
		registry,
		sqlite_compat=True,
		max_retries=2,
		dlq_after_seconds=1_000_000,
	)
	await worker.setup()

	await worker.enqueue(
		OutboxEnvelope(kind="wf.notify", tenant_id="t", body={"x": 1})
	)

	# First two run_once calls should retry.
	r1 = await worker.run_once()
	assert r1.retried == 1
	r2 = await worker.run_once()
	assert r2.retried == 1
	# Third drain crosses max_retries -> dead.
	r3 = await worker.run_once()
	assert r3.dead == 1
	assert calls == 3
	await conn.close()
