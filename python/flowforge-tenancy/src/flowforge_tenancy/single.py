"""SingleTenantGUC — fixed tenant id, Postgres GUC binder."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class SingleTenantGUC:
	"""Bind a single, fixed tenant id onto every session.

	The session is expected to be a SQLAlchemy AsyncSession (or anything
	with ``execute(sql, params)``) — but the binder is duck-typed so a
	stub session in tests works too.
	"""

	def __init__(self, tenant_id: str) -> None:
		assert tenant_id, "tenant_id must be non-empty"
		self._tenant_id = tenant_id
		self._elevated = False

	async def current_tenant(self) -> str:
		return self._tenant_id

	async def bind_session(self, session: Any, tenant_id: str) -> None:
		"""Issue ``SELECT set_config('app.tenant_id', :tid, true)``.

		Tests pass a stub with an ``execute`` coroutine; production
		passes an AsyncSession.
		"""
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


async def _set_config(session: Any, key: str, value: str) -> None:
	# Accepts both SQLAlchemy text() and our test stub.
	statement = f"SELECT set_config('{key}', :v, true)"
	res = session.execute(statement, {"v": value})
	if hasattr(res, "__await__"):
		await res
