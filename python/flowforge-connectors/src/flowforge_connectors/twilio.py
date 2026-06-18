"""Twilio SMS connector."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)
_TWILIO_SMS_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"


class TwilioSMSConnector(ConnectorBase):
	"""Send SMS via the Twilio REST API."""

	connector_id = "twilio_sms"

	def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
		if not account_sid or not auth_token or not from_number:
			raise ValueError("TwilioSMSConnector requires account_sid, auth_token, from_number")
		self._sid = account_sid
		self._token = auth_token
		self._from = from_number

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		to = payload.get("to", "")
		body = payload.get("body", "")
		if not to or not body:
			return ConnectorResult(ok=False, error="Twilio: 'to' and 'body' required in payload")
		url = _TWILIO_SMS_URL.format(account_sid=self._sid)
		data = {"To": to, "From": self._from, "Body": body}
		try:
			async with httpx.AsyncClient(timeout=15.0) as client:
				r = await client.post(
					url,
					data=data,
					auth=(self._sid, self._token),
				)
			if r.is_success:
				j = r.json()
				return ConnectorResult(ok=True, data={"sid": j.get("sid", ""), "status": j.get("status", "")})
			return ConnectorResult(ok=False, error=f"Twilio {r.status_code}: {r.text[:200]}", status_code=r.status_code)
		except Exception as exc:
			_log.error("TwilioSMSConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
