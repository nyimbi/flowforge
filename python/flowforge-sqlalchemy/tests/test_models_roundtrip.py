"""Models compile + round-trip on async SQLite."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from flowforge.engine.fire import Instance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flowforge_sqlalchemy import (
	BusinessCalendar,
	PendingSignal,
	SagaQueries,
	SqlAlchemySnapshotStore,
	WorkflowDefinition,
	WorkflowDefinitionVersion,
	WorkflowEvent,
	WorkflowInstance,
	WorkflowInstanceQuarantine,
	WorkflowInstanceToken,
)

pytestmark = pytest.mark.asyncio


async def _seed_instance(
	sf: async_sessionmaker[AsyncSession], tenant_id: str
) -> WorkflowInstance:
	inst = WorkflowInstance(
		id=str(uuid.uuid4()),
		tenant_id=tenant_id,
		def_key="claim_intake",
		def_version="1.0.0",
		subject_kind="claim",
		state="intake",
		terminal=False,
		context={"intake": {"policy_id": "p-1"}},
	)
	async with sf() as session:
		session.add(inst)
		await session.commit()
		await session.refresh(inst)
	return inst


async def test_definition_roundtrip(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	def_id = str(uuid.uuid4())
	async with session_factory() as session:
		session.add(
			WorkflowDefinition(
				id=def_id,
				tenant_id=tenant_id,
				key="claim_intake",
				subject_kind="claim",
				current_version="1.0.0",
			)
		)
		session.add(
			WorkflowDefinitionVersion(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				definition_id=def_id,
				def_key="claim_intake",
				version="1.0.0",
				body={"states": [{"name": "intake"}]},
			)
		)
		await session.commit()

	async with session_factory() as session:
		row = await session.scalar(
			select(WorkflowDefinition).where(WorkflowDefinition.id == def_id)
		)
		assert row is not None
		assert row.key == "claim_intake"
		assert row.current_version == "1.0.0"
		assert isinstance(row.created_at, datetime)

		version_rows = (
			await session.scalars(
				select(WorkflowDefinitionVersion).where(
					WorkflowDefinitionVersion.definition_id == def_id
				)
			)
		).all()
		assert len(version_rows) == 1
		assert version_rows[0].body["states"][0]["name"] == "intake"


async def test_instance_event_token_quarantine_roundtrip(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst = await _seed_instance(session_factory, tenant_id)

	async with session_factory() as session:
		session.add(
			WorkflowEvent(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				instance_id=inst.id,
				seq=1,
				event="submit",
				from_state="intake",
				to_state="triage",
				transition_id="submit",
				payload={"foo": "bar"},
			)
		)
		session.add(
			WorkflowInstanceToken(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				instance_id=inst.id,
				region="parallel-region-A",
				state="branch_a",
				context={},
			)
		)
		session.add(
			WorkflowInstanceQuarantine(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				instance_id=inst.id,
				reason="guard_raised",
				details={"trace": "snippet"},
				quarantined_by="ops-1",
				quarantined_at=datetime.now(timezone.utc),
			)
		)
		await session.commit()

	async with session_factory() as session:
		events = (
			await session.scalars(
				select(WorkflowEvent).where(WorkflowEvent.instance_id == inst.id)
			)
		).all()
		assert len(events) == 1
		assert events[0].event == "submit"
		assert events[0].payload == {"foo": "bar"}

		tokens = (
			await session.scalars(
				select(WorkflowInstanceToken).where(
					WorkflowInstanceToken.instance_id == inst.id
				)
			)
		).all()
		assert len(tokens) == 1
		assert tokens[0].region == "parallel-region-A"

		quarantine = await session.scalar(
			select(WorkflowInstanceQuarantine).where(
				WorkflowInstanceQuarantine.instance_id == inst.id
			)
		)
		assert quarantine is not None
		assert quarantine.reason == "guard_raised"


async def test_business_calendar_and_pending_signal_roundtrip(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	async with session_factory() as session:
		session.add(
			BusinessCalendar(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				calendar_key="ke-default",
				timezone="Africa/Nairobi",
				working_hours={"mon": [{"start": "09:00", "end": "17:00"}]},
				holidays=["2026-01-01"],
			)
		)
		session.add(
			PendingSignal(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				name="payment_received",
				correlation_key="claim-7",
				payload={"amount": 250},
			)
		)
		await session.commit()

	async with session_factory() as session:
		cal = await session.scalar(
			select(BusinessCalendar).where(BusinessCalendar.calendar_key == "ke-default")
		)
		assert cal is not None
		assert cal.timezone == "Africa/Nairobi"
		assert cal.holidays == ["2026-01-01"]

		sig = await session.scalar(
			select(PendingSignal).where(PendingSignal.correlation_key == "claim-7")
		)
		assert sig is not None
		assert sig.payload == {"amount": 250}
		assert sig.consumed is False


async def test_snapshot_store_roundtrips_state(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)

	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	# initial fetch -> None
	assert await store.get(inst_row.id) is None

	engine_inst = Instance(
		id=inst_row.id,
		def_key="claim_intake",
		def_version="1.0.0",
		state="triage",
		context={"triage": {"priority": "high"}},
		created_entities=[("claim", {"id": "c-1", "policy_id": "p-1"})],
		saga=[{"kind": "release_lock", "args": {}}],
		history=["intake-(submit:submit)->triage"],
	)
	await store.put(engine_inst)
	loaded = await store.get(inst_row.id)
	assert loaded is not None
	assert loaded.state == "triage"
	assert loaded.context == {"triage": {"priority": "high"}}
	assert loaded.created_entities == [("claim", {"id": "c-1", "policy_id": "p-1"})]
	assert loaded.saga == [{"kind": "release_lock", "args": {}}]
	assert loaded.history == ["intake-(submit:submit)->triage"]

	# overwrite path
	engine_inst.state = "approved"
	engine_inst.history.append("triage-(approve:approve)->approved")
	await store.put(engine_inst)
	loaded2 = await store.get(inst_row.id)
	assert loaded2 is not None
	assert loaded2.state == "approved"
	assert len(loaded2.history) == 2


async def test_saga_queries_append_list_mark(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst = await _seed_instance(session_factory, tenant_id)

	q = SagaQueries(session_factory, tenant_id=tenant_id)
	id_a = await q.append(inst.id, kind="release_lock", args={"k": "a"})
	id_b = await q.append(inst.id, kind="refund", args={"k": "b"})
	assert id_a != id_b

	rows = await q.list_for_instance(inst.id)
	assert [r.idx for r in rows] == [0, 1]
	assert [r.kind for r in rows] == ["release_lock", "refund"]
	assert all(r.status == "pending" for r in rows)

	pending = await q.list_pending_for_compensation(inst.id)
	assert [r.idx for r in pending] == [1, 0]  # LIFO

	hit = await q.mark(inst.id, 1, "compensated")
	assert hit is True
	miss = await q.mark(inst.id, 99, "compensated")
	assert miss is False

	rows_after = await q.list_for_instance(inst.id)
	assert rows_after[1].status == "compensated"
	assert rows_after[0].status == "pending"
