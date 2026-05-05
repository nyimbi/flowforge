"""RlsBinder — bind row-level-security parameters onto a storage session."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from .types import ExecutionContext


@runtime_checkable
class RlsBinder(Protocol):
	"""Set session-local GUCs / row filters before any framework query.

	UMS default: emits ``set_config('app.tenant_id', ...)`` and
	``set_config('app.elevated', ...)`` per session. MySQL hosts use a
	WHERE-injection variant (see portability §11 R2).
	"""

	async def bind(self, session: Any, ctx: ExecutionContext) -> None:
		"""Bind tenancy + elevation parameters onto *session*."""

	def elevated(self, session: Any) -> AbstractAsyncContextManager[None]:
		"""Bracket an operator-elevated section; clears state on exit."""
