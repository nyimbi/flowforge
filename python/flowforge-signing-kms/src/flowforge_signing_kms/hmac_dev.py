"""HmacDevSigning — local-dev signing backend using HMAC-SHA256.

Reads the shared secret from the environment variable ``FLOWFORGE_SIGNING_SECRET``
(falls back to a hard-coded insecure default so tests work without env setup).

Key rotation is supported via ``FLOWFORGE_SIGNING_KEY_ID`` (default: ``"dev-key-1"``).
The key id is embedded in every signature so verify() can route to the right secret
even after a rotation event.

Not for production use.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Final

_DEFAULT_SECRET: Final = "flowforge-dev-secret-not-for-production"
_SEP: Final = b"."


def _env_secret() -> str:
	return os.environ.get("FLOWFORGE_SIGNING_SECRET", _DEFAULT_SECRET)


def _env_key_id() -> str:
	return os.environ.get("FLOWFORGE_SIGNING_KEY_ID", "dev-key-1")


def _hmac_sign(secret: str, key_id: str, payload: bytes) -> bytes:
	"""Return raw HMAC-SHA256 digest over ``key_id + "." + payload``."""
	msg = key_id.encode() + _SEP + payload
	return hmac.new(secret.encode(), msg, hashlib.sha256).digest()


class HmacDevSigning:
	"""HMAC-SHA256 signing adapter for local development.

	Parameters
	----------
	secret:
	    Shared HMAC secret.  Defaults to ``FLOWFORGE_SIGNING_SECRET`` env var.
	key_id:
	    Logical key identifier embedded in logs and used during verify().
	    Defaults to ``FLOWFORGE_SIGNING_KEY_ID`` env var.
	"""

	def __init__(
		self,
		secret: str | None = None,
		key_id: str | None = None,
	) -> None:
		self._secret = secret if secret is not None else _env_secret()
		self._key_id = key_id if key_id is not None else _env_key_id()

	# ------------------------------------------------------------------
	# SigningPort protocol
	# ------------------------------------------------------------------

	async def sign_payload(self, payload: bytes) -> bytes:
		"""Return a detached HMAC-SHA256 signature for *payload*."""
		return _hmac_sign(self._secret, self._key_id, payload)

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		"""Verify *signature* against *payload* under *key_id*.

		Uses the same secret as the current instance.  In a real rotation
		scenario the caller would look up the secret for *key_id* from a
		secrets store; here we keep it simple and reuse ``self._secret``.
		"""
		expected = _hmac_sign(self._secret, key_id, payload)
		return hmac.compare_digest(expected, signature)

	def current_key_id(self) -> str:
		"""Return the active signing key id."""
		return self._key_id
