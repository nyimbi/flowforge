"""Models compile + round-trip on async SQLite."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import cast

import pytest
from flowforge.dsl import WorkflowDef
from flowforge.engine import new_instance
from flowforge.engine.fire import FireResult, Instance
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flowforge_sqlalchemy import (
	BusinessCalendar,
	OutboxMessage,
	PendingSignal,
	SagaConflict,
	SagaQueries,
	SagaTenantMismatch,
	SnapshotConflict,
	SnapshotTenantMismatch,
	SqlAlchemySnapshotStore,
	WorkflowDefinition,
	WorkflowDefinitionVersion,
	WorkflowEvent,
	WorkflowInstance,
	WorkflowInstanceQuarantine,
	WorkflowInstanceSnapshot,
	WorkflowInstanceToken,
	WorkflowSagaStep,
)
from flowforge_sqlalchemy.snapshot_store import (
	_instance_from_body,
	_is_terminal_state,
	_transition_payload,
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


def _workflow_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "approve",
					"event": "approve",
					"from_state": "intake",
					"to_state": "approved",
					"priority": 0,
				}
			],
		}
	)


def _workflow_with_effects() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "review", "kind": "manual_review"},
				{"name": "rejected", "kind": "terminal_fail"},
				{"name": "approved", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "review",
					"priority": 0,
					"effects": [
						{"kind": "set", "target": "context.submitted", "expr": True},
						{"kind": "audit", "template": "wf.claim.submitted"},
					],
				},
				{
					"id": "reject",
					"event": "reject",
					"from_state": "intake",
					"to_state": "rejected",
					"priority": 0,
				},
				{
					"id": "approve",
					"event": "approve",
					"from_state": "review",
					"to_state": "approved",
					"priority": 0,
					"effects": [
						{"kind": "audit", "template": "wf.claim.approved"},
						{"kind": "notify", "template": "claim.approved.email"},
					],
				},
			],
		}
	)


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


async def test_snapshot_store_create_instance_seeds_runtime_rows(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_def()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	loaded = await store.get_for_tenant(instance.id, tenant_id=tenant_id)
	assert loaded is not None
	assert loaded.state == "intake"
	assert loaded.history == []
	assert await store.get_for_tenant(instance.id, tenant_id="other-tenant") is None

	async with session_factory() as session:
		row = await session.scalar(
			select(WorkflowInstance).where(
				WorkflowInstance.tenant_id == tenant_id,
				WorkflowInstance.id == instance.id,
			)
		)
		assert row is not None
		assert row.def_key == wd.key
		assert row.def_version == wd.version
		assert row.subject_kind == wd.subject_kind
		assert row.terminal is False


async def test_snapshot_store_create_instance_rejects_wrong_tenant(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_def()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	with pytest.raises(SnapshotTenantMismatch):
		await store.create_instance(
			instance,
			workflow_def=wd,
			tenant_id="other-tenant",
		)


async def test_snapshot_store_create_instance_duplicate_surfaces_conflict(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_def()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)
	with pytest.raises(SnapshotConflict) as excinfo:
		await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)
	assert excinfo.value.actual_seq == 0


async def test_snapshot_store_filters_reads_by_tenant(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	other_store = SqlAlchemySnapshotStore(session_factory, tenant_id="other-tenant")

	engine_inst = Instance(
		id=inst_row.id,
		def_key="claim_intake",
		def_version="1.0.0",
		state="triage",
		context={},
		created_entities=[],
		saga=[],
		history=["intake-(submit:submit)->triage"],
	)
	await store.put(engine_inst)

	assert await store.get(inst_row.id) is not None
	assert await other_store.get(inst_row.id) is None


async def test_snapshot_store_cross_tenant_put_does_not_overwrite(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	other_store = SqlAlchemySnapshotStore(session_factory, tenant_id="other-tenant")

	engine_inst = Instance(
		id=inst_row.id,
		def_key="claim_intake",
		def_version="1.0.0",
		state="triage",
		context={},
		created_entities=[],
		saga=[],
		history=["intake-(submit:submit)->triage"],
	)
	await store.put(engine_inst)
	with pytest.raises(SnapshotTenantMismatch):
		await other_store.put(
			Instance(
				id=inst_row.id,
				def_key="claim_intake",
				def_version="1.0.0",
				state="hijacked",
				context={},
				created_entities=[],
				saga=[],
				history=["bad"],
			)
		)

	loaded = await store.get(inst_row.id)
	assert loaded is not None
	assert loaded.state == "triage"

	# overwrite path
	engine_inst.state = "approved"
	engine_inst.history.append("triage-(approve:approve)->approved")
	await store.put(engine_inst)
	loaded2 = await store.get(inst_row.id)
	assert loaded2 is not None
	assert loaded2.state == "approved"
	assert len(loaded2.history) == 2


async def test_snapshot_store_compare_and_put_rejects_stale_seq(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	engine_inst = Instance(
		id=inst_row.id,
		def_key="claim_intake",
		def_version="1.0.0",
		state="intake",
		context={},
		created_entities=[],
		saga=[],
		history=[],
	)
	await store.compare_and_put(engine_inst, expected_seq=0)

	engine_inst.state = "triage"
	engine_inst.history.append("intake-(submit:submit)->triage")
	await store.compare_and_put(engine_inst, expected_seq=0)

	stale = Instance(
		id=inst_row.id,
		def_key="claim_intake",
		def_version="1.0.0",
		state="approved",
		context={},
		created_entities=[],
		saga=[],
		history=["intake-(submit:submit)->triage", "triage-(approve:approve)->approved"],
	)
	with pytest.raises(SnapshotConflict) as excinfo:
		await store.compare_and_put(stale, expected_seq=0)
	assert excinfo.value.actual_seq == 1

	loaded = await store.get(inst_row.id)
	assert loaded is not None
	assert loaded.state == "triage"
	assert len(loaded.history) == 1


async def test_snapshot_store_compare_and_put_accepts_current_seq(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	engine_inst = Instance(
		id=inst_row.id,
		def_key="claim_intake",
		def_version="1.0.0",
		state="intake",
		context={},
		created_entities=[],
		saga=[],
		history=[],
	)
	await store.compare_and_put(engine_inst, expected_seq=0)

	engine_inst.state = "triage"
	engine_inst.history.append("intake-(submit:submit)->triage")
	await store.compare_and_put(engine_inst, expected_seq=0)

	engine_inst.state = "approved"
	engine_inst.history.append("triage-(approve:approve)->approved")
	await store.compare_and_put(engine_inst, expected_seq=1)

	loaded = await store.get(inst_row.id)
	assert loaded is not None
	assert loaded.state == "approved"
	assert len(loaded.history) == 2


async def test_snapshot_store_compare_and_put_rejects_wrong_tenant(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)
	other_store = SqlAlchemySnapshotStore(session_factory, tenant_id="other-tenant")

	with pytest.raises(SnapshotTenantMismatch):
		await other_store.compare_and_put(
			Instance(
				id=inst_row.id,
				def_key="claim_intake",
				def_version="1.0.0",
				state="intake",
				context={},
				created_entities=[],
				saga=[],
				history=[],
			),
			expected_seq=0,
		)


async def test_snapshot_store_compare_and_put_rejects_negative_seq(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst_row = await _seed_instance(session_factory, tenant_id)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)

	with pytest.raises(AssertionError, match="expected_seq"):
		await store.compare_and_put(
			Instance(
				id=inst_row.id,
				def_key="claim_intake",
				def_version="1.0.0",
				state="intake",
				context={},
				created_entities=[],
				saga=[],
				history=[],
			),
			expected_seq=-1,
		)


async def test_snapshot_store_compare_and_put_insert_race_surfaces_conflict(
	tenant_id: str,
) -> None:
	class Result:
		rowcount = 0

	class FakeSession:
		def __init__(self) -> None:
			self.scalar_calls = 0
			self.rolled_back = False

		async def __aenter__(self) -> "FakeSession":
			return self

		async def __aexit__(
			self,
			exc_type: object,
			exc: object,
			tb: object,
		) -> None:
			return None

		async def scalar(self, _stmt: object) -> str | int | None:
			self.scalar_calls += 1
			if self.scalar_calls == 1:
				return "owned-instance"
			if self.scalar_calls == 2:
				return None
			return 7

		async def execute(self, _stmt: object) -> Result:
			return Result()

		def add(self, row: object) -> None:
			assert isinstance(row, WorkflowInstanceSnapshot)
			assert row.seq == 0

		async def commit(self) -> None:
			raise IntegrityError("insert", {}, RuntimeError("duplicate snapshot"))

		async def rollback(self) -> None:
			self.rolled_back = True

	session = FakeSession()

	class FakeSessionFactory:
		def __call__(self) -> FakeSession:
			return session

	store = SqlAlchemySnapshotStore(
		cast(async_sessionmaker[AsyncSession], FakeSessionFactory()),
		tenant_id=tenant_id,
	)

	with pytest.raises(SnapshotConflict) as excinfo:
		await store.compare_and_put(
			Instance(
				id="inst-1",
				def_key="claim_intake",
				def_version="1.0.0",
				state="intake",
				context={},
				created_entities=[],
				saga=[],
				history=[],
			),
			expected_seq=0,
		)
	assert excinfo.value.actual_seq == 7
	assert session.rolled_back is True


async def test_snapshot_store_fire_and_commit_writes_durable_side_effects(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	audit_events: list[object] = []

	class AuditSink:
		async def record_in_connection(self, conn: object, event: object) -> None:
			assert conn is not None
			audit_events.append(event)

	store = SqlAlchemySnapshotStore(
		session_factory,
		tenant_id=tenant_id,
		audit_sink=AuditSink(),
	)
	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	submitted = await store.fire_and_commit(
		wd=wd,
		instance=instance,
		event="submit",
		tenant_id=tenant_id,
	)
	approved = await store.fire_and_commit(
		wd=wd,
		instance=instance,
		event="approve",
		tenant_id=tenant_id,
	)

	assert submitted.new_state == "review"
	assert approved.new_state == "approved"
	assert approved.terminal is True

	async with session_factory() as session:
		instance_row = await session.scalar(
			select(WorkflowInstance).where(
				WorkflowInstance.tenant_id == tenant_id,
				WorkflowInstance.id == instance.id,
			)
		)
		assert instance_row is not None
		assert instance_row.state == "approved"
		assert instance_row.terminal is True
		assert instance_row.context["submitted"] is True

		snapshot = await session.scalar(
			select(WorkflowInstanceSnapshot).where(
				WorkflowInstanceSnapshot.tenant_id == tenant_id,
				WorkflowInstanceSnapshot.instance_id == instance.id,
			)
		)
		assert snapshot is not None
		assert snapshot.seq == 2

		events = (
			await session.scalars(
				select(WorkflowEvent)
				.where(
					WorkflowEvent.tenant_id == tenant_id,
					WorkflowEvent.instance_id == instance.id,
				)
				.order_by(WorkflowEvent.seq.asc())
			)
		).all()
		assert [(row.seq, row.event, row.transition_id) for row in events] == [
			(1, "submit", "submit"),
			(2, "approve", "approve"),
		]
		assert events[0].from_state == "intake"

		outbox_rows = (
			await session.scalars(
				select(OutboxMessage).where(
					OutboxMessage.tenant_id == tenant_id,
					OutboxMessage.status == "pending",
				)
			)
		).all()
		assert [row.kind for row in outbox_rows] == ["wf.notify"]

	assert len(audit_events) >= 2


async def test_snapshot_store_fire_and_commit_no_match_does_not_write_event(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	result = await store.fire_and_commit(
		wd=wd,
		instance=instance,
		event="approve",
		tenant_id=tenant_id,
	)

	assert result.matched_transition_id is None
	assert instance.state == "intake"
	async with session_factory() as session:
		rows = (
			await session.scalars(
				select(WorkflowEvent).where(
					WorkflowEvent.tenant_id == tenant_id,
					WorkflowEvent.instance_id == instance.id,
				)
			)
		).all()
		assert rows == []


async def test_snapshot_store_fire_and_commit_rejects_wrong_tenant(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	with pytest.raises(SnapshotTenantMismatch):
		await store.fire_and_commit(
			wd=wd,
			instance=instance,
			event="submit",
			tenant_id="other-tenant",
		)


async def test_snapshot_store_fire_and_commit_requires_transactional_audit_sink(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(
		session_factory,
		tenant_id=tenant_id,
		audit_sink=object(),
	)
	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	with pytest.raises(TypeError, match="record_in_connection"):
		await store.fire_and_commit(
			wd=wd,
			instance=instance,
			event="submit",
			tenant_id=tenant_id,
		)
	assert instance.state == "intake"
	assert instance.history == []


async def test_snapshot_store_fire_and_commit_rolls_back_on_stale_snapshot(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	stale = await store.get(instance.id)
	assert stale is not None
	await store.fire_and_commit(
		wd=wd,
		instance=instance,
		event="submit",
		tenant_id=tenant_id,
	)

	with pytest.raises(SnapshotConflict) as excinfo:
		await store.fire_and_commit(
			wd=wd,
			instance=stale,
			event="reject",
			tenant_id=tenant_id,
		)
	assert excinfo.value.actual_seq == 1
	assert stale.state == "intake"
	assert stale.history == []


async def test_snapshot_store_fire_and_commit_creates_missing_initial_snapshot(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	async with session_factory() as session:
		session.add(
			WorkflowInstance(
				id=instance.id,
				tenant_id=tenant_id,
				def_key=wd.key,
				def_version=wd.version,
				subject_kind=wd.subject_kind,
				state=instance.state,
				terminal=False,
				context={},
			)
		)
		await session.commit()

	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	result = await store.fire_and_commit(
		wd=wd,
		instance=instance,
		event="submit",
		tenant_id=tenant_id,
	)

	assert result.new_state == "review"
	loaded = await store.get(instance.id)
	assert loaded is not None
	assert loaded.state == "review"
	assert len(loaded.history) == 1


async def test_snapshot_store_fire_and_commit_converts_integrity_to_conflict(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	wd = _workflow_with_effects()
	instance = new_instance(wd)
	store = SqlAlchemySnapshotStore(session_factory, tenant_id=tenant_id)
	await store.create_instance(instance, workflow_def=wd, tenant_id=tenant_id)

	async def fail_compare(*args: object, **kwargs: object) -> None:
		_ = args, kwargs
		raise IntegrityError("update", {}, RuntimeError("duplicate"))

	monkeypatch.setattr(store, "_compare_and_put_in_session", fail_compare)
	with pytest.raises(SnapshotConflict) as excinfo:
		await store.fire_and_commit(
			wd=wd,
			instance=instance,
			event="submit",
			tenant_id=tenant_id,
		)

	assert excinfo.value.actual_seq == 0
	assert instance.state == "intake"
	assert instance.history == []


async def test_snapshot_store_serialization_helpers_cover_edge_shapes() -> None:
	wd = _workflow_def()
	assert _is_terminal_state(wd, "approved") is True
	assert _is_terminal_state(wd, "missing") is False

	row = WorkflowInstanceSnapshot(
		id=str(uuid.uuid4()),
		tenant_id="t-1",
		instance_id="inst-1",
		def_key="claim_intake",
		def_version="1.0.0",
		state="intake",
		body={},
		seq=0,
	)
	loaded = _instance_from_body(
		row,
		{
			"created_entities": [
				["claim", {"id": "c-1"}],
				["bad"],
				"not-a-pair",
			],
		},
	)
	assert loaded.id == "inst-1"
	assert loaded.created_entities == [("claim", {"id": "c-1"})]

	no_audit = FireResult(
		instance=loaded,
		matched_transition_id=None,
		planned_effects=[],
		new_state="intake",
		terminal=False,
	)
	assert _transition_payload(no_audit) == {}


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


async def test_saga_queries_filter_by_tenant(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst = await _seed_instance(session_factory, tenant_id)
	q = SagaQueries(session_factory, tenant_id=tenant_id)
	other_q = SagaQueries(session_factory, tenant_id="other-tenant")

	await q.append(inst.id, kind="release_lock", args={"k": "a"})

	assert [r.kind for r in await q.list_for_instance(inst.id)] == ["release_lock"]
	assert await other_q.list_for_instance(inst.id) == []
	assert await other_q.list_pending_for_compensation(inst.id) == []
	assert await other_q.mark(inst.id, 0, "compensated") is False
	assert [r.status for r in await q.list_for_instance(inst.id)] == ["pending"]


async def test_saga_queries_cross_tenant_append_does_not_share_idx(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst = await _seed_instance(session_factory, tenant_id)
	q = SagaQueries(session_factory, tenant_id=tenant_id)
	other_q = SagaQueries(session_factory, tenant_id="other-tenant")

	await q.append(inst.id, kind="release_lock")
	with pytest.raises(SagaTenantMismatch):
		await other_q.append(inst.id, kind="refund")

	assert [r.kind for r in await q.list_for_instance(inst.id)] == ["release_lock"]
	assert await other_q.list_for_instance(inst.id) == []


async def test_saga_queries_reject_invalid_status(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	inst = await _seed_instance(session_factory, tenant_id)
	q = SagaQueries(session_factory, tenant_id=tenant_id)

	with pytest.raises(AssertionError, match="invalid saga status"):
		await q.mark(inst.id, 0, "unknown")


async def test_saga_queries_append_integrity_error_surfaces_conflict(
	tenant_id: str,
) -> None:
	class FakeSession:
		def __init__(self) -> None:
			self.scalar_calls = 0
			self.rolled_back = False

		async def __aenter__(self) -> "FakeSession":
			return self

		async def __aexit__(
			self,
			exc_type: object,
			exc: object,
			tb: object,
		) -> None:
			return None

		async def scalar(self, _stmt: object) -> str | int | None:
			self.scalar_calls += 1
			return "owned-instance" if self.scalar_calls == 1 else None

		def add(self, row: object) -> None:
			assert isinstance(row, WorkflowSagaStep)
			assert row.idx == 0

		async def commit(self) -> None:
			raise IntegrityError("insert", {}, RuntimeError("duplicate idx"))

		async def rollback(self) -> None:
			self.rolled_back = True

	session = FakeSession()

	class FakeSessionFactory:
		def __call__(self) -> FakeSession:
			return session

	q = SagaQueries(
		cast(async_sessionmaker[AsyncSession], FakeSessionFactory()),
		tenant_id=tenant_id,
	)

	with pytest.raises(SagaConflict) as excinfo:
		await q.append("inst-1", kind="release_lock")
	assert excinfo.value.idx == 0
	assert session.rolled_back is True
