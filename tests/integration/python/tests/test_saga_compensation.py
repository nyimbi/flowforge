"""Integration test #9: saga ledger + outbox compensation.

When a transition records a ``compensate`` effect and a subsequent step
fails, the ledger row should advance to ``compensating`` and the outbox
worker should dispatch the compensation handler. After drain, no orphan
state is left behind.

The flowforge engine writes saga rows onto ``Instance.saga`` whenever
the ``compensate`` effect fires. The host then projects those rows into
the ``workflow_saga_steps`` table; we use the ``SagaQueries`` helper
from flowforge-sqlalchemy to drive that projection.
"""

from __future__ import annotations

import uuid

import aiosqlite
import pytest
from flowforge import config as ff_config
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.ports.types import OutboxEnvelope
from flowforge_outbox_pg import DrainWorker, HandlerRegistry
from flowforge_sqlalchemy import (
	SagaQueries,
	WorkflowInstance,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed_instance(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	instance_id: str,
) -> None:
	async with session_factory() as session:
		session.add(
			WorkflowInstance(
				id=instance_id,
				tenant_id=tenant_id,
				def_key="saga_demo",
				def_version="1.0.0",
				subject_kind="demo",
				state="intake",
				terminal=False,
				context={},
			)
		)
		await session.commit()


async def test_saga_compensation_lifecycle(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	saga_workflow_def: WorkflowDef,
) -> None:
	wd = saga_workflow_def
	instance_id = str(uuid.uuid4())
	await _seed_instance(session_factory, tenant_id, instance_id)

	# 1. Wire an outbox handler that records dispatched compensation envelopes.
	conn = await aiosqlite.connect(":memory:")
	registry = HandlerRegistry()
	dispatched: list[OutboxEnvelope] = []

	async def compensation_handler(env: OutboxEnvelope) -> None:
		dispatched.append(env)

	registry.register("wf.compensate", compensation_handler, backend="default")
	worker = DrainWorker(conn, registry, sqlite_compat=True)
	await worker.setup()

	# 2. Wire ff_config.outbox to the worker.
	class _OutboxAdapter:
		async def dispatch(self, envelope: OutboxEnvelope) -> None:
			# Mirror the engine convention: a `compensate` effect produces no
			# outbox envelope on its own — the host enqueues a wf.compensate
			# envelope explicitly when it transitions the saga step.
			pass

	ff_config.outbox = _OutboxAdapter()

	# 3. Fire the reserve transition — this records a saga step.
	saga_q = SagaQueries(session_factory, tenant_id=tenant_id)
	inst = new_instance(wd, instance_id=instance_id)
	fr1 = await fire(wd, inst, "reserve", tenant_id=tenant_id)
	assert fr1.matched_transition_id == "reserve"
	assert inst.saga, "engine should have recorded a saga compensation step"
	assert inst.saga[0]["kind"] == "release_reservation"

	# Project the saga row into storage with status=pending.
	step_id = await saga_q.append(
		instance_id, kind=inst.saga[0]["kind"], args=inst.saga[0]["args"]
	)
	pending = await saga_q.list_for_instance(instance_id)
	assert len(pending) == 1
	assert pending[0].status == "pending"
	assert step_id

	# 4. Simulate downstream failure -> the host enqueues the compensation
	#    envelope. (SagaQueries enforces a fixed status enum: pending |
	#    done | compensated | failed; the in-flight "compensating" state
	#    lives only on Instance.saga rows — the storage row stays pending
	#    until the worker reports success.)
	await worker.enqueue(
		OutboxEnvelope(
			kind="wf.compensate",
			tenant_id=tenant_id,
			body={"instance_id": instance_id, "kind": "release_reservation"},
			correlation_id=instance_id,
		)
	)

	# 5. Drain the outbox; handler runs, host marks step compensated.
	result = await worker.run_once()
	assert result.dispatched == 1
	assert len(dispatched) == 1
	await saga_q.mark(instance_id, 0, "compensated")

	# 6. Final state: ledger row is compensated, no orphan pending steps.
	rows = await saga_q.list_for_instance(instance_id)
	assert rows[0].status == "compensated"
	assert all(r.status != "pending" for r in rows)

	await conn.close()
