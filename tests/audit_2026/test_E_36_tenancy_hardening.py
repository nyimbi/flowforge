"""E-36 — Tenancy SQL hardening regression tests (T-01, T-02, T-03).

Audit findings (audit-fix-plan.md §4.1, §7 E-36):
- T-01 (P0): SQL injection in ``_set_config``. Validate GUC name via
  ``^[a-zA-Z_][a-zA-Z_0-9.]*$``; bind both name and value as parameters.
- T-02 (P2): ``_elevated`` is a per-instance ``ContextVar`` — concurrent
  ``elevated_scope()`` calls in async tasks observe their own scope only.
- T-03 (P3): ``bind_session`` asserts ``session.in_transaction()``; raises
  if outside tx.

These tests duplicate the per-package suite under
``framework/python/flowforge-tenancy/tests/test_resolvers.py`` so the
audit-2026 ratchet job can run a single ``pytest framework/tests/audit_2026``
target without having to traverse every workspace package.
"""

from __future__ import annotations

import asyncio
import re

import pytest


pytestmark = pytest.mark.asyncio


class _StubSession:
	def __init__(self, in_tx: bool = True) -> None:
		self.calls: list[tuple[str, dict]] = []
		self._in_tx = in_tx

	def in_transaction(self) -> bool:
		return self._in_tx

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))


# ---------------------------------------------------------------------------
# T-01 — SQL injection blocked, bind-param SQL constant
# ---------------------------------------------------------------------------


async def test_T_01_set_config_bind_param_no_string_interp() -> None:
	from flowforge_tenancy.single import _GUC_KEY_RE, _SET_CONFIG_SQL, _set_config

	# Audit-mandated regex pattern (audit-fix-plan.md §7 E-36).
	assert _GUC_KEY_RE.pattern == r"^[a-zA-Z_][a-zA-Z_0-9.]*$"
	# SQL must be a constant template — both name and value bound as params.
	assert _SET_CONFIG_SQL == "SELECT set_config(:k, :v, true)"
	# Sanity: no f-string-style placeholder in the template.
	assert "'" not in _SET_CONFIG_SQL or _SET_CONFIG_SQL.count("'") == 0
	assert re.search(r"\{[^}]*\}", _SET_CONFIG_SQL) is None

	# Malicious GUC names → ValueError, no SQL emitted.
	for bogus in (
		"x'); DROP TABLE--",
		"'; DROP TABLE foo; --",
		"app id",  # space
		"app;id",  # semicolon
		"1abc",  # leading digit
		"app--id",  # SQL comment marker
		"",  # empty
		"‮app",  # unicode RTL override
	):
		s = _StubSession()
		with pytest.raises(ValueError):
			await _set_config(s, bogus, "v")
		assert s.calls == [], f"malicious key {bogus!r} reached the session"

	# Non-string GUC name → ValueError.
	s = _StubSession()
	with pytest.raises(ValueError):
		await _set_config(s, 42, "v")  # type: ignore[arg-type]
	assert s.calls == []

	# Valid path emits the constant SQL with both params bound.
	s = _StubSession()
	await _set_config(s, "app.tenant_id", "tenant-A")
	sql, params = s.calls[-1]
	assert sql == "SELECT set_config(:k, :v, true)"
	assert params == {"k": "app.tenant_id", "v": "tenant-A"}


# ---------------------------------------------------------------------------
# T-02 — ContextVar elevation isolation under concurrency
# ---------------------------------------------------------------------------


async def test_T_02_elevation_contextvar_single_tenant() -> None:
	"""100 concurrent elevated_scope calls observe their own scope only."""
	from flowforge_tenancy import SingleTenantGUC

	r = SingleTenantGUC("tenant-A")
	results: list[tuple[int, bool, str]] = []

	async def worker(idx: int) -> None:
		should_elevate = idx % 2 == 0
		if should_elevate:
			async with r.elevated_scope():
				await asyncio.sleep(0)
				s = _StubSession()
				await r.bind_session(s, "tenant-A")
				elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
				results.append((idx, should_elevate, elev[-1][1]["v"]))
		else:
			await asyncio.sleep(0)
			s = _StubSession()
			await r.bind_session(s, "tenant-A")
			elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
			results.append((idx, should_elevate, elev[-1][1]["v"]))

	await asyncio.gather(*(worker(i) for i in range(100)))

	for idx, should_elevate, observed in results:
		expected = "true" if should_elevate else "false"
		assert observed == expected, (
			f"task {idx}: elevation leaked across ContextVar (got {observed}, want {expected})"
		)
	assert len(results) == 100


async def test_T_02_elevation_contextvar_multi_tenant() -> None:
	from flowforge_tenancy import MultiTenantGUC

	r = MultiTenantGUC(resolver=lambda: "tenant-A")
	leaked: list[str] = []

	async def elevator() -> None:
		async with r.elevated_scope():
			await asyncio.sleep(0)
			s = _StubSession()
			await r.bind_session(s, "tenant-A")
			elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
			leaked.append(elev[-1][1]["v"])

	async def observer() -> None:
		await asyncio.sleep(0)
		s = _StubSession()
		await r.bind_session(s, "tenant-A")
		elev = [c for c in s.calls if c[1].get("k") == "app.elevated"]
		leaked.append(elev[-1][1]["v"])

	await asyncio.gather(elevator(), observer(), elevator(), observer())
	assert leaked.count("true") == 2
	assert leaked.count("false") == 2


# ---------------------------------------------------------------------------
# T-03 — bind_session asserts session.in_transaction()
# ---------------------------------------------------------------------------


async def test_T_03_in_transaction_assert_single_tenant() -> None:
	from flowforge_tenancy import SingleTenantGUC

	r = SingleTenantGUC("tenant-A")
	s = _StubSession(in_tx=False)
	with pytest.raises(AssertionError):
		await r.bind_session(s, "tenant-A")
	assert s.calls == [], "bind_session must short-circuit before SQL when not in tx"


async def test_T_03_in_transaction_assert_multi_tenant() -> None:
	from flowforge_tenancy import MultiTenantGUC

	r = MultiTenantGUC(resolver=lambda: "tenant-A")
	s = _StubSession(in_tx=False)
	with pytest.raises(AssertionError):
		await r.bind_session(s, "tenant-A")
	assert s.calls == []
