"""Generic outbound HTTP webhook connector."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class HTTPWebhookConnector(ConnectorBase):
	"""Send a JSON POST to a configurable URL.

	Args:
		url: Target URL.
		headers: Extra headers to include (e.g. Authorization).
		timeout: Request timeout in seconds.
	"""

	connector_id = "http_webhook"

	def __init__(
		self,
		url: str,
		*,
		headers: dict[str, str] | None = None,
		timeout: float = 30.0,
	) -> None:
		if not url:
			raise ValueError("HTTPWebhookConnector requires a URL")
		self._url = url
		self._headers = headers or {}
		self._timeout = timeout

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		try:
			async with httpx.AsyncClient(timeout=self._timeout) as client:
				r = await client.post(self._url, json=payload, headers=self._headers)
			if r.is_success:
				try:
					data = r.json()
				except Exception:
					data = {"body": r.text}
				return ConnectorResult(ok=True, data=data, status_code=r.status_code)
			return ConnectorResult(
				ok=False,
				error=f"HTTP {r.status_code}: {r.text[:200]}",
				status_code=r.status_code,
			)
		except Exception as exc:
			_log.error("HTTPWebhookConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
