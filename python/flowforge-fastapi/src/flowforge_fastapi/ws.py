"""WebSocket fan-out hub.

Single in-process pub/sub. The runtime router ``await``s
:meth:`WorkflowEventsHub.publish` after every state-changing event;
WebSocket subscribers receive the JSON envelope as a text frame.

E-41 hardening (audit-fix-plan §4.2, §4.3):

* **FA-03**.  WS auth now flows through :class:`WSPrincipalExtractor`
  which receives the :class:`WebSocket` directly.  The legacy
  HTTP-scope-spoof trampoline is gone — pre-fix the framework mutated
  ``websocket.scope['type']`` from ``"websocket"`` to ``"http"`` so a
  ``Request``-shaped extractor would parse cookies, but that lied to
  any code downstream that read ``scope['type']``.
* **FA-04**.  The hub is now per-FastAPI-app.  ``mount_routers`` builds
  a fresh :class:`WorkflowEventsHub` and pins it to ``app.state``;
  ``get_events_hub`` is overridden as a FastAPI dependency on each
  app, so two apps in the same process never share subscribers and
  cross-test leak is structurally impossible.

We deliberately keep this in-process — multi-host fan-out belongs in a
real broker (Redis pub/sub, NATS, Postgres LISTEN/NOTIFY) wired by an
``OutboxRegistry`` adapter. The hub only mediates the local connection
set so tests can verify the WS contract end-to-end with
``httpx.ASGITransport``-equivalent WS clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from flowforge.ports.types import Principal

from .auth import (
	PrincipalExtractor,
	StaticPrincipalExtractor,
	WSPrincipalExtractor,
)


logger = logging.getLogger(__name__)


class WorkflowEventsHub:
	"""In-process broadcast hub.

	Subscribers receive a fresh :class:`asyncio.Queue`; the hub fans out
	every published envelope to every queue. Disconnected subscribers are
	dropped on next publish.
	"""

	def __init__(self) -> None:
		self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
		self._lock = asyncio.Lock()

	async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
		queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
		async with self._lock:
			self._subscribers.add(queue)
		return queue

	async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
		async with self._lock:
			self._subscribers.discard(queue)

	async def publish(self, envelope: dict[str, Any]) -> int:
		"""Fan out *envelope* to every subscriber; return delivered count."""

		async with self._lock:
			targets = list(self._subscribers)
		delivered = 0
		for q in targets:
			try:
				q.put_nowait(envelope)
				delivered += 1
			except asyncio.QueueFull:  # pragma: no cover - default queues are unbounded
				logger.warning("flowforge-fastapi: hub subscriber queue full; dropping")
		return delivered

	def subscriber_count(self) -> int:
		return len(self._subscribers)

	def clear(self) -> None:
		"""Drop every subscriber. Tests use this between cases."""

		self._subscribers.clear()


# Module-level singleton kept ONLY as the default returned by
# :func:`get_events_hub` when no app-scoped override is wired (e.g.
# the legacy code path that reaches ``get_events_hub`` without going
# through ``mount_routers``).  E-41 / FA-04: ``mount_routers`` overrides
# this dependency with the per-app hub stored on ``app.state``.
_hub = WorkflowEventsHub()


def get_events_hub() -> WorkflowEventsHub:
	"""Return the default :class:`WorkflowEventsHub`.

	FastAPI apps wired via :func:`flowforge_fastapi.mount_routers`
	override this dependency to return the app-scoped hub on
	``app.state.flowforge_events_hub``; tests that build a router
	directly without ``mount_routers`` keep using the module default.
	"""

	return _hub


class _HTTPOnlyAdapter:
	"""Adapter that wraps a :class:`PrincipalExtractor` so it can be used
	as a :class:`WSPrincipalExtractor`.

	E-41 / FA-03: even when a host opts in to this shim for backward
	compatibility, the WebSocket scope is NEVER mutated.  Cookie /
	header reads happen against the WS scope directly via
	``websocket.cookies`` and ``websocket.headers``, both of which
	starlette already exposes natively.

	If the underlying HTTP extractor *needs* a real :class:`Request`
	(e.g. it inspects ``request.url`` or anything beyond cookies/headers),
	this adapter is the wrong tool — supply a native
	:class:`WSPrincipalExtractor` instead.
	"""

	def __init__(self, http_extractor: PrincipalExtractor) -> None:
		self._http = http_extractor

	async def __call__(self, websocket: WebSocket) -> Principal:
		# Build a faux Request from the WS-side cookies/headers without
		# mutating the original scope.  The faux scope is constructed
		# fresh and never reused.
		from starlette.requests import Request

		http_scope = {
			"type": "http",
			"method": "GET",
			"path": websocket.scope.get("path", "/"),
			"raw_path": websocket.scope.get("raw_path", b"/"),
			"query_string": websocket.scope.get("query_string", b""),
			"headers": list(websocket.scope.get("headers", [])),
		}
		request = Request(scope=http_scope)
		return await self._http(request)


def build_ws_router(
	*,
	principal_extractor: PrincipalExtractor | None = None,
	ws_principal_extractor: WSPrincipalExtractor | None = None,
	path: str = "/ws",
) -> APIRouter:
	"""Construct the WebSocket router.

	Behaviour:

	* The handshake calls *ws_principal_extractor* (preferred) with the
	  :class:`WebSocket` directly.  If ``ws_principal_extractor`` is None
	  but a legacy ``principal_extractor`` was supplied, the legacy one
	  is wrapped in :class:`_HTTPOnlyAdapter` so the WS scope is read
	  honestly without mutation.  When extraction raises, the socket
	  closes with policy violation (4401).
	* Once connected, the client receives a small ``hello`` frame and
	  then every published envelope.

	E-41 / FA-03: the WS scope is never mutated — pre-fix the framework
	flipped ``scope['type']`` from ``"websocket"`` to ``"http"`` to
	satisfy ``starlette.requests.Request``, which lied to any consumer
	that inspected the scope downstream.
	"""

	resolved_ws_extractor: WSPrincipalExtractor
	if ws_principal_extractor is not None:
		resolved_ws_extractor = ws_principal_extractor
	elif principal_extractor is not None:
		resolved_ws_extractor = _HTTPOnlyAdapter(principal_extractor)
	else:
		# Default: no auth — wrapper around the static extractor.
		resolved_ws_extractor = StaticPrincipalExtractor()  # type: ignore[assignment]

	router = APIRouter(tags=["flowforge-ws"])

	@router.websocket(path)
	async def ws_endpoint(websocket: WebSocket) -> None:
		principal = await _extract_ws_principal(websocket, resolved_ws_extractor)
		if principal is None:
			# Already closed inside helper.
			return

		await websocket.accept()
		# E-41 / FA-04: prefer the per-app hub when the WS endpoint runs
		# inside a mount_routers-wired app.  ``app.state`` is reachable
		# via ``websocket.app``; fall back to the module default for
		# router-direct test setups.
		hub = _hub_for(websocket)
		queue = await hub.subscribe()
		try:
			await websocket.send_text(
				json.dumps(
					{
						"type": "hello",
						"user_id": principal.user_id,
					}
				)
			)
			while True:
				try:
					envelope = await queue.get()
				except asyncio.CancelledError:
					break
				await websocket.send_text(json.dumps(envelope))
		except WebSocketDisconnect:
			pass
		finally:
			await hub.unsubscribe(queue)

	return router


def _hub_for(websocket: WebSocket) -> WorkflowEventsHub:
	"""Return the per-app hub if one is pinned to ``app.state``, else the default."""
	app = getattr(websocket, "app", None)
	if app is not None:
		hub = getattr(app.state, "flowforge_events_hub", None)
		if isinstance(hub, WorkflowEventsHub):
			return hub
	return _hub


async def _extract_ws_principal(
	websocket: WebSocket,
	extractor: WSPrincipalExtractor,
) -> Principal | None:
	"""Run *extractor* on the live :class:`WebSocket`; close on failure.

	Returns the principal or ``None`` after closing the socket.
	"""
	try:
		principal = await extractor(websocket)
	except HTTPException as exc:
		logger.info("flowforge-fastapi: WS auth rejected (HTTPException %d)", exc.status_code)
		await websocket.close(code=4401)
		return None
	except Exception as exc:  # noqa: BLE001 — close on any auth failure
		logger.info("flowforge-fastapi: WS auth failed: %s", exc)
		await websocket.close(code=4401)
		return None
	return principal


__all__ = [
	"WorkflowEventsHub",
	"build_ws_router",
	"get_events_hub",
]
