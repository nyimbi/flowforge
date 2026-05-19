"""Live Postgres release checks for transactional fire and drain behavior.

These tests are intentionally outside the default local integration suite.
Run with ``FLOWFORGE_TEST_PG_URL`` set to a disposable Postgres database:

    uv run --with asyncpg pytest tests/integration/postgres -q

The fixture creates a unique schema and drops only that schema at teardown.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from flowforge.dsl import WorkflowDef
from flowforge.engine import new_instance
from flowforge.ports.types import AuditEvent, OutboxEnvelope, Principal
from flowforge_audit_pg import PgAuditSink, create_tables as create_audit_tables
from flowforge_outbox_pg.registry import HandlerRegistry
from flowforge_outbox_pg.worker import DrainWorker
from flowforge_sqlalchemy import (
	Base,
	OutboxMessage,
	SnapshotConflict,
	SqlAlchemySnapshotStore,
	WorkflowDefinition,
	WorkflowDefinitionVersion,
	WorkflowInstance,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class LivePostgres:
	engine: AsyncEngine
	session_factory: async_sessionmaker[AsyncSession]
	asyncpg_url: str
	schema: str
	asyncpg: Any


def _raw_url() -> str:
	raw = os.getenv("FLOWFORGE_TEST_PG_URL") or os.getenv("FLOWFORGE_LIVE_PG_URL")
	if not raw:
		pytest.skip("set FLOWFORGE_TEST_PG_URL to run live Postgres release checks")
	return raw


def _sqlalchemy_url(raw: str) -> str:
	if raw.startswith("postgresql+asyncpg://"):
		return raw
	if raw.startswith("postgresql+psycopg2://"):
		return raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
	if raw.startswith("postgresql://"):
		return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
	return raw


def _asyncpg_url(raw: str) -> str:
	return (
		raw.replace("postgresql+asyncpg://", "postgresql://", 1)
		.replace("postgresql+psycopg2://", "postgresql://", 1)
	)


def _quote_ident(value: str) -> str:
	return '"' + value.replace('"', '""') + '"'


def _plan_uses_index(plan_doc: object, index_name: str) -> bool:
	if isinstance(plan_doc, str):
		plan_doc = json.loads(plan_doc)
	if not isinstance(plan_doc, list) or not plan_doc:
		return False
	root = plan_doc[0].get("Plan") if isinstance(plan_doc[0], dict) else None
	if not isinstance(root, dict):
		return False
	stack = [root]
	while stack:
		node = stack.pop()
		if node.get("Index Name") == index_name:
			return True
		children = node.get("Plans", [])
		if isinstance(children, list):
			stack.extend(child for child in children if isinstance(child, dict))
	return False


@pytest_asyncio.fixture
async def live_pg() -> AsyncIterator[LivePostgres]:
	raw_url = _raw_url()
	asyncpg = pytest.importorskip("asyncpg")
	schema = f"ff_live_pg_{uuid.uuid4().hex}"
	admin = create_async_engine(_sqlalchemy_url(raw_url), future=True)
	engine: AsyncEngine | None = None
	try:
		async with admin.begin() as conn:
			await conn.execute(text(f"CREATE SCHEMA {_quote_ident(schema)}"))
		engine = create_async_engine(
			_sqlalchemy_url(raw_url),
			future=True,
			connect_args={"server_settings": {"search_path": schema}},
		)
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
			await create_audit_tables(conn)
		yield LivePostgres(
			engine=engine,
			session_factory=async_sessionmaker(engine, expire_on_commit=False),
			asyncpg_url=_asyncpg_url(raw_url),
			schema=schema,
			asyncpg=asyncpg,
		)
	finally:
		if engine is not None:
			await engine.dispose()
		async with admin.begin() as conn:
			await conn.execute(text(f"DROP SCHEMA IF EXISTS {_quote_ident(schema)} CASCADE"))
		await admin.dispose()


@pytest.fixture
def claim_workflow_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "review", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "review",
					"effects": [{"kind": "audit", "template": "wf.claim.submitted"}],
				},
				{
					"id": "approve",
					"event": "approve",
					"from_state": "review",
					"to_state": "approved",
					"effects": [
						{"kind": "audit", "template": "wf.claim.approved"},
						{"kind": "notify", "template": "claim.approved.email"},
					],
				},
			],
		}
	)


async def _persist_def_and_instance(
	session_factory: async_sessionmaker[AsyncSession],
	wd: WorkflowDef,
	tenant_id: str,
) -> str:
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
	return instance_id


async def test_live_postgres_fire_and_commit_rejects_stale_snapshot(
	live_pg: LivePostgres,
	claim_workflow_def: WorkflowDef,
) -> None:
	tenant_id = "tenant-live-cas"
	instance_id = await _persist_def_and_instance(
		live_pg.session_factory,
		claim_workflow_def,
		tenant_id,
	)
	store = SqlAlchemySnapshotStore(live_pg.session_factory, tenant_id=tenant_id)
	initial = new_instance(claim_workflow_def, instance_id=instance_id)
	await store.put(initial)

	first = await store.get(instance_id)
	second = await store.get(instance_id)
	assert first is not None
	assert second is not None

	await store.fire_and_commit(
		wd=claim_workflow_def,
		instance=first,
		event="submit",
		principal=Principal(user_id="u-1"),
	)
	with pytest.raises(SnapshotConflict):
		await store.fire_and_commit(
			wd=claim_workflow_def,
			instance=second,
			event="submit",
			principal=Principal(user_id="u-2"),
		)


async def test_live_postgres_fire_and_commit_rows_drain_with_skip_locked(
	live_pg: LivePostgres,
	claim_workflow_def: WorkflowDef,
) -> None:
	tenant_id = "tenant-live-drain"
	instance_id = await _persist_def_and_instance(
		live_pg.session_factory,
		claim_workflow_def,
		tenant_id,
	)
	store = SqlAlchemySnapshotStore(
		live_pg.session_factory,
		tenant_id=tenant_id,
		audit_sink=PgAuditSink(live_pg.engine),
	)
	instance = new_instance(claim_workflow_def, instance_id=instance_id)
	await store.put(instance)
	await store.fire_and_commit(
		wd=claim_workflow_def,
		instance=instance,
		event="submit",
		principal=Principal(user_id="u-1"),
	)
	await store.fire_and_commit(
		wd=claim_workflow_def,
		instance=instance,
		event="approve",
		principal=Principal(user_id="u-1"),
	)

	received: list[OutboxEnvelope] = []
	registry = HandlerRegistry()

	async def _record(envelope: OutboxEnvelope) -> None:
		received.append(envelope)

	registry.register("wf.notify", _record)
	conn = await live_pg.asyncpg.connect(
		live_pg.asyncpg_url,
		server_settings={"search_path": live_pg.schema},
	)
	try:
		worker = DrainWorker(conn, registry, batch_size=10)
		result = await worker.run_once()
	finally:
		await conn.close()

	assert result.dispatched == 1
	assert result.retried == 0
	assert result.dead == 0
	assert result.no_handler == 0
	assert [envelope.kind for envelope in received] == ["wf.notify"]
	async with live_pg.session_factory() as session:
		status = await session.scalar(
			select(OutboxMessage.status).where(
				OutboxMessage.tenant_id == tenant_id,
				OutboxMessage.kind == "wf.notify",
			)
		)
	assert status == "dispatched"


async def test_live_postgres_audit_chain_verifies_interleaved_tenants(
	live_pg: LivePostgres,
) -> None:
	sink = PgAuditSink(live_pg.engine)
	for tenant_id, subject_id in [
		("tenant-a", "a-1"),
		("tenant-b", "b-1"),
		("tenant-a", "a-2"),
		("tenant-b", "b-2"),
	]:
		await sink.record(
			AuditEvent(
				kind="wf.test",
				subject_kind="claim",
				subject_id=subject_id,
				tenant_id=tenant_id,
				actor_user_id="auditor",
				payload={"tenant": tenant_id, "subject": subject_id},
			)
		)

	verdict = await sink.verify_chain()
	assert verdict.ok is True
	assert verdict.checked_count == 4


async def test_live_postgres_audit_chain_uses_tenant_ordinal_index(
	live_pg: LivePostgres,
) -> None:
	sink = PgAuditSink(live_pg.engine)
	for tenant_id in ("tenant-plan-a", "tenant-plan-b"):
		for idx in range(25):
			await sink.record(
				AuditEvent(
					kind="wf.plan",
					subject_kind="claim",
					subject_id=f"{tenant_id}-{idx}",
					tenant_id=tenant_id,
					actor_user_id="auditor",
					payload={"idx": idx},
				)
			)

	conn = await live_pg.asyncpg.connect(
		live_pg.asyncpg_url,
		server_settings={"search_path": live_pg.schema},
	)
	try:
		async with conn.transaction():
			await conn.execute("SET LOCAL enable_seqscan = off")
			plan_doc = await conn.fetchval(
				"""
				EXPLAIN (FORMAT JSON)
				SELECT event_id
				FROM ff_audit_events
				WHERE tenant_id = $1
				ORDER BY ordinal ASC NULLS LAST
				LIMIT 25
				""",
				"tenant-plan-a",
			)
	finally:
		await conn.close()

	assert _plan_uses_index(plan_doc, "ix_ff_audit_tenant_ordinal")
