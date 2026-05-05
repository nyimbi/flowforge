"""Shared fixtures for the cross-package integration suite.

Each test gets its own in-memory SQLite engine so tables and audit chains
are fully isolated. The flowforge ``config`` ports are reset to fakes by
default; tests opt in to real adapters by overwriting the relevant ports.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
	AsyncEngine,
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)

from flowforge import config as ff_config
from flowforge.dsl import WorkflowDef
from flowforge_audit_pg.sink import create_tables as create_audit_tables
from flowforge_sqlalchemy import Base


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqla_engine() -> AsyncIterator[AsyncEngine]:
	"""Per-test in-memory aiosqlite engine with all flowforge tables created.

	Tables created:
	    * The ten engine-managed tables (``flowforge_sqlalchemy.Base``).
	    * ``ff_audit_events`` (created via ``flowforge_audit_pg.sink.create_tables``).
	"""
	engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
		await create_audit_tables(conn)
	try:
		yield engine
	finally:
		await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(sqla_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
	return async_sessionmaker(sqla_engine, expire_on_commit=False)


@pytest.fixture
def tenant_id() -> str:
	return "tenant-int"


# ---------------------------------------------------------------------------
# Port reset
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_ports() -> None:
	"""Reset ports between tests so leftover state never leaks across cases."""
	ff_config.reset_to_fakes()


# ---------------------------------------------------------------------------
# Reusable workflow defs
# ---------------------------------------------------------------------------


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
				{"name": "rejected", "kind": "terminal_fail"},
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
				{
					"id": "reject",
					"event": "reject",
					"from_state": "review",
					"to_state": "rejected",
					"priority": 0,
				},
			],
		}
	)


@pytest.fixture
def parallel_workflow_def() -> WorkflowDef:
	"""Workflow with two parallel regions joined at the end.

	Topology::

	    intake --(submit)--> region_a (manual)
	                        \\--(submit)--> region_b (manual)
	    region_a --(done_a)-> region_a_done
	    region_b --(done_b)-> region_b_done
	    Once both regions are "done", a join transition completes the workflow.
	"""

	return WorkflowDef.model_validate(
		{
			"key": "parallel_demo",
			"version": "1.0.0",
			"subject_kind": "demo",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "region_a", "kind": "manual_review"},
				{"name": "region_b", "kind": "manual_review"},
				{"name": "region_a_done", "kind": "manual_review"},
				{"name": "region_b_done", "kind": "manual_review"},
				{"name": "joined", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "fork_a",
					"event": "start_a",
					"from_state": "intake",
					"to_state": "region_a",
				},
				{
					"id": "fork_b",
					"event": "start_b",
					"from_state": "region_a",
					"to_state": "region_b",
					"effects": [{"kind": "set", "target": "context.region_a_state", "expr": "active"}],
				},
				{
					"id": "done_a",
					"event": "done_a",
					"from_state": "region_b",
					"to_state": "region_a_done",
					"effects": [{"kind": "set", "target": "context.region_a_done", "expr": True}],
				},
				{
					"id": "done_b",
					"event": "done_b",
					"from_state": "region_a_done",
					"to_state": "region_b_done",
					"effects": [{"kind": "set", "target": "context.region_b_done", "expr": True}],
				},
				{
					"id": "join",
					"event": "join",
					"from_state": "region_b_done",
					"to_state": "joined",
					"guards": [
						{"kind": "expr", "expr": {"and": [
							{"var": "context.region_a_done"},
							{"var": "context.region_b_done"},
						]}}
					],
				},
			],
		}
	)


@pytest.fixture
def gated_workflow_def() -> WorkflowDef:
	"""Workflow whose ``submit`` transition is permission-gated."""

	return WorkflowDef.model_validate(
		{
			"key": "gated_demo",
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
					"gates": [
						{"kind": "permission", "permission": "claim.submit"},
					],
				},
			],
		}
	)


@pytest.fixture
def saga_workflow_def() -> WorkflowDef:
	"""Workflow that records a compensation step on its first transition."""
	return WorkflowDef.model_validate(
		{
			"key": "saga_demo",
			"version": "1.0.0",
			"subject_kind": "demo",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "reserved", "kind": "manual_review"},
				{"name": "done", "kind": "terminal_success"},
				{"name": "rolled_back", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "reserve",
					"event": "reserve",
					"from_state": "intake",
					"to_state": "reserved",
					"effects": [
						{"kind": "compensate", "compensation_kind": "release_reservation",
						 "values": {"resource": "slot-1"}},
						{"kind": "notify", "template": "reserve.notify"},
					],
				},
				{
					"id": "complete",
					"event": "complete",
					"from_state": "reserved",
					"to_state": "done",
				},
				{
					"id": "rollback",
					"event": "rollback",
					"from_state": "reserved",
					"to_state": "rolled_back",
				},
			],
		}
	)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def fixture_lookup_data() -> dict[str, Any]:
	"""Sample lookup data used by the determinism test."""
	return {"limit": 100000, "currency": "USD"}
