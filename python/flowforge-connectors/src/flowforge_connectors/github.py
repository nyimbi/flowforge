"""GitHub webhook signature verifier (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .base import ConnectorBase, ConnectorResult


class GitHubWebhookVerifier(ConnectorBase):
	"""Verify GitHub webhook signatures (``X-Hub-Signature-256``)."""

	connector_id = "github_webhook"

	def __init__(self, secret: str) -> None:
		if not secret:
			raise ValueError("GitHubWebhookVerifier requires a secret")
		self._secret = secret.encode()

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		return ConnectorResult(ok=True, data=payload)

	async def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
		sig = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256", "")
		if not sig.startswith("sha256="):
			return False
		expected = "sha256=" + hmac.new(self._secret, body, hashlib.sha256).hexdigest()
		return hmac.compare_digest(expected, sig)
