"""Integration test #3: FastAPI full-stack HTTP + WS round-trip.

Stands up a FastAPI app via :func:`flowforge_fastapi.mount_routers` with
real adapters wired in:

* ``flowforge-sqlalchemy`` ``SqlAlchemySnapshotStore`` for instance state.
* ``flowforge-audit-pg`` ``PgAuditSink`` for audit writes (sqlite fallback).
* ``flowforge-outbox-pg`` ``DrainWorker`` is constructed but not driven —
  the engine's ``config.outbox`` port enqueues into it transparently.
* ``flowforge-rbac-static`` resolver, ``flowforge-tenancy.SingleTenantGUC``,
  ``flowforge-money.StaticMoneyPort``, ``flowforge-signing-kms.HmacDevSigning``,
  ``flowforge-notify-multichannel`` (FakeInAppAdapter), and
  ``flowforge-documents-s3`` (NoopDocumentPort) cover the remaining ports.

Drives a full HTTP round-trip:

* POST /defs/validate (publish workflow)
* POST /instances (start)
* POST /instances/{id}/events (advance)
* GET /instances/{id} (snapshot)
* WS /ws (events fan out)
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import aiosqlite
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from flowforge import config as ff_config
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import OutboxEnvelope, Principal
from flowforge_audit_pg import PgAuditSink, ff_audit_events
from flowforge_documents_s3 import NoopDocumentPort
from flowforge_fastapi import (
	StaticPrincipalExtractor,
	StaticTenantResolver,
	get_events_hub,
	get_instance_store,
	get_registry,
	mount_routers,
	reset_state,
)
from flowforge_money import StaticMoneyPort, StaticRateProvider
from flowforge_notify_multichannel.transports import FakeInAppAdapter
from flowforge_outbox_pg import DrainWorker, HandlerRegistry
from flowforge_rbac_static import StaticRbac
from flowforge_signing_kms import HmacDevSigning
from flowforge_tenancy import SingleTenantGUC
from flowforge_sqlalchemy import (
	OutboxMessage,
	SqlAlchemySnapshotStore,
	WorkflowEvent,
	WorkflowInstance,
	WorkflowInstanceSnapshot,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.testclient import TestClient

pytestmark = pytest.mark.asyncio

PREFIX = "/api/v1/workflows"


@pytest_asyncio.fixture
async def real_adapters_app(
	sqla_engine: AsyncEngine,
	session_factory: async_sessionmaker[AsyncSession],
	claim_workflow_def: WorkflowDef,
) -> AsyncIterator[tuple[FastAPI, HandlerRegistry, list[OutboxEnvelope]]]:
	"""Spin up FastAPI with all real adapters wired through ``flowforge.config``."""

	# Reset adapter + core state.
	reset_state()
	get_events_hub().clear()
	ff_config.reset_to_fakes()

	# Audit (real PgAuditSink on aiosqlite via the shared sqla_engine).
	ff_config.audit = PgAuditSink(sqla_engine)

	# Outbox: outbox-pg DrainWorker on its own aiosqlite connection.
	conn = await aiosqlite.connect(":memory:")
	registry = HandlerRegistry()
	dispatched: list[OutboxEnvelope] = []

	async def _capture(env: OutboxEnvelope) -> None:
		dispatched.append(env)

	registry.register("wf.notify", _capture, backend="default")
	worker = DrainWorker(conn, registry, sqlite_compat=True)
	await worker.setup()

	class _OutboxAdapter:
		async def dispatch(self, envelope: OutboxEnvelope) -> None:
			await worker.enqueue(envelope)

	ff_config.outbox = _OutboxAdapter()

	# RBAC, tenancy, money, signing, notify, documents.
	ff_config.rbac = StaticRbac(
		{
			"roles": {"staff": ["claim.submit", "claim.approve", "claim.read"]},
			"principals": {"alice": ["staff"]},
			"permissions": [
				{"name": "claim.submit", "description": "submit"},
				{"name": "claim.approve", "description": "approve"},
				{"name": "claim.read", "description": "read"},
			],
		}
	)
	ff_config.tenancy = SingleTenantGUC("t-1")
	from decimal import Decimal

	ff_config.money = StaticMoneyPort(
		StaticRateProvider({"USD": {"ZAR": Decimal("18.5")}})
	)
	ff_config.signing = HmacDevSigning(secret="dev-secret", key_id="k1")
	ff_config.notification = FakeInAppAdapter()
	ff_config.documents = NoopDocumentPort()

	# Register the workflow def.
	get_registry().register(claim_workflow_def)

	app = FastAPI()
	mount_routers(
		app,
		prefix=PREFIX,
		principal_extractor=StaticPrincipalExtractor(
			Principal(user_id="alice", roles=("staff",))
		),
		tenant_resolver=StaticTenantResolver("t-1"),
	)
	app.dependency_overrides[get_instance_store] = lambda: SqlAlchemySnapshotStore(
		session_factory,
		tenant_id="t-1",
		audit_sink=ff_config.audit,
	)

	try:
		yield app, registry, dispatched
	finally:
		await conn.close()


@pytest_asyncio.fixture
async def http_client(real_adapters_app) -> AsyncIterator[httpx.AsyncClient]:
	app, _, _ = real_adapters_app
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as ac:
		yield ac


async def test_full_round_trip_designer_runtime(
	http_client: httpx.AsyncClient,
	session_factory: async_sessionmaker[AsyncSession],
) -> None:
	# 1. Designer: list defs.
	defs_resp = await http_client.get(f"{PREFIX}/defs")
	assert defs_resp.status_code == 200
	keys = [d["key"] for d in defs_resp.json()["defs"]]
	assert "claim_intake" in keys

	# 2. Runtime: start an instance.
	create_resp = await http_client.post(
		f"{PREFIX}/instances",
		json={"def_key": "claim_intake", "tenant_id": "t-1"},
	)
	assert create_resp.status_code == 201, create_resp.text
	instance = create_resp.json()
	instance_id = instance["id"]
	assert instance["state"] == "intake"

	# 3. Fire submit -> review (writes audit + enqueues outbox).
	submit = await http_client.post(
		f"{PREFIX}/instances/{instance_id}/events",
		json={"event": "submit", "tenant_id": "t-1"},
	)
	assert submit.status_code == 200, submit.text
	assert submit.json()["new_state"] == "review"

	# 4. Fire approve -> approved (terminal, also notifies).
	approve = await http_client.post(
		f"{PREFIX}/instances/{instance_id}/events",
		json={"event": "approve", "tenant_id": "t-1"},
	)
	assert approve.status_code == 200
	body = approve.json()
	assert body["terminal"] is True
	assert body["new_state"] == "approved"

	# 5. GET snapshot.
	snap = await http_client.get(f"{PREFIX}/instances/{instance_id}")
	assert snap.status_code == 200
	assert snap.json()["state"] == "approved"

	# 6. SQL-backed runtime state, audit, events, and durable outbox rows exist.
	async with session_factory() as session:
		instance_row = await session.scalar(
			select(WorkflowInstance).where(
				WorkflowInstance.tenant_id == "t-1",
				WorkflowInstance.id == instance_id,
			)
		)
		assert instance_row is not None
		assert instance_row.state == "approved"
		assert instance_row.terminal is True

		snapshot = await session.scalar(
			select(WorkflowInstanceSnapshot).where(
				WorkflowInstanceSnapshot.tenant_id == "t-1",
				WorkflowInstanceSnapshot.instance_id == instance_id,
			)
		)
		assert snapshot is not None
		assert snapshot.state == "approved"
		assert snapshot.seq == 2

		events = (
			await session.scalars(
				select(WorkflowEvent)
				.where(
					WorkflowEvent.tenant_id == "t-1",
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
					OutboxMessage.tenant_id == "t-1",
					OutboxMessage.status == "pending",
				)
			)
		).all()
		assert [row.kind for row in outbox_rows] == ["wf.notify"]

		audit_count = await session.scalar(
			select(func.count()).select_from(ff_audit_events)
		)
		assert audit_count is not None
		assert audit_count >= 4


@pytest.mark.asyncio(loop_scope="function")
async def test_ws_state_change_envelope_is_published(
	real_adapters_app,
	claim_workflow_def: WorkflowDef,
) -> None:
	"""WebSocket subscribers receive ``instance.state_changed`` after a fire."""
	app, _, _ = real_adapters_app

	with TestClient(app) as tc:
		with tc.websocket_connect(f"{PREFIX}/ws") as ws:
			hello = json.loads(ws.receive_text())
			assert hello["type"] == "hello"

			create = tc.post(
				f"{PREFIX}/instances",
				json={"def_key": "claim_intake", "tenant_id": "t-1"},
			)
			assert create.status_code == 201
			# Drain the create envelope.
			created = json.loads(ws.receive_text())
			assert created["type"] == "instance.created"

			fire_resp = tc.post(
				f"{PREFIX}/instances/{create.json()['id']}/events",
				json={"event": "submit", "tenant_id": "t-1"},
			)
			assert fire_resp.status_code == 200

			env = json.loads(ws.receive_text())
			assert env["type"] == "instance.state_changed"
			assert env["from_state"] == "intake"
			assert env["to_state"] == "review"
