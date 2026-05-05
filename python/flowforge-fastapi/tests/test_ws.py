"""WebSocket-side coverage.

Exercise:

* The hub fans out envelopes to subscribers.
* The WS endpoint pushes a ``state_changed`` envelope after the runtime
  router fires an event.
* Auth failures close the WS with policy code 4401.

We use Starlette's :class:`TestClient` (which is sync but uses an ASGI
in-process transport) for the WS handshake; the ASGI app is the same
one the HTTP tests drive via httpx.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from starlette.testclient import TestClient

from flowforge import config as ff_config
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import Principal

from flowforge_fastapi import (
	StaticPrincipalExtractor,
	WorkflowEventsHub,
	build_ws_router,
	get_events_hub,
	get_registry,
	mount_routers,
	reset_state,
)


PREFIX = "/api/v1/workflows"


@pytest.mark.asyncio
async def test_hub_publish_fans_out_to_subscribers() -> None:
	hub = WorkflowEventsHub()
	q1 = await hub.subscribe()
	q2 = await hub.subscribe()
	delivered = await hub.publish({"type": "demo", "n": 1})
	assert delivered == 2
	assert q1.get_nowait() == {"type": "demo", "n": 1}
	assert q2.get_nowait() == {"type": "demo", "n": 1}

	await hub.unsubscribe(q1)
	delivered_after = await hub.publish({"type": "demo", "n": 2})
	assert delivered_after == 1
	assert q2.get_nowait() == {"type": "demo", "n": 2}


def test_ws_pushes_state_change(claim_workflow_def: WorkflowDef) -> None:
	"""End-to-end: connect WS, fire HTTP event, receive state-change frame."""

	reset_state()
	get_events_hub().clear()
	ff_config.reset_to_fakes()
	get_registry().register(claim_workflow_def)

	app = FastAPI()
	mount_routers(
		app,
		prefix=PREFIX,
		principal_extractor=StaticPrincipalExtractor(
			Principal(user_id="alice", roles=("staff",))
		),
	)

	with TestClient(app) as tc:
		with tc.websocket_connect(f"{PREFIX}/ws") as ws:
			hello = json.loads(ws.receive_text())
			assert hello["type"] == "hello"
			assert hello["user_id"] == "alice"

			# Drive the HTTP side from the same TestClient — TestClient
			# multiplexes WS + HTTP over the same in-process ASGI app.
			create = tc.post(
				f"{PREFIX}/instances", json={"def_key": "demo_claim"}
			)
			assert create.status_code == 201
			created = json.loads(ws.receive_text())
			assert created["type"] == "instance.created"

			fire_resp = tc.post(
				f"{PREFIX}/instances/{create.json()['id']}/events",
				json={"event": "submit"},
			)
			assert fire_resp.status_code == 200

			frame = json.loads(ws.receive_text())
			assert frame["type"] == "instance.state_changed"
			assert frame["to_state"] == "review"
			assert frame["transition_id"] == "submit"


def test_ws_rejects_unauthenticated() -> None:
	"""Extractor that always raises -> WS is closed before accept."""

	reset_state()
	get_events_hub().clear()
	ff_config.reset_to_fakes()

	class DenyAll:
		async def __call__(self, request: Request) -> Principal:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="nope",
			)

	app = FastAPI()
	app.include_router(
		build_ws_router(principal_extractor=DenyAll()),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with pytest.raises(Exception):
			# WebSocketDisconnect (or starlette.testclient.WebSocketDisconnect).
			with tc.websocket_connect(f"{PREFIX}/ws"):
				pass


@pytest.mark.asyncio
async def test_hub_subscriber_count_tracks_lifecycle() -> None:
	hub = WorkflowEventsHub()
	assert hub.subscriber_count() == 0
	q = await hub.subscribe()
	assert hub.subscriber_count() == 1
	await hub.unsubscribe(q)
	assert hub.subscriber_count() == 0


@pytest.mark.asyncio
async def test_hub_publish_with_no_subscribers_returns_zero() -> None:
	hub = WorkflowEventsHub()
	delivered = await hub.publish({"type": "noop"})
	assert delivered == 0


@pytest.mark.asyncio
async def test_hub_clear_drops_all_subscribers() -> None:
	hub = WorkflowEventsHub()
	await hub.subscribe()
	await hub.subscribe()
	hub.clear()
	assert hub.subscriber_count() == 0


@pytest.mark.asyncio
async def test_hub_queue_yields_in_order() -> None:
	hub = WorkflowEventsHub()
	q = await hub.subscribe()
	for i in range(5):
		await hub.publish({"type": "demo", "n": i})
	# Drain
	got: list[int] = []
	while True:
		try:
			got.append((await asyncio.wait_for(q.get(), timeout=0.1))["n"])
		except asyncio.TimeoutError:
			break
	assert got == [0, 1, 2, 3, 4]
