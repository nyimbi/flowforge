"""Integration test #1: engine + storage round-trip.

Verifies that the flowforge core compiler + engine cooperates with the
``flowforge-sqlalchemy`` storage adapter:

* Compile + register a workflow def.
* Persist a workflow instance row.
* Fire transitions and have each transition produce a ``workflow_events``
  row with stable ordering (the seq column is monotonic per instance).
* Round-trip the engine ``Instance`` through ``SqlAlchemySnapshotStore``
  preserving state, history, and saga ledger.

This test exercises the contract between the engine's two-phase fire
output and the persistence schema. No HTTP layer.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import aiosqlite
import pytest
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.ports.types import OutboxEnvelope, Principal
from flowforge_audit_pg import PgAuditSink, ff_audit_events
from flowforge_audit_pg.sink import create_tables as create_audit_tables
from flowforge_outbox_pg.registry import HandlerRegistry
from flowforge_outbox_pg.worker import DrainWorker
from flowforge_sqlalchemy import (
	Base,
	OutboxMessage,
	SqlAlchemySnapshotStore,
	WorkflowDefinition,
	WorkflowDefinitionVersion,
	WorkflowEvent,
	WorkflowInstance,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio


async def _persist_def_and_instance(
	session_factory: async_sessionmaker[AsyncSession],
	wd: WorkflowDef,
	tenant_id: str,
) -> tuple[str, str]:
	"""Persist a definition + version + instance row; return (def_id, instance_id)."""
	def_id = str(uuid.uuid4())
	instance_id = str(uuid.uuid4())
	async with session_factory() as session:
		session.add(
			WorkflowDefinition(
				id=def_id,
				tenant_id=tenant_id,
				key=wd.key,
				subject_kind=wd.subject_kind,
				current_version=wd.version,
			)
		)
		session.add(
			WorkflowDefinitionVersion(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				definition_id=def_id,
				def_key=wd.key,
				version=wd.version,
				body=wd.model_dump(mode="json", exclude_none=True),
			)
		)
		session.add(
			WorkflowInstance(
				id=instance_id,
				tenant_id=tenant_id,
				def_key=wd.key,
				def_version=wd.version,
				subject_kind=wd.subject_kind,
				state=wd.initial_state,
				terminal=False,
				context={},
			)
		)
		await session.commit()
	return def_id, instance_id


async def test_compile_persist_fire_persists_state_and_events(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	claim_workflow_def: WorkflowDef,
) -> None:
	"""End-to-end: compile def, fire two events, persist via SQLAlchemy storage."""
	wd = claim_workflow_def
	_, instance_id = await _persist_def_and_instance(session_factory, wd, tenant_id)

	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	# 1. Build the engine instance and snapshot it.
	engine_inst = new_instance(wd, instance_id=instance_id)
	await store.put(engine_inst)

	# 2. Fire submit -> review.
	fr1 = await fire(wd, engine_inst, "submit", tenant_id=tenant_id)
	assert fr1.matched_transition_id == "submit"
	assert fr1.new_state == "review"

	# Persist the event log row + new snapshot in a single tx.
	async with session_factory() as session:
		session.add(
			WorkflowEvent(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				instance_id=instance_id,
				seq=1,
				event="submit",
				from_state="intake",
				to_state="review",
				transition_id=fr1.matched_transition_id,
				payload={},
			)
		)
		await session.commit()
	await store.put(engine_inst)

	# 3. Fire approve -> approved (terminal).
	fr2 = await fire(wd, engine_inst, "approve", tenant_id=tenant_id)
	assert fr2.matched_transition_id == "approve"
	assert fr2.terminal is True

	async with session_factory() as session:
		session.add(
			WorkflowEvent(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				instance_id=instance_id,
				seq=2,
				event="approve",
				from_state="review",
				to_state="approved",
				transition_id=fr2.matched_transition_id,
				payload={},
			)
		)
		await session.commit()
	await store.put(engine_inst)

	# 4. Verify both events persisted in order.
	async with session_factory() as session:
		rows = (
			await session.scalars(
				select(WorkflowEvent)
				.where(WorkflowEvent.instance_id == instance_id)
				.order_by(WorkflowEvent.seq.asc())
			)
		).all()
		assert [r.seq for r in rows] == [1, 2]
		assert [r.transition_id for r in rows] == ["submit", "approve"]
		assert [r.from_state for r in rows] == ["intake", "review"]
		assert [r.to_state for r in rows] == ["review", "approved"]

	# 5. Reload the snapshot and assert state matches.
	loaded = await store.get(instance_id)
	assert loaded is not None
	assert loaded.state == "approved"
	assert loaded.context.get("submitted") is True
	assert len(loaded.history) == 2


async def test_persisted_events_are_chained_by_monotonic_seq(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	claim_workflow_def: WorkflowDef,
) -> None:
	"""Persisted ``workflow_events`` rows must come out in fire order."""
	wd = claim_workflow_def
	_, instance_id = await _persist_def_and_instance(session_factory, wd, tenant_id)

	engine_inst = new_instance(wd, instance_id=instance_id)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	await store.put(engine_inst)

	fired = []
	for seq, event in enumerate(["submit", "approve"], start=1):
		fr = await fire(wd, engine_inst, event, tenant_id=tenant_id)
		fired.append((seq, event, fr.new_state))
		async with session_factory() as session:
			session.add(
				WorkflowEvent(
					id=str(uuid.uuid4()),
					tenant_id=tenant_id,
					instance_id=instance_id,
					seq=seq,
					event=event,
					to_state=fr.new_state,
					transition_id=fr.matched_transition_id,
				)
			)
			await session.commit()

	# Read with ascending seq and zip back; values must be byte-identical.
	async with session_factory() as session:
		rows = (
			await session.scalars(
				select(WorkflowEvent)
				.where(WorkflowEvent.instance_id == instance_id)
				.order_by(WorkflowEvent.seq.asc())
			)
		).all()
		read = [(r.seq, r.event, r.to_state) for r in rows]

	assert read == fired


async def test_sqlalchemy_fire_and_commit_persists_audit_snapshot_event_and_outbox(
	session_factory: async_sessionmaker[AsyncSession],
	sqla_engine: AsyncEngine,
	tenant_id: str,
	claim_workflow_def: WorkflowDef,
) -> None:
	wd = claim_workflow_def
	_, instance_id = await _persist_def_and_instance(session_factory, wd, tenant_id)
	store = SqlAlchemySnapshotStore(
		session_factory,
		tenant_id=tenant_id,
		audit_sink=PgAuditSink(sqla_engine),
	)
	engine_inst = new_instance(wd, instance_id=instance_id)
	await store.put(engine_inst)

	await store.fire_and_commit(
		wd=wd,
		instance=engine_inst,
		event="submit",
		principal=Principal(user_id="u-1"),
	)
	result = await store.fire_and_commit(
		wd=wd,
		instance=engine_inst,
		event="approve",
		principal=Principal(user_id="u-1"),
	)

	assert result.terminal is True
	assert engine_inst.state == "approved"

	async with session_factory() as session:
		events = (
			await session.scalars(
				select(WorkflowEvent)
				.where(
					WorkflowEvent.tenant_id == tenant_id,
					WorkflowEvent.instance_id == instance_id,
				)
				.order_by(WorkflowEvent.seq.asc())
			)
		).all()
		assert [(row.seq, row.event, row.transition_id) for row in events] == [
			(1, "submit", "submit"),
			(2, "approve", "approve"),
		]

		outbox_rows = (
			await session.scalars(
				select(OutboxMessage).where(
					OutboxMessage.tenant_id == tenant_id,
					OutboxMessage.status == "pending",
				)
			)
		).all()
		assert [row.kind for row in outbox_rows] == ["wf.notify"]
		assert outbox_rows[0].body["template"] == "claim.approved.email"

		audit_count = await session.scalar(select(func.count()).select_from(ff_audit_events))
		assert audit_count is not None
		assert audit_count >= 4

	loaded = await store.get(instance_id)
	assert loaded is not None
	assert loaded.state == "approved"
	assert len(loaded.history) == 2


async def test_sqlalchemy_fire_and_commit_outbox_rows_are_drain_worker_compatible(
	tmp_path: Path,
	tenant_id: str,
	claim_workflow_def: WorkflowDef,
) -> None:
	"""Rows produced by the transactional fire path must drain through the worker."""
	db_path = tmp_path / "flowforge-outbox.sqlite3"
	engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
		await create_audit_tables(conn)
	session_factory = async_sessionmaker(engine, expire_on_commit=False)

	try:
		wd = claim_workflow_def
		_, instance_id = await _persist_def_and_instance(session_factory, wd, tenant_id)
		store = SqlAlchemySnapshotStore(
			session_factory,
			tenant_id=tenant_id,
			audit_sink=PgAuditSink(engine),
		)
		engine_inst = new_instance(wd, instance_id=instance_id)
		await store.put(engine_inst)
		await store.fire_and_commit(
			wd=wd,
			instance=engine_inst,
			event="submit",
			principal=Principal(user_id="u-1"),
		)
		await store.fire_and_commit(
			wd=wd,
			instance=engine_inst,
			event="approve",
			principal=Principal(user_id="u-1"),
		)

		received: list[OutboxEnvelope] = []
		registry = HandlerRegistry()

		async def _record(envelope: OutboxEnvelope) -> None:
			received.append(envelope)

		registry.register("wf.notify", _record)
		async with aiosqlite.connect(db_path) as conn:
			worker = DrainWorker(conn, registry, sqlite_compat=True)
			result = await worker.run_once()

		assert result.dispatched == 1
		assert result.retried == 0
		assert result.dead == 0
		assert result.no_handler == 0
		assert len(received) == 1
		envelope = received[0]
		assert envelope.kind == "wf.notify"
		assert envelope.tenant_id == tenant_id
		assert envelope.body["template"] == "claim.approved.email"

		async with session_factory() as session:
			status = await session.scalar(
				select(OutboxMessage.status).where(
					OutboxMessage.tenant_id == tenant_id,
					OutboxMessage.kind == "wf.notify",
				)
			)
			assert status == "dispatched"
	finally:
		await engine.dispose()


async def test_sqlalchemy_fire_and_commit_rolls_back_everything_on_audit_failure(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	claim_workflow_def: WorkflowDef,
) -> None:
	class _FailingTransactionalAudit:
		async def record_in_connection(
			self,
			conn: AsyncConnection,
			event: object,
		) -> str:
			raise RuntimeError("audit unavailable")

	wd = claim_workflow_def
	_, instance_id = await _persist_def_and_instance(session_factory, wd, tenant_id)
	store = SqlAlchemySnapshotStore(
		session_factory,
		tenant_id=tenant_id,
		audit_sink=_FailingTransactionalAudit(),
	)
	engine_inst = new_instance(wd, instance_id=instance_id)
	await store.put(engine_inst)

	with pytest.raises(RuntimeError, match="audit unavailable"):
		await store.fire_and_commit(
			wd=wd,
			instance=engine_inst,
			event="submit",
			principal=Principal(user_id="u-1"),
		)

	assert engine_inst.state == "intake"
	assert engine_inst.history == []

	async with session_factory() as session:
		event_count = await session.scalar(
			select(func.count())
			.select_from(WorkflowEvent)
			.where(WorkflowEvent.instance_id == instance_id)
		)
		outbox_count = await session.scalar(
			select(func.count())
			.select_from(OutboxMessage)
			.where(OutboxMessage.tenant_id == tenant_id)
		)
		assert event_count == 0
		assert outbox_count == 0

	loaded = await store.get(instance_id)
	assert loaded is not None
	assert loaded.state == "intake"
	assert loaded.history == []
