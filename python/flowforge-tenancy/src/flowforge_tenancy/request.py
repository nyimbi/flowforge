"""Request-scoped tenant resolver callables.

These helpers are intentionally framework-light.  They accept a callable that
returns the current request-like object, so FastAPI/Starlette, test doubles, and
other ASGI surfaces can use them with ``MultiTenantGUC`` without this package
depending on a web framework.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit


RequestGetter = Callable[[], Any]

_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_JWT_ALGORITHMS: dict[str, Any] = {
	"HS256": hashlib.sha256,
	"HS384": hashlib.sha384,
	"HS512": hashlib.sha512,
}


class TenantResolutionError(ValueError):
	"""Raised when a request does not contain a valid tenant id."""


def _clean_tenant_id(value: Any, *, source: str) -> str:
	if not isinstance(value, str):
		raise TenantResolutionError(f"{source} tenant id must be a string")
	tenant_id = value.strip()
	if not tenant_id:
		raise TenantResolutionError(f"{source} tenant id is empty")
	if not _TENANT_ID_RE.fullmatch(tenant_id):
		raise TenantResolutionError(f"{source} tenant id contains unsupported characters")
	return tenant_id


def _headers_from_request(request: Any) -> Any:
	headers = getattr(request, "headers", None)
	if headers is None:
		if isinstance(request, Mapping):
			headers = request
		else:
			headers = {}
	return headers


def _header_value(headers: Any, name: str) -> str | None:
	if hasattr(headers, "get"):
		value = headers.get(name)
		if value is not None:
			return str(value)
		lower_name = name.lower()
		for key in (lower_name, name.upper(), name.title()):
			value = headers.get(key)
			if value is not None:
				return str(value)
	if isinstance(headers, Mapping):
		lower_name = name.lower()
		for key, value in headers.items():
			if str(key).lower() == lower_name:
				return str(value)
	return None


def _b64url_decode(value: str) -> bytes:
	padding = "=" * (-len(value) % 4)
	try:
		return base64.urlsafe_b64decode((value + padding).encode("ascii"))
	except (ValueError, TypeError) as exc:
		raise TenantResolutionError("jwt contains invalid base64url data") from exc


def _json_segment(value: str, *, segment: str) -> dict[str, Any]:
	try:
		decoded = json.loads(_b64url_decode(value))
	except json.JSONDecodeError as exc:
		raise TenantResolutionError(f"jwt {segment} is not valid JSON") from exc
	if not isinstance(decoded, dict):
		raise TenantResolutionError(f"jwt {segment} must be a JSON object")
	return decoded


def _split_bearer(value: str) -> str:
	parts = value.strip().split(None, 1)
	if len(parts) == 2 and parts[0].lower() == "bearer":
		return parts[1].strip()
	return value.strip()


class HeaderTenantResolver:
	"""Resolve the tenant id from a request header.

	The default header is ``X-Tenant-ID``.  Dictionary-like and Starlette-style
	headers are both supported.
	"""

	def __init__(
		self,
		request_getter: RequestGetter,
		*,
		header_name: str = "X-Tenant-ID",
		required: bool = True,
		default: str | None = None,
	) -> None:
		self._request_getter = request_getter
		self._header_name = header_name
		self._required = required
		self._default = default

	def __call__(self) -> str:
		headers = _headers_from_request(self._request_getter())
		value = _header_value(headers, self._header_name)
		if value is None:
			if self._default is not None:
				return _clean_tenant_id(self._default, source="default")
			if self._required:
				raise TenantResolutionError(f"missing tenant header {self._header_name!r}")
			raise TenantResolutionError("tenant header is not configured")
		return _clean_tenant_id(value, source=self._header_name)


class JwtClaimTenantResolver:
	"""Resolve the tenant id from a JWT claim in a bearer token.

	HS256/HS384/HS512 signatures are verified with ``secret`` by default.  To
	decode unsigned or externally-verified tokens, pass ``verify_signature=False``
	explicitly; insecure decoding is never the implicit default.
	"""

	def __init__(
		self,
		request_getter: RequestGetter,
		*,
		claim_name: str = "tenant_id",
		header_name: str = "Authorization",
		secret: str | bytes | None = None,
		algorithms: Sequence[str] = ("HS256",),
		verify_signature: bool = True,
		leeway_seconds: int = 0,
	) -> None:
		self._request_getter = request_getter
		self._claim_name = claim_name
		self._header_name = header_name
		self._secret = secret.encode() if isinstance(secret, str) else secret
		self._algorithms = tuple(algorithms)
		self._verify_signature = verify_signature
		self._leeway_seconds = leeway_seconds

	def __call__(self) -> str:
		headers = _headers_from_request(self._request_getter())
		raw_header = _header_value(headers, self._header_name)
		if raw_header is None:
			raise TenantResolutionError(f"missing jwt header {self._header_name!r}")
		token = _split_bearer(raw_header)
		parts = token.split(".")
		if len(parts) != 3:
			raise TenantResolutionError("jwt must contain header, payload, and signature")

		header = _json_segment(parts[0], segment="header")
		payload = _json_segment(parts[1], segment="payload")
		alg = header.get("alg")
		if self._verify_signature:
			self._verify(parts, alg)
		self._verify_time_claims(payload)
		return _clean_tenant_id(payload.get(self._claim_name), source=f"jwt claim {self._claim_name!r}")

	def _verify(self, parts: list[str], alg: Any) -> None:
		if not self._secret:
			raise TenantResolutionError("jwt signature verification requires a secret")
		if alg not in self._algorithms or alg not in _JWT_ALGORITHMS:
			raise TenantResolutionError(f"jwt alg {alg!r} is not allowed")
		signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
		expected = hmac.new(self._secret, signing_input, _JWT_ALGORITHMS[alg]).digest()
		actual = _b64url_decode(parts[2])
		if not hmac.compare_digest(actual, expected):
			raise TenantResolutionError("jwt signature verification failed")

	def _verify_time_claims(self, payload: dict[str, Any]) -> None:
		now = time.time()
		leeway = self._leeway_seconds
		exp = payload.get("exp")
		if exp is not None and float(exp) + leeway < now:
			raise TenantResolutionError("jwt has expired")
		nbf = payload.get("nbf")
		if nbf is not None and float(nbf) - leeway > now:
			raise TenantResolutionError("jwt is not yet valid")


class SubdomainTenantResolver:
	"""Resolve the tenant id from the request host subdomain."""

	def __init__(
		self,
		request_getter: RequestGetter,
		*,
		base_domain: str | None = None,
		ignore_labels: set[str] | frozenset[str] | None = None,
	) -> None:
		self._request_getter = request_getter
		self._base_domain = base_domain.strip(".").lower() if base_domain else None
		self._ignore_labels = frozenset(ignore_labels or {"www"})

	def __call__(self) -> str:
		request = self._request_getter()
		host = self._host_from_request(request)
		tenant_label = self._tenant_label(host)
		return _clean_tenant_id(tenant_label, source="subdomain")

	def _host_from_request(self, request: Any) -> str:
		url = getattr(request, "url", None)
		hostname = getattr(url, "hostname", None)
		if hostname:
			return str(hostname).strip(".").lower()
		headers = _headers_from_request(request)
		raw_host = _header_value(headers, "Host")
		if raw_host is None:
			raise TenantResolutionError("missing host header")
		parsed = urlsplit(f"//{raw_host}")
		if parsed.hostname is None:
			raise TenantResolutionError("host header does not contain a hostname")
		return parsed.hostname.strip(".").lower()

	def _tenant_label(self, host: str) -> str:
		if self._base_domain is not None:
			suffix = f".{self._base_domain}"
			if not host.endswith(suffix):
				raise TenantResolutionError(f"host {host!r} is outside base domain {self._base_domain!r}")
			remainder = host[: -len(suffix)]
			if "." in remainder:
				raise TenantResolutionError("host contains multiple subdomain labels")
			label = remainder
		else:
			label = host.split(".", 1)[0]
		if label in self._ignore_labels:
			raise TenantResolutionError(f"ignored subdomain label {label!r} is not a tenant")
		return label
