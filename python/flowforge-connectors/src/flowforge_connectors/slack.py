"""Slack Incoming Webhook connector."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class SlackConnector(ConnectorBase):
	"""Post a message to a Slack channel via Incoming Webhook URL."""

	connector_id = "slack"

	def __init__(self, webhook_url: str) -> None:
		if not webhook_url:
			raise ValueError("SlackConnector requires a webhook_url")
		self._url = webhook_url

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		text = payload.get("text", "")
		blocks = payload.get("blocks")
		body: dict[str, Any] = {"text": text}
		if blocks:
			body["blocks"] = blocks
		try:
			async with httpx.AsyncClient(timeout=10.0) as client:
				r = await client.post(self._url, json=body)
			if r.is_success:
				return ConnectorResult(ok=True, data={"response": r.text}, status_code=r.status_code)
			return ConnectorResult(ok=False, error=f"Slack {r.status_code}: {r.text}", status_code=r.status_code)
		except Exception as exc:
			_log.error("SlackConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
