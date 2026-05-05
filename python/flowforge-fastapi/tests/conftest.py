"""Shared pytest fixtures for flowforge-fastapi tests.

Each test gets:

* A fresh FastAPI app with all three routers mounted.
* A clean :func:`flowforge.config.reset_to_fakes` state.
* The module-level adapter registries reset.
* An ``httpx.AsyncClient`` wired through ``httpx.ASGITransport`` so
  requests run in-process — no port binding.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import Principal

from flowforge_fastapi import (
	StaticPrincipalExtractor,
	get_events_hub,
	get_registry,
	mount_routers,
	reset_state,
)


@pytest.fixture()
def claim_workflow_def() -> WorkflowDef:
	"""Three-state workflow used by every router test."""

	return WorkflowDef.model_validate(
		{
			"key": "demo_claim",
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
						{
							"kind": "set",
							"target": "context.submitted",
							"expr": True,
						}
					],
				},
				{
					"id": "approve",
					"event": "approve",
					"from_state": "review",
					"to_state": "approved",
					"priority": 0,
					"effects": [
						{"kind": "audit", "template": "wf.demo_claim.approved"}
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


@pytest.fixture()
def app(claim_workflow_def: WorkflowDef) -> FastAPI:
	"""FastAPI app with adapter routers + a test principal."""

	# Reset adapter + core state for full isolation.
	reset_state()
	get_events_hub().clear()
	config.reset_to_fakes()
	get_registry().register(claim_workflow_def)

	app = FastAPI()
	mount_routers(
		app,
		prefix="/api/v1/workflows",
		principal_extractor=StaticPrincipalExtractor(
			Principal(user_id="alice", roles=("staff",))
		),
	)
	return app


@pytest_asyncio.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
	"""``httpx.AsyncClient`` over the ASGI app — no real server."""

	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(
		transport=transport, base_url="http://testserver"
	) as ac:
		yield ac


@pytest.fixture()
def hub_envelopes() -> list[dict[str, Any]]:
	"""Convenience accumulator some tests pull from the hub."""

	return []
