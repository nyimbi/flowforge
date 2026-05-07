"""Tenancy resolver tests."""

from __future__ import annotations

import asyncio

import pytest

from flowforge.ports import TenancyResolver
from flowforge_tenancy import MultiTenantGUC, NoTenancy, SingleTenantGUC

pytestmark = pytest.mark.asyncio


class StubSession:
	def __init__(self, in_tx: bool = True) -> None:
		self.calls: list[tuple[str, dict]] = []
		self._in_tx = in_tx

	def in_transaction(self) -> bool:
		return self._in_tx

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))


async def test_single_tenant_satisfies_protocol() -> None:
	r = SingleTenantGUC("t-1")
	assert isinstance(r, TenancyResolver)


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


async def test_no_tenancy_does_not_bind() -> None:
	r = NoTenancy()
	s = StubSession()
	await r.bind_session(s, "ignored")
	assert s.calls == []
	assert await r.current_tenant() == "default"


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
