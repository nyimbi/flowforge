"""HubSpot CRM connector — create/update contacts and deals."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)
_HUBSPOT_API = "https://api.hubapi.com"


class HubSpotConnector(ConnectorBase):
	"""Create or update HubSpot contacts and deals via the v3 API.

	Supports operations: ``create_contact``, ``update_contact``,
	``create_deal``, ``update_deal``.
	"""

	connector_id = "hubspot"

	def __init__(self, api_key: str) -> None:
		if not api_key:
			raise ValueError("HubSpotConnector requires an api_key")
		self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		op = payload.get("op", "")
		properties = payload.get("properties", {})
		object_id = payload.get("id")

		try:
			async with httpx.AsyncClient(timeout=15.0) as client:
				if op == "create_contact":
					r = await client.post(
						f"{_HUBSPOT_API}/crm/v3/objects/contacts",
						json={"properties": properties},
						headers=self._headers,
					)
				elif op == "update_contact":
					r = await client.patch(
						f"{_HUBSPOT_API}/crm/v3/objects/contacts/{object_id}",
						json={"properties": properties},
						headers=self._headers,
					)
				elif op == "create_deal":
					r = await client.post(
						f"{_HUBSPOT_API}/crm/v3/objects/deals",
						json={"properties": properties},
						headers=self._headers,
					)
				elif op == "update_deal":
					r = await client.patch(
						f"{_HUBSPOT_API}/crm/v3/objects/deals/{object_id}",
						json={"properties": properties},
						headers=self._headers,
					)
				else:
					return ConnectorResult(ok=False, error=f"HubSpotConnector: unknown op {op!r}")

			if r.is_success:
				return ConnectorResult(ok=True, data=r.json(), status_code=r.status_code)
			return ConnectorResult(ok=False, error=f"HubSpot {r.status_code}: {r.text[:200]}", status_code=r.status_code)
		except Exception as exc:
			_log.error("HubSpotConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
