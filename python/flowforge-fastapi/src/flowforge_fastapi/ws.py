"""WebSocket fan-out hub.

Single in-process pub/sub. The runtime router ``await``s
:meth:`WorkflowEventsHub.publish` after every state-changing event;
WebSocket subscribers receive the JSON envelope as a text frame.

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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from flowforge.ports.types import Principal

from .auth import PrincipalExtractor, StaticPrincipalExtractor


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


# Module-level singleton; reset via :func:`flowforge_fastapi.reset_state`
# (which only touches registry state — explicit hub.clear() if needed).
_hub = WorkflowEventsHub()


def get_events_hub() -> WorkflowEventsHub:
	"""Return the singleton :class:`WorkflowEventsHub`."""

	return _hub


def build_ws_router(
	*,
	principal_extractor: PrincipalExtractor | None = None,
	path: str = "/ws",
) -> APIRouter:
	"""Construct the WebSocket router.

	Behaviour:

	* The handshake calls *principal_extractor* over the same Request-
	  shape interface (FastAPI exposes ``websocket`` rather than
	  ``request``; we use the underlying scope to satisfy the
	  Protocol). When extraction raises, we close with policy violation.
	* Once connected, the client receives a small ``hello`` frame and
	  then every published envelope.
	"""

	extractor: PrincipalExtractor = principal_extractor or StaticPrincipalExtractor()
	router = APIRouter(tags=["flowforge-ws"])

	@router.websocket(path)
	async def ws_endpoint(websocket: WebSocket) -> None:
		# Build a faux request enough for the extractor: we expose
		# ``cookies``, ``headers``, ``method``. Many extractors only
		# need one of these.
		principal = await _extract_ws_principal(websocket, extractor)
		if principal is None:
			# Already closed inside helper.
			return

		await websocket.accept()
		hub = get_events_hub()
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


async def _extract_ws_principal(
	websocket: WebSocket,
	extractor: PrincipalExtractor,
) -> Principal | None:
	"""Adapt the WebSocket-side scope into something Request-shaped.

	Starlette's :class:`~starlette.requests.Request` asserts the scope
	type is ``http``. The WS scope is ``websocket``; we shallow-copy and
	flip ``type`` so cookie/header access works uniformly. The principal
	extractor only reads cookies/headers/method, so the swap is safe.

	Returns the principal or ``None`` after closing the socket.
	"""

	from starlette.requests import Request

	http_scope = dict(websocket.scope)
	http_scope["type"] = "http"
	http_scope.setdefault("method", "GET")
	request = Request(scope=http_scope)
	try:
		principal = await extractor(request)
	except Exception as exc:  # noqa: BLE001 — close on any auth failure
		logger.info("flowforge-fastapi: WS auth failed: %s", exc)
		# 4401 is the conventional close code for auth failure in WS.
		await websocket.close(code=4401)
		return None
	return principal


__all__ = [
	"WorkflowEventsHub",
	"build_ws_router",
	"get_events_hub",
]
