"""Redis get/set/publish connector."""

from __future__ import annotations

import logging
from typing import Any

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class RedisConnector(ConnectorBase):
	"""Execute Redis operations (get, set, publish, lpush).

	Requires ``redis[asyncio]`` to be installed.
	"""

	connector_id = "redis"

	def __init__(self, url: str = "redis://localhost:6379/0") -> None:
		self._url = url

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		op = payload.get("op", "get")
		key = payload.get("key", "")
		value = payload.get("value")
		channel = payload.get("channel", "")

		try:
			import redis.asyncio as aioredis  # type: ignore[import]
			client = aioredis.from_url(self._url, decode_responses=True)
			try:
				if op == "get":
					result = await client.get(key)
					return ConnectorResult(ok=True, data={"value": result})
				elif op == "set":
					ttl = payload.get("ttl_seconds")
					await client.set(key, str(value), ex=ttl)
					return ConnectorResult(ok=True, data={"key": key})
				elif op == "publish":
					count = await client.publish(channel, str(value))
					return ConnectorResult(ok=True, data={"receivers": count})
				elif op == "lpush":
					length = await client.lpush(key, str(value))
					return ConnectorResult(ok=True, data={"list_length": length})
				else:
					return ConnectorResult(ok=False, error=f"RedisConnector: unknown op {op!r}")
			finally:
				await client.aclose()
		except ImportError:
			return ConnectorResult(ok=False, error="redis[asyncio] not installed")
		except Exception as exc:
			_log.error("RedisConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
