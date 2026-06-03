"""E-76 — JWT principal extractor for jtbd-hub.

Implements :class:`flowforge_jtbd_hub.rbac.PrincipalExtractor` using
:mod:`flowforge_signing_kms` as the sole verifier.  No embedded JWT
library is used (E-73 design constraint).

Token format
------------
A token is a base64url-encoded JSON payload prepended with a detached
HMAC-SHA256 signature produced by the :class:`~flowforge.ports.SigningPort`.
The wire format is::

    <base64url(signature)>.<base64url(payload_json)>

The payload JSON carries::

    {
        "user_id": "<str>",
        "roles": ["hub_admin", ...],
        "jti":   "<str>",   # unique token id for revocation
        "exp":   <int>,     # Unix timestamp — seconds since epoch
        "key_id": "<str>"   # signing key id for verify() dispatch
    }

Verification sequence in :meth:`JwtPrincipalExtractor.__call__`
---------------------------------------------------------------
1. Split the ``Authorization: Bearer <token>`` header.
2. Decode the two dot-separated segments.
3. Call ``signing.verify(payload_bytes, signature_bytes, key_id)`` on the
   ``SigningPort``.  Wrong key or tampered payload → return ``None``.
4. Decode the JSON payload.
5. Check ``exp`` against ``time.time()``.  Expired → return ``None``.
6. Check ``revocation.is_revoked(user_id, jti)``.  Revoked → return ``None``.
7. Map ``roles`` strings to :class:`~flowforge_jtbd_hub.rbac.Role` values.
   Unknown roles are silently dropped (forward-compat).
8. Return :class:`~flowforge_jtbd_hub.rbac.Principal`.

Lazy-init (F-6)
---------------
The :class:`JwtPrincipalExtractor` stores the :class:`SigningPort` reference
passed at construction time but never calls ``sign_payload`` / ``verify``
at import or construction.  The signer is exercised only when
:meth:`__call__` is invoked from a live request.

Async design
------------
``__call__`` is an ``async def`` method.  FastAPI introspects dependency
callables and correctly awaits async ones, so this works transparently in
the ``Depends(...)`` injection chain.  Tests call it with ``await``.
The :class:`~flowforge_jtbd_hub.rbac.PrincipalExtractor` Protocol specifies
``__call__(request) -> Principal | None``; the async variant is a strict
superset — any awaiting caller satisfies the protocol (Python's structural
typing checks arity and name, not async-ness of the return type).
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

from .rbac import Principal, Role
from .token_revocation import RevocationList


def _b64url_encode(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
	# Re-add stripped padding.
	padding = 4 - len(s) % 4
	if padding != 4:
		s += "=" * padding
	return base64.urlsafe_b64decode(s)


class JwtPrincipalExtractor:
	"""Extracts a :class:`~flowforge_jtbd_hub.rbac.Principal` from a
	``Authorization: Bearer <signed-token>`` header.

	:param signing: Any :class:`flowforge.ports.SigningPort` implementation.
	  Passed at construction; first used on the first incoming request (F-6).
	:param revocation: :class:`~flowforge_jtbd_hub.token_revocation.RevocationList`
	  used for jti-level revocation checks.  Defaults to a fresh empty list.
	"""

	def __init__(
		self,
		signing: Any,
		*,
		revocation: RevocationList | None = None,
	) -> None:
		self._signing = signing
		self._revocation: RevocationList = revocation if revocation is not None else RevocationList()

	# ------------------------------------------------------------------
	# PrincipalExtractor protocol — async callable
	# ------------------------------------------------------------------

	async def __call__(self, request: object) -> Principal | None:
		"""Extract and verify a Principal from *request*.

		Accepts any object with a ``.headers`` dict-like attribute (FastAPI
		``Request`` or the thin :class:`~flowforge_jtbd_hub.app._AuthHeaderRequest`
		shim).  Returns ``None`` for absent, malformed, expired, or revoked tokens.
		"""
		headers: Any = getattr(request, "headers", {})
		authorization: str | None = headers.get("Authorization") or headers.get("authorization")
		if not authorization:
			return None
		if not authorization.startswith("Bearer "):
			return None
		token = authorization[len("Bearer "):]
		return await self._averify_token(token)

	# ------------------------------------------------------------------
	# token issuance
	# ------------------------------------------------------------------

	async def aissue_token(
		self,
		user_id: str,
		roles: list[str],
		*,
		exp_seconds: int = 3600,
	) -> str:
		"""Sign and return a fresh token string.

		:param user_id: Identity to embed.
		:param roles: List of role strings (e.g. ``["hub_admin"]``).
		:param exp_seconds: Lifetime in seconds from now.  Defaults to 1 hour.
		:returns: Wire-format token ``<sig_b64url>.<payload_b64url>``.

		Emits metric ``flowforge_jwt_tokens_issued_total`` via the global
		metrics port when available.
		"""
		payload_dict: dict[str, Any] = {
			"user_id": user_id,
			"roles": roles,
			"jti": str(uuid.uuid4()),
			"exp": int(time.time()) + exp_seconds,
			"key_id": self._signing.current_key_id(),
		}
		payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode()
		sig = await self._signing.sign_payload(payload_bytes)
		token = _b64url_encode(sig) + "." + _b64url_encode(payload_bytes)
		try:
			from flowforge import config as _cfg
			_c = _cfg.current()
			if _c.metrics is not None:
				_c.metrics.emit("flowforge_jwt_tokens_issued_total", 1.0, {})
		except Exception:
			pass
		return token

	# keep synchronous alias for callers that cannot await
	def issue_token(
		self,
		user_id: str,
		roles: list[str],
		*,
		exp_seconds: int = 3600,
	) -> Any:
		"""Synchronous-friendly alias — returns a coroutine.

		Usage: ``token = await extractor.issue_token(...)`` from async context,
		or wrap with ``asyncio.run(...)`` in a sync context.
		"""
		return self.aissue_token(user_id, roles, exp_seconds=exp_seconds)

	# ------------------------------------------------------------------
	# internals
	# ------------------------------------------------------------------

	async def _averify_token(self, token: str) -> Principal | None:
		"""Core async token verification."""
		# Split wire format: <sig_b64url>.<payload_b64url>
		parts = token.split(".", 1)
		if len(parts) != 2:
			return None
		try:
			sig_bytes = _b64url_decode(parts[0])
			payload_bytes = _b64url_decode(parts[1])
		except Exception:
			return None

		# Decode payload to get key_id for verify() dispatch.
		try:
			payload: dict[str, Any] = json.loads(payload_bytes)
		except Exception:
			return None

		key_id: str | None = payload.get("key_id")
		if not key_id:
			return None

		# Verify signature — wrong key or tampered payload returns False
		# or raises UnknownKeyId; both cases → return None.
		try:
			ok = await self._signing.verify(payload_bytes, sig_bytes, key_id)
		except Exception:
			return None
		if not ok:
			return None

		# Expiry check.
		exp = payload.get("exp")
		if exp is None or time.time() > exp:
			return None

		user_id: str | None = payload.get("user_id")
		if not user_id:
			return None
		jti: str | None = payload.get("jti")
		if not jti:
			return None

		# Revocation check.
		if self._revocation.is_revoked(user_id, jti):
			return None

		# Map role strings — unknown roles silently dropped (forward-compat).
		raw_roles: list[str] = payload.get("roles") or []
		roles: list[Role] = []
		for r in raw_roles:
			try:
				roles.append(Role(r))
			except ValueError:
				pass

		return Principal(user_id=user_id, roles=tuple(roles))


def make_jwt_extractor(
	signing: Any,
	*,
	revocation: RevocationList | None = None,
) -> JwtPrincipalExtractor:
	"""Convenience factory for :class:`JwtPrincipalExtractor`.

	:param signing: Any ``SigningPort`` implementation.
	:param revocation: Optional :class:`RevocationList`; a fresh empty list
	  is created when omitted.
	:returns: A configured :class:`JwtPrincipalExtractor`.
	"""
	return JwtPrincipalExtractor(signing, revocation=revocation)


__all__ = [
	"JwtPrincipalExtractor",
	"make_jwt_extractor",
]
