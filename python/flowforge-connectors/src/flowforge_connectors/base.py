"""Connector SDK base classes.

A connector bridges an external service (Stripe, GitHub, Slack, etc.) with
flowforge's outbox and notification ports.  Connectors are stateless;
all I/O state lives in the workflow instance context or the external service.

Every connector implements :meth:`execute` which receives a generic
``payload`` dict and returns a :class:`ConnectorResult`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConnectorResult:
	"""Return value of :meth:`ConnectorBase.execute`."""

	ok: bool
	data: dict[str, Any] = field(default_factory=dict)
	error: str | None = None
	status_code: int | None = None


class ConnectorBase(ABC):
	"""Abstract base class for all flowforge connectors.

	Subclasses implement :meth:`execute` and optionally :meth:`verify_webhook`
	for inbound webhook verification.
	"""

	#: Human-readable name, used in logs and audit events.
	connector_id: str = "unknown"

	@abstractmethod
	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		"""Execute the connector action described by *payload*.

		Implementations MUST NOT raise — wrap failures in a
		:class:`ConnectorResult` with ``ok=False``.
		"""

	async def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
		"""Verify an inbound webhook signature.

		Returns ``True`` if the signature is valid.  Default always returns
		``True`` (no verification).  Override for HMAC-signed webhooks.
		"""
		return True
