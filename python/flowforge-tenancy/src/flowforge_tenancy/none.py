"""NoTenancy — single-org apps that don't isolate by tenant."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class NoTenancy:
	"""Returns a constant pseudo-tenant; never touches the session."""

	def __init__(self, pseudo_tenant: str = "default") -> None:
		self._pseudo = pseudo_tenant

	async def current_tenant(self) -> str:
		return self._pseudo

	async def bind_session(self, session: Any, tenant_id: str) -> None:
		return None

	@asynccontextmanager
	async def elevated_scope(self) -> AsyncIterator[None]:
		yield
