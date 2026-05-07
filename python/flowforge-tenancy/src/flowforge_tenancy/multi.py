"""MultiTenantGUC — tenant id resolved per-request via callable.

Mirrors the E-36 hardenings of :mod:`flowforge_tenancy.single`:

- Same bind-param GUC helper (T-01).
- Per-instance ``ContextVar`` for elevation so concurrent async tasks
  each see their own scope (T-02).
- ``bind_session`` asserts the session is inside a transaction (T-03).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Awaitable, Callable

from .single import _assert_in_transaction, _set_config

Resolver = Callable[[], str | Awaitable[str]]


class MultiTenantGUC:
	"""Resolve tenant id at call time. Same GUC binder as single-tenant.

	*resolver* may be sync or async; the binder normalises both.
	"""

	def __init__(self, resolver: Resolver) -> None:
		self._resolver = resolver
		self._elevated: ContextVar[bool] = ContextVar(
			f"flowforge_tenancy_elevated_multi_{id(self)}", default=False
		)

	async def current_tenant(self) -> str:
		val = self._resolver()
		if hasattr(val, "__await__"):
			val = await val  # type: ignore[assignment]
		assert isinstance(val, str) and val, "resolver must return a non-empty tenant id"
		return val

	async def bind_session(self, session: Any, tenant_id: str) -> None:
		_assert_in_transaction(session)
		await _set_config(session, "app.tenant_id", tenant_id)
		await _set_config(
			session, "app.elevated", "true" if self._elevated.get() else "false"
		)

	@asynccontextmanager
	async def elevated_scope(self) -> AsyncIterator[None]:
		token = self._elevated.set(True)
		try:
			yield
		finally:
			self._elevated.reset(token)
