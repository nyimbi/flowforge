"""Authentication, CSRF, and principal extraction helpers.

The adapter does not assume *how* a host authenticates a request. It
declares two small protocols — :class:`PrincipalExtractor` (HTTP-side,
``async __call__(Request) -> Principal``) and :class:`WSPrincipalExtractor`
(WebSocket-side, ``async __call__(WebSocket) -> Principal``) — and
ships defaults:

* :class:`StaticPrincipalExtractor` — for tests, demos, and CLI tools.
* :class:`CookiePrincipalExtractor` — reads a signed cookie containing a
  serialised principal + ``iat``/``exp`` and rejects expired cookies.

CSRF is double-submit-cookie: the server sets a random token in a cookie
on first idempotent request; mutating endpoints require the same token
as ``X-CSRF-Token`` header.

E-41 hardening (audit-fix-plan §4.2, §4.3):

* **FA-01**.  ``CookiePrincipalExtractor.verify`` canonicalises base64
  padding before recomputing the HMAC so a re-padded body or signature
  still verifies (some intermediaries normalise `-+/=` cookie values).
* **FA-02**.  ``issue_csrf_token`` defaults ``secure=True``; passing
  ``secure=False`` raises :class:`ConfigError` unless the caller also
  passes ``dev_mode=True``.
* **FA-03**.  WS-side principal extraction takes a :class:`WebSocket`
  directly via :class:`WSPrincipalExtractor`; the legacy "spoof an HTTP
  scope" trampoline is gone.
* **FA-06**.  Cookie payload carries ``iat`` and ``exp``; verify
  rejects expired cookies.
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from typing import Awaitable, Callable, Protocol, runtime_checkable

from fastapi import HTTPException, Request, Response, WebSocket, status

from flowforge.ports.types import Principal


csrf_cookie_name: str = "flowforge_csrf"
csrf_header_name: str = "X-CSRF-Token"


class ConfigError(Exception):
	"""Raised on a configuration shape that is unsafe in production.

	E-41 / FA-02: ``issue_csrf_token(secure=False)`` outside of an explicit
	``dev_mode=True`` is a config error so insecure cookie shapes cannot
	silently slip into a TLS-terminated host.
	"""


@runtime_checkable
class PrincipalExtractor(Protocol):
	"""Protocol for turning a Starlette/FastAPI request into a Principal.

	Implementations MUST be async and MUST raise
	:class:`fastapi.HTTPException` (401) when the request lacks a valid
	identity.
	"""

	async def __call__(self, request: Request) -> Principal:
		...


@runtime_checkable
class WSPrincipalExtractor(Protocol):
	"""Protocol for turning a FastAPI :class:`WebSocket` into a Principal.

	E-41 / FA-03: WS-side auth must take the WebSocket directly so the
	scope's ``type`` is honest.  Pre-fix the framework mutated the WS
	scope to look like HTTP so a :class:`PrincipalExtractor` could be
	reused; that lied to any code that read ``scope['type']`` and is the
	kind of smell that survives until pen-test.

	Implementations MUST be async.  On auth failure they may either
	raise :class:`HTTPException` (the WS router translates to a 4401
	close) or close the socket themselves and raise.
	"""

	async def __call__(self, websocket: WebSocket) -> Principal:
		...


class StaticPrincipalExtractor:
	"""Always returns the same :class:`Principal`. Used by tests/demos.

	Satisfies both :class:`PrincipalExtractor` and
	:class:`WSPrincipalExtractor` because the principal is the same in
	either context.
	"""

	def __init__(self, principal: Principal | None = None) -> None:
		self._principal = principal or Principal(
			user_id="system",
			roles=("system",),
			is_system=True,
		)

	async def __call__(self, request: Request) -> Principal:
		# Type-annotated as ``Request`` to satisfy FastAPI dependency
		# introspection (which can't represent ``Request | WebSocket`` as a
		# pydantic field).  ``ws.py`` short-circuits the WebSocket path via
		# ``_HTTPOnlyAdapter`` or by passing the static instance directly
		# without going through FastAPI dep injection.
		return self._principal


class CookiePrincipalExtractor:
	"""Reads a signed cookie and reconstructs a :class:`Principal`.

	Cookie payload format: ``base64url(json).base64url(hmac_sha256(secret, json))``.
	The cookie name defaults to ``flowforge_session``.

	The JSON body carries ``user_id``, ``roles``, ``is_system``, plus the
	E-41 / FA-06 ``iat`` (issued-at, unix seconds) and ``exp`` (expiration,
	unix seconds) fields.  Verify rejects expired cookies with 401.
	"""

	def __init__(
		self,
		*,
		secret: str | bytes,
		cookie_name: str = "flowforge_session",
		ttl_seconds: int = 60 * 60 * 24,  # 24 h default
	) -> None:
		self._secret = secret.encode() if isinstance(secret, str) else secret
		self._cookie_name = cookie_name
		self._ttl = int(ttl_seconds)
		# Tests overload ``self._now`` to freeze time; production uses
		# ``time.time``.
		self._now: Callable[[], float] = time.time

	def issue(self, principal: Principal) -> str:
		"""Serialise *principal* into a signed cookie value with ``iat``/``exp``."""
		now = int(self._now())
		payload = json.dumps(
			{
				"user_id": principal.user_id,
				"roles": list(principal.roles),
				"is_system": principal.is_system,
				"iat": now,
				"exp": now + self._ttl,
			},
			sort_keys=True,
			separators=(",", ":"),
		).encode()
		body = urlsafe_b64encode(payload).rstrip(b"=")
		mac = hmac.new(self._secret, body, sha256).digest()
		sig = urlsafe_b64encode(mac).rstrip(b"=")
		return f"{body.decode()}.{sig.decode()}"

	async def __call__(self, request: Request) -> Principal:
		raw = request.cookies.get(self._cookie_name)
		if not raw or "." not in raw:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="missing or malformed session cookie",
			)
		body_b64, sig_b64 = raw.split(".", 1)

		# E-41 / FA-01: canonicalise padding before doing anything with the
		# cookie components.  The HMAC at issue time was computed over the
		# un-padded body bytes; if any intermediary re-pads, we still need
		# the same hash domain.
		body_b64_canon = body_b64.rstrip("=")
		sig_b64_canon = sig_b64.rstrip("=")

		try:
			body = urlsafe_b64decode(_pad(body_b64_canon).encode())
			sig = urlsafe_b64decode(_pad(sig_b64_canon).encode())
		except Exception as exc:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="malformed session cookie",
			) from exc
		expected = hmac.new(self._secret, body_b64_canon.encode(), sha256).digest()
		if not hmac.compare_digest(sig, expected):
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="invalid session signature",
			)
		try:
			data = json.loads(body)
		except json.JSONDecodeError as exc:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="malformed session payload",
			) from exc

		# E-41 / FA-06: enforce ``exp`` if present.  Cookies issued by
		# pre-FA-06 clients have no ``exp`` and remain valid (the field
		# is opt-in additive, not a breaking validation).
		exp = data.get("exp")
		if isinstance(exp, (int, float)):
			now = int(self._now())
			if now >= int(exp):
				raise HTTPException(
					status_code=status.HTTP_401_UNAUTHORIZED,
					detail="session cookie expired",
				)
		return Principal(
			user_id=str(data.get("user_id", "")),
			roles=tuple(data.get("roles", ())),
			is_system=bool(data.get("is_system", False)),
		)


def _pad(s: str) -> str:
	return s + "=" * (-len(s) % 4)


def issue_csrf_token(
	response: Response,
	*,
	secure: bool = True,
	dev_mode: bool = False,
) -> str:
	"""Generate + set the CSRF cookie on *response*; return the token.

	Hosts call this on the first idempotent response (e.g. a login or
	bootstrap endpoint). Subsequent mutating requests must echo the same
	value as ``X-CSRF-Token``.

	E-41 / FA-02: defaults ``secure=True``.  Passing ``secure=False``
	without an explicit ``dev_mode=True`` raises :class:`ConfigError` so
	insecure cookies cannot leak into a TLS-terminated host by default.
	"""
	if secure is False and not dev_mode:
		raise ConfigError(
			"issue_csrf_token: secure=False is only allowed when dev_mode=True. "
			"In production the CSRF cookie MUST carry the Secure attribute."
		)

	token = secrets.token_urlsafe(32)
	response.set_cookie(
		key=csrf_cookie_name,
		value=token,
		httponly=False,  # readable by client JS so it can mirror in header
		secure=secure,
		samesite="lax",
	)
	return token


async def csrf_protect(request: Request) -> None:
	"""FastAPI dependency: reject if cookie token != header token.

	Idempotent verbs (GET/HEAD/OPTIONS) are exempt.
	"""

	if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
		return
	cookie = request.cookies.get(csrf_cookie_name)
	header = request.headers.get(csrf_header_name)
	if not cookie or not header or not hmac.compare_digest(cookie, header):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="CSRF token missing or mismatched",
		)


# Convenience type aliases used by router builders.
PrincipalExtractorCallable = Callable[[Request], Awaitable[Principal]]
WSPrincipalExtractorCallable = Callable[[WebSocket], Awaitable[Principal]]


__all__ = [
	"ConfigError",
	"CookiePrincipalExtractor",
	"PrincipalExtractor",
	"PrincipalExtractorCallable",
	"StaticPrincipalExtractor",
	"WSPrincipalExtractor",
	"WSPrincipalExtractorCallable",
	"csrf_cookie_name",
	"csrf_header_name",
	"csrf_protect",
	"issue_csrf_token",
]
