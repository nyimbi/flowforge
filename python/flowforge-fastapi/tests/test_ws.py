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
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException, Request, status
from starlette.testclient import TestClient

from flowforge import config as ff_config
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import Principal

from flowforge_fastapi import (
	StaticPrincipalExtractor,
	StaticTenantResolver,
	WorkflowEventsHub,
	build_ws_router,
	get_events_hub,
	get_registry,
	mount_routers,
	reset_state,
)
from flowforge_fastapi.ws import _extract_ws_principal, _hub_for


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
		tenant_resolver=StaticTenantResolver("t-1"),
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


def test_ws_rejects_cross_site_browser_origin() -> None:
	"""Browser-originated WS handshakes must not be accepted cross-site."""

	app = FastAPI()
	app.include_router(
		build_ws_router(
			principal_extractor=StaticPrincipalExtractor(
				Principal(user_id="alice", roles=("staff",))
			)
		),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with pytest.raises(Exception):
			with tc.websocket_connect(
				f"{PREFIX}/ws",
				headers={"origin": "https://evil.example"},
			):
				pass


def test_ws_accepts_same_origin_browser_handshake() -> None:
	"""Default Origin policy allows same-origin browser connections."""

	app = FastAPI()
	app.include_router(
		build_ws_router(
			principal_extractor=StaticPrincipalExtractor(
				Principal(user_id="alice", roles=("staff",))
			)
		),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with tc.websocket_connect(
			f"{PREFIX}/ws",
			headers={"origin": "http://testserver"},
		) as ws:
			hello = json.loads(ws.receive_text())
			assert hello["type"] == "hello"
			assert hello["user_id"] == "alice"


def test_ws_accepts_explicit_allowed_origin() -> None:
	"""Hosts can trust a separate admin origin explicitly."""

	app = FastAPI()
	app.include_router(
		build_ws_router(
			principal_extractor=StaticPrincipalExtractor(
				Principal(user_id="alice", roles=("staff",))
			),
			allowed_origins=("https://admin.example",),
		),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with tc.websocket_connect(
			f"{PREFIX}/ws",
			headers={"origin": "https://admin.example"},
		) as ws:
			hello = json.loads(ws.receive_text())
			assert hello["type"] == "hello"


def test_ws_accepts_wildcard_allowed_origin() -> None:
	app = FastAPI()
	app.include_router(
		build_ws_router(
			principal_extractor=StaticPrincipalExtractor(
				Principal(user_id="alice", roles=("staff",))
			),
			allowed_origins=("*",),
		),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with tc.websocket_connect(
			f"{PREFIX}/ws",
			headers={"origin": "https://any.example"},
		) as ws:
			assert json.loads(ws.receive_text())["type"] == "hello"


def test_ws_uses_explicit_ws_principal_extractor() -> None:
	class WsExtractor:
		async def __call__(self, websocket) -> Principal:
			return Principal(user_id=websocket.headers["x-user"], roles=("staff",))

	app = FastAPI()
	app.include_router(build_ws_router(ws_principal_extractor=WsExtractor()), prefix=PREFIX)

	with TestClient(app) as tc:
		with tc.websocket_connect(f"{PREFIX}/ws", headers={"x-user": "ws-user"}) as ws:
			hello = json.loads(ws.receive_text())
			assert hello["user_id"] == "ws-user"


def test_ws_uses_test_defaults_when_explicitly_allowed() -> None:
	app = FastAPI()
	app.include_router(build_ws_router(allow_test_defaults=True), prefix=PREFIX)

	with TestClient(app) as tc:
		with tc.websocket_connect(f"{PREFIX}/ws") as ws:
			hello = json.loads(ws.receive_text())
			assert hello["user_id"] == "system"


def test_ws_rejects_same_host_wrong_scheme_origin() -> None:
	"""Same-origin checks include scheme, not just host."""

	app = FastAPI()
	app.include_router(
		build_ws_router(
			principal_extractor=StaticPrincipalExtractor(
				Principal(user_id="alice", roles=("staff",))
			)
		),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with pytest.raises(Exception):
			with tc.websocket_connect(
				f"{PREFIX}/ws",
				headers={"origin": "https://testserver"},
			):
				pass


def test_ws_allowed_origins_are_additive_to_same_origin() -> None:
	"""Explicit extra origins do not disable default same-origin support."""

	app = FastAPI()
	app.include_router(
		build_ws_router(
			principal_extractor=StaticPrincipalExtractor(
				Principal(user_id="alice", roles=("staff",))
			),
			allowed_origins=("https://admin.example",),
		),
		prefix=PREFIX,
	)

	with TestClient(app) as tc:
		with tc.websocket_connect(
			f"{PREFIX}/ws",
			headers={"origin": "http://testserver"},
		) as ws:
			hello = json.loads(ws.receive_text())
			assert hello["type"] == "hello"


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


@pytest.mark.asyncio
async def test_hub_uses_bounded_subscriber_queues() -> None:
	hub = WorkflowEventsHub(max_queue_size=1)
	q = await hub.subscribe()

	assert await hub.publish({"type": "demo", "n": 1}) == 1
	assert await hub.publish({"type": "demo", "n": 2}) == 0
	assert q.qsize() == 1
	assert q.get_nowait() == {"type": "demo", "n": 1}
	assert hub.metrics()["dropped_total"] == 1


@pytest.mark.asyncio
async def test_hub_exposes_drop_metrics_and_prometheus_text() -> None:
	hub = WorkflowEventsHub(max_queue_size=1)
	q = await hub.subscribe()

	assert hub.metrics() == {
		"subscribers": 1,
		"max_queue_size": 1,
		"published_total": 0,
		"delivered_total": 0,
		"dropped_total": 0,
	}

	assert await hub.publish({"type": "demo", "n": 1}) == 1
	assert await hub.publish({"type": "demo", "n": 2}) == 0

	assert q.get_nowait() == {"type": "demo", "n": 1}
	assert hub.metrics() == {
		"subscribers": 1,
		"max_queue_size": 1,
		"published_total": 2,
		"delivered_total": 1,
		"dropped_total": 1,
	}
	text = hub.prometheus_text()
	assert "flowforge_fastapi_ws_subscribers 1" in text
	assert "flowforge_fastapi_ws_published_envelopes_total 2" in text
	assert "flowforge_fastapi_ws_delivered_envelopes_total 1" in text
	assert "flowforge_fastapi_ws_dropped_envelopes_total 1" in text


@pytest.mark.asyncio
async def test_ws_internal_extract_closes_on_generic_auth_failure() -> None:
	class FailingExtractor:
		async def __call__(self, websocket) -> Principal:
			_ = websocket
			raise RuntimeError("token backend down")

	class FakeWebSocket:
		def __init__(self) -> None:
			self.close_codes: list[int] = []

		async def close(self, *, code: int) -> None:
			self.close_codes.append(code)

	websocket = FakeWebSocket()
	principal = await _extract_ws_principal(
		cast(Any, websocket),
		FailingExtractor(),
	)
	assert principal is None
	assert websocket.close_codes == [4401]


def test_hub_for_falls_back_when_app_has_no_hub() -> None:
	class NoApp:
		pass

	assert isinstance(_hub_for(cast(Any, NoApp())), WorkflowEventsHub)

	class State:
		pass

	class App:
		state = State()

	class WebSocket:
		app = App()

	assert isinstance(_hub_for(cast(Any, WebSocket())), WorkflowEventsHub)
