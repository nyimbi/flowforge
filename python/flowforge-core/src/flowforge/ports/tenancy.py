"""TenancyResolver port — single/multi/no tenancy."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from .types import TenantId


@runtime_checkable
class TenancyResolver(Protocol):
	"""Determines the active tenant for a session.

	Implementations live in ``flowforge-tenancy`` (default) or in host
	code. The engine calls :meth:`current_tenant` on every event entry
	and :meth:`bind_session` before any DB query.
	"""

	async def current_tenant(self) -> TenantId:
		"""Return the active tenant identifier."""

	async def bind_session(self, session: Any, tenant_id: TenantId) -> None:
		"""Bind tenancy parameters onto the storage session.

		For Postgres hosts this typically calls ``set_config('app.tenant_id', ...)``.
		For single-tenant hosts this is a no-op.
		"""

	def elevated_scope(self) -> AbstractAsyncContextManager[None]:
		"""Bracket an elevated section (operator, support, migration).

		Inside the bracket, RLS predicates that test ``app.elevated`` see
		``true``; outside, they see ``false``.
		"""
