"""Tenancy resolver tests."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import pytest

from flowforge.ports import TenancyResolver
from flowforge_tenancy import (
	HeaderTenantResolver,
	JwtClaimTenantResolver,
	MultiTenantGUC,
	NoTenancy,
	SingleTenantGUC,
	SubdomainTenantResolver,
	TenantResolutionError,
)

pytestmark = pytest.mark.asyncio


class StubSession:
	def __init__(self, in_tx: bool = True) -> None:
		self.calls: list[tuple[str, dict]] = []
		self._in_tx = in_tx

	def in_transaction(self) -> bool:
		return self._in_tx

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))


class AsyncExecuteSession:
	def __init__(self) -> None:
		self.calls: list[tuple[str, dict]] = []

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))

		async def _complete() -> None:
			return None

		return _complete()


class DuckTypedSession:
	def __init__(self) -> None:
		self.calls: list[tuple[str, dict]] = []

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))


@dataclass
class RequestStub:
	headers: dict[str, str]


def _b64url(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _jwt(payload: dict[str, Any], *, secret: str = "secret", alg: str = "HS256") -> str:
	header = {"typ": "JWT", "alg": alg}
	header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
	payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
	signing_input = f"{header_b64}.{payload_b64}".encode()
	signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
	return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


async def test_single_tenant_satisfies_protocol() -> None:
	r = SingleTenantGUC("t-1")
	assert isinstance(r, TenancyResolver)
	assert await r.current_tenant() == "t-1"


async def test_single_tenant_binds_guc() -> None:
	r = SingleTenantGUC("t-1")
	s = StubSession()
	await r.bind_session(s, "t-1")
	# Post-E-36: GUC name is a bound parameter (`:k`), not spliced into SQL.
	bound_keys = [c[1].get("k") for c in s.calls]
	assert "app.tenant_id" in bound_keys
	assert "app.elevated" in bound_keys


async def test_single_elevated_scope_toggles() -> None:
	r = SingleTenantGUC("t-1")
	s = StubSession()
	async with r.elevated_scope():
		await r.bind_session(s, "t-1")
		# inside scope: app.elevated=true
		elev_calls = [c for c in s.calls if c[1].get("k") == "app.elevated"]
		assert elev_calls[-1][1]["v"] == "true"

	s2 = StubSession()
	await r.bind_session(s2, "t-1")
	elev_calls = [c for c in s2.calls if c[1].get("k") == "app.elevated"]
	assert elev_calls[-1][1]["v"] == "false"


async def test_multi_tenant_resolves_per_call() -> None:
	current = {"t": "t-A"}
	r = MultiTenantGUC(resolver=lambda: current["t"])
	assert await r.current_tenant() == "t-A"
	current["t"] = "t-B"
	assert await r.current_tenant() == "t-B"


async def test_multi_tenant_supports_async_resolver() -> None:
	async def aresolver() -> str:
		return "t-async"

	r = MultiTenantGUC(resolver=aresolver)
	assert await r.current_tenant() == "t-async"


async def test_header_tenant_resolver_reads_x_tenant_id() -> None:
	request = RequestStub(headers={"X-Tenant-ID": " tenant-a "})
	r = MultiTenantGUC(resolver=HeaderTenantResolver(lambda: request))
	assert await r.current_tenant() == "tenant-a"


async def test_header_tenant_resolver_rejects_missing_and_unsafe_values() -> None:
	with pytest.raises(TenantResolutionError, match="missing tenant header"):
		HeaderTenantResolver(lambda: RequestStub(headers={}))()

	with pytest.raises(TenantResolutionError, match="unsupported characters"):
		HeaderTenantResolver(lambda: RequestStub(headers={"x-tenant-id": "../../tenant"}))()


async def test_jwt_claim_tenant_resolver_verifies_hmac_signature() -> None:
	token = _jwt({"tenant_id": "tenant-jwt", "exp": time.time() + 60}, secret="s3cr3t")
	request = RequestStub(headers={"Authorization": f"Bearer {token}"})
	r = MultiTenantGUC(resolver=JwtClaimTenantResolver(lambda: request, secret="s3cr3t"))
	assert await r.current_tenant() == "tenant-jwt"


async def test_jwt_claim_tenant_resolver_detects_tampering() -> None:
	token = _jwt({"tenant_id": "tenant-a"}, secret="s3cr3t")
	header, payload, signature = token.split(".")
	tampered_payload = _b64url(json.dumps({"tenant_id": "tenant-b"}, separators=(",", ":")).encode())
	request = RequestStub(headers={"Authorization": f"Bearer {header}.{tampered_payload}.{signature}"})

	with pytest.raises(TenantResolutionError, match="signature verification failed"):
		JwtClaimTenantResolver(lambda: request, secret="s3cr3t")()


async def test_jwt_claim_tenant_resolver_requires_secret_by_default() -> None:
	token = _jwt({"tenant_id": "tenant-a"}, secret="s3cr3t")
	request = RequestStub(headers={"Authorization": f"Bearer {token}"})

	with pytest.raises(TenantResolutionError, match="requires a secret"):
		JwtClaimTenantResolver(lambda: request)()


async def test_jwt_claim_tenant_resolver_allows_explicit_unverified_decode() -> None:
	token = _jwt({"tenant_id": "tenant-unverified"}, secret="unused")
	request = RequestStub(headers={"Authorization": f"Bearer {token}"})
	resolver = JwtClaimTenantResolver(lambda: request, verify_signature=False)
	assert resolver() == "tenant-unverified"


async def test_subdomain_tenant_resolver_reads_host_label() -> None:
	request = RequestStub(headers={"Host": "tenant-42.example.com:8443"})
	r = MultiTenantGUC(resolver=SubdomainTenantResolver(lambda: request, base_domain="example.com"))
	assert await r.current_tenant() == "tenant-42"


async def test_subdomain_tenant_resolver_rejects_ambiguous_hosts() -> None:
	resolver = SubdomainTenantResolver(
		lambda: RequestStub(headers={"Host": "api.tenant.example.com"}),
		base_domain="example.com",
	)
	with pytest.raises(TenantResolutionError, match="multiple subdomain labels"):
		resolver()

	with pytest.raises(TenantResolutionError, match="outside base domain"):
		SubdomainTenantResolver(
			lambda: RequestStub(headers={"Host": "tenant.other.test"}),
			base_domain="example.com",
		)()


async def test_no_tenancy_does_not_bind() -> None:
	r = NoTenancy()
	s = StubSession()
	await r.bind_session(s, "ignored")
	assert s.calls == []
	assert await r.current_tenant() == "default"


async def test_no_tenancy_elevated_scope_is_noop() -> None:
	r = NoTenancy("public")
	async with r.elevated_scope():
		assert await r.current_tenant() == "public"


async def test_single_tenant_accepts_duck_typed_session_without_tx_probe() -> None:
	r = SingleTenantGUC("t-1")
	s = DuckTypedSession()
	await r.bind_session(s, "t-1")
	assert [c[1]["k"] for c in s.calls] == ["app.tenant_id", "app.elevated"]


async def test_set_config_awaits_async_execute_result() -> None:
	from flowforge_tenancy.single import _set_config

	s = AsyncExecuteSession()
	await _set_config(s, "app.tenant_id", "t-async")
	assert s.calls == [
		("SELECT set_config(:k, :v, true)", {"k": "app.tenant_id", "v": "t-async"})
	]


# ---------------------------------------------------------------------------
# E-36 acceptance tests (T-01, T-02, T-03 per audit-fix-plan.md §7)
# ---------------------------------------------------------------------------


async def test_T_01_set_config_bind_param() -> None:
	"""T-01 (P0): SQL injection in `_set_config` is blocked.

	- Malicious GUC key raises ``ValueError`` (regex validation).
	- Valid path emits SQL with ``:k`` bound parameter — no f-string interpolation.
	"""
	from flowforge_tenancy.single import _GUC_KEY_RE, _set_config

	# Sanity: regex is the audit-mandated pattern.
	assert _GUC_KEY_RE.pattern == r"^[a-zA-Z_][a-zA-Z_0-9.]*$"

	# Malicious key — must raise before touching the session.
	bad = StubSession()
	with pytest.raises(ValueError):
		await _set_config(bad, "x'); DROP TABLE--", "v")
	assert bad.calls == [], "session must not see malicious key"

	# Other obviously-bad keys.
	for bogus in ("'; DROP--", "1abc", "app id", "app;id", "", "app--id"):
		s = StubSession()
		with pytest.raises(ValueError):
			await _set_config(s, bogus, "v")

	# Valid key — SQL log shows ``:k`` (and ``:v``); no f-string interp.
	good = StubSession()
	await _set_config(good, "app.tenant_id", "t-1")
	sql, params = good.calls[-1]
	assert ":k" in sql
	assert ":v" in sql
	# Must NOT splice the key into the SQL string.
	assert "app.tenant_id" not in sql
	assert "set_config('" not in sql
	assert params == {"k": "app.tenant_id", "v": "t-1"}


async def test_T_02_elevation_contextvar() -> None:
	"""T-02 (P2): elevation flag is task-isolated via ContextVar.

	100 concurrent ``elevated_scope()`` callers each observe their own scope
	regardless of interleaving with non-elevated callers.
	"""
	r = SingleTenantGUC("t-1")
	results: list[tuple[int, bool, str]] = []

	async def worker(idx: int) -> None:
		should_elevate = idx % 2 == 0
		if should_elevate:
			async with r.elevated_scope():
				# yield so siblings interleave and can clobber a non-isolated flag
				await asyncio.sleep(0)
				s = StubSession()
				await r.bind_session(s, "t-1")
				elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
				results.append((idx, should_elevate, elev[-1][1]["v"]))
		else:
			await asyncio.sleep(0)
			s = StubSession()
			await r.bind_session(s, "t-1")
			elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
			results.append((idx, should_elevate, elev[-1][1]["v"]))

	await asyncio.gather(*(worker(i) for i in range(100)))

	# Every worker sees its own scope.
	for idx, should_elevate, observed in results:
		expected = "true" if should_elevate else "false"
		assert observed == expected, (
			f"worker {idx} expected {expected} got {observed} — elevation leaked across tasks"
		)
	assert sum(1 for _, e, _ in results if e) == 50
	assert len(results) == 100


async def test_T_02_elevation_contextvar_multi() -> None:
	"""T-02 also applies to MultiTenantGUC."""
	r = MultiTenantGUC(resolver=lambda: "t-1")
	leaked: list[str] = []

	async def elevator() -> None:
		async with r.elevated_scope():
			await asyncio.sleep(0)
			s = StubSession()
			await r.bind_session(s, "t-1")
			elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
			leaked.append(elev[-1][1]["v"])

	async def observer() -> None:
		await asyncio.sleep(0)
		s = StubSession()
		await r.bind_session(s, "t-1")
		elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
		leaked.append(elev[-1][1]["v"])

	await asyncio.gather(elevator(), observer(), elevator(), observer())
	# elevators observe true, observers observe false — no leakage.
	assert leaked.count("true") == 2
	assert leaked.count("false") == 2


async def test_T_03_in_transaction_assert() -> None:
	"""T-03 (P3): ``bind_session`` outside a transaction raises."""
	r = SingleTenantGUC("t-1")
	s = StubSession(in_tx=False)
	with pytest.raises(AssertionError):
		await r.bind_session(s, "t-1")
	assert s.calls == [], "must not emit SQL when not in transaction"


async def test_T_03_multi_tenant_in_transaction_assert() -> None:
	"""T-03 also applies to MultiTenantGUC."""
	r = MultiTenantGUC(resolver=lambda: "t-1")
	s = StubSession(in_tx=False)
	with pytest.raises(AssertionError):
		await r.bind_session(s, "t-1")
	assert s.calls == []
