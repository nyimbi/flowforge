"""Tenancy resolver tests."""

from __future__ import annotations

import pytest

from flowforge.ports import TenancyResolver
from flowforge_tenancy import MultiTenantGUC, NoTenancy, SingleTenantGUC

pytestmark = pytest.mark.asyncio


class StubSession:
	def __init__(self) -> None:
		self.calls: list[tuple[str, dict]] = []

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))


async def test_single_tenant_satisfies_protocol() -> None:
	r = SingleTenantGUC("t-1")
	assert isinstance(r, TenancyResolver)


async def test_single_tenant_binds_guc() -> None:
	r = SingleTenantGUC("t-1")
	s = StubSession()
	await r.bind_session(s, "t-1")
	keys = [c[0] for c in s.calls]
	assert any("app.tenant_id" in k for k in keys)
	assert any("app.elevated" in k for k in keys)


async def test_single_elevated_scope_toggles() -> None:
	r = SingleTenantGUC("t-1")
	s = StubSession()
	async with r.elevated_scope():
		await r.bind_session(s, "t-1")
		# inside scope: app.elevated=true
		elev_calls = [c for c in s.calls if "app.elevated" in c[0]]
		assert elev_calls[-1][1]["v"] == "true"

	s2 = StubSession()
	await r.bind_session(s2, "t-1")
	elev_calls = [c for c in s2.calls if "app.elevated" in c[0]]
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


async def test_no_tenancy_does_not_bind() -> None:
	r = NoTenancy()
	s = StubSession()
	await r.bind_session(s, "ignored")
	assert s.calls == []
	assert await r.current_tenant() == "default"
