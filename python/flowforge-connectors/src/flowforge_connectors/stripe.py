"""Stripe webhook signature verifier."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from .base import ConnectorBase, ConnectorResult


class StripeWebhookVerifier(ConnectorBase):
	"""Verify Stripe webhook signatures and parse events.

	Pass the raw request body and ``Stripe-Signature`` header to
	:meth:`verify_webhook`.  :meth:`execute` is a passthrough that returns
	the payload unchanged.
	"""

	connector_id = "stripe_webhook"
	_TOLERANCE_SECONDS = 300

	def __init__(self, webhook_secret: str) -> None:
		if not webhook_secret:
			raise ValueError("StripeWebhookVerifier requires webhook_secret")
		self._secret = webhook_secret

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		return ConnectorResult(ok=True, data=payload)

	async def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
		sig_header = headers.get("Stripe-Signature") or headers.get("stripe-signature", "")
		if not sig_header:
			return False
		parts = dict(part.split("=", 1) for part in sig_header.split(",") if "=" in part)
		timestamp = parts.get("t", "")
		v1_sig = parts.get("v1", "")
		if not timestamp or not v1_sig:
			return False
		try:
			ts = int(timestamp)
		except ValueError:
			return False
		if abs(time.time() - ts) > self._TOLERANCE_SECONDS:
			return False
		signed_payload = f"{timestamp}.".encode() + body
		expected = hmac.new(
			self._secret.encode(), signed_payload, hashlib.sha256
		).hexdigest()
		return hmac.compare_digest(expected, v1_sig)
