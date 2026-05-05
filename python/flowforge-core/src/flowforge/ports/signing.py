"""SigningPort — payload signing for elevation log + outgoing webhooks."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SigningPort(Protocol):
	"""Cryptographic signing facade.

	Mandatory in production; the engine refuses to enter an elevated
	scope without a working SigningPort (see portability §7.2).
	"""

	async def sign_payload(self, payload: bytes) -> bytes:
		"""Return a detached signature for *payload* using the active key."""

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* under *key_id*."""

	def current_key_id(self) -> str:
		"""Return the active signing key id (deterministic, used in logs)."""
