"""MultiTenantGUC — tenant id resolved per-request via callable."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

from .single import _set_config

Resolver = Callable[[], str | Awaitable[str]]


class MultiTenantGUC:
	"""Resolve tenant id at call time. Same GUC binder as single-tenant.

	*resolver* may be sync or async; the binder normalises both.
	"""

	def __init__(self, resolver: Resolver) -> None:
		self._resolver = resolver
		self._elevated = False

	async def current_tenant(self) -> str:
		val = self._resolver()
		if hasattr(val, "__await__"):
			val = await val  # type: ignore[assignment]
		assert isinstance(val, str) and val, "resolver must return a non-empty tenant id"
		return val

	async def bind_session(self, session: Any, tenant_id: str) -> None:
		await _set_config(session, "app.tenant_id", tenant_id)
		await _set_config(session, "app.elevated", "true" if self._elevated else "false")

	@asynccontextmanager
	async def elevated_scope(self) -> AsyncIterator[None]:
		prior = self._elevated
		self._elevated = True
		try:
			yield
		finally:
			self._elevated = prior
