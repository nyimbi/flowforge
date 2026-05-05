"""Authentication, CSRF, and principal extraction helpers.

The adapter does not assume *how* a host authenticates a request. It
declares a small :class:`PrincipalExtractor` protocol — anything with an
``async __call__(request) -> Principal`` — and ships two defaults:

* :class:`StaticPrincipalExtractor` — for tests, demos, and CLI tools.
* :class:`CookiePrincipalExtractor` — reads a signed cookie containing a
  serialised principal. Suitable for the UMS host where the existing
  session cookie already carries user_id + roles.

CSRF is double-submit-cookie: the server sets a random token in a cookie
on first idempotent request; mutating endpoints require the same token
as ``X-CSRF-Token`` header.
"""

from __future__ import annotations

import hmac
import json
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from typing import Awaitable, Callable, Protocol, runtime_checkable

from fastapi import HTTPException, Request, Response, status

from flowforge.ports.types import Principal


csrf_cookie_name: str = "flowforge_csrf"
csrf_header_name: str = "X-CSRF-Token"


@runtime_checkable
class PrincipalExtractor(Protocol):
	"""Protocol for turning a Starlette/FastAPI request into a Principal.

	Implementations MUST be async and MUST raise
	:class:`fastapi.HTTPException` (401) when the request lacks a valid
	identity.
	"""

	async def __call__(self, request: Request) -> Principal:
		...


class StaticPrincipalExtractor:
	"""Always returns the same :class:`Principal`. Used by tests/demos."""

	def __init__(self, principal: Principal | None = None) -> None:
		self._principal = principal or Principal(
			user_id="system",
			roles=("system",),
			is_system=True,
		)

	async def __call__(self, request: Request) -> Principal:
		return self._principal


class CookiePrincipalExtractor:
	"""Reads a signed cookie and reconstructs a :class:`Principal`.

	Cookie payload format: ``base64url(json).base64url(hmac_sha256(secret, json))``.
	The cookie name defaults to ``flowforge_session``.

	This is a small, dependency-free helper — production hosts with a
	real session story should plug their own extractor in.
	"""

	def __init__(
		self,
		*,
		secret: str | bytes,
		cookie_name: str = "flowforge_session",
	) -> None:
		self._secret = secret.encode() if isinstance(secret, str) else secret
		self._cookie_name = cookie_name

	def issue(self, principal: Principal) -> str:
		"""Serialise *principal* into a signed cookie value."""

		payload = json.dumps(
			{
				"user_id": principal.user_id,
				"roles": list(principal.roles),
				"is_system": principal.is_system,
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
		try:
			body = urlsafe_b64decode(_pad(body_b64).encode())
			sig = urlsafe_b64decode(_pad(sig_b64).encode())
		except Exception as exc:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="malformed session cookie",
			) from exc
		expected = hmac.new(self._secret, body_b64.encode(), sha256).digest()
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
		return Principal(
			user_id=str(data.get("user_id", "")),
			roles=tuple(data.get("roles", ())),
			is_system=bool(data.get("is_system", False)),
		)


def _pad(s: str) -> str:
	return s + "=" * (-len(s) % 4)


def issue_csrf_token(response: Response, *, secure: bool = False) -> str:
	"""Generate + set the CSRF cookie on *response*; return the token.

	Hosts call this on the first idempotent response (e.g. a login or
	bootstrap endpoint). Subsequent mutating requests must echo the same
	value as ``X-CSRF-Token``.
	"""

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


__all__ = [
	"CookiePrincipalExtractor",
	"PrincipalExtractor",
	"PrincipalExtractorCallable",
	"StaticPrincipalExtractor",
	"csrf_cookie_name",
	"csrf_header_name",
	"csrf_protect",
	"issue_csrf_token",
]
