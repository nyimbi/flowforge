"""PostgreSQL :class:`flowforge.ports.rls.RlsBinder` implementation.

This binder sets the GUCs that UMS-style RLS policies read:

* ``app.tenant_id`` — current tenant. Policies use ``current_setting()``
  to filter rows.
* ``app.elevated`` — set to ``'true'`` while an operator-elevated section
  is active; policies opt out of tenant filtering when this is ``true``.

The binder is a no-op on non-PostgreSQL dialects (SQLite tests) so the
same code path works in both environments. The :meth:`elevated`
context manager always re-clears the GUC on exit, even if the wrapped
block raises.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from flowforge.ports.types import ExecutionContext
from sqlalchemy import text


class PgRlsBinder:
	"""Bind ``app.tenant_id`` / ``app.elevated`` GUCs onto an async session."""

	async def bind(self, session: Any, ctx: ExecutionContext) -> None:
		"""Issue ``set_config`` for tenant + elevated on *session*.

		``session`` must expose an async ``execute()`` method (any
		:class:`sqlalchemy.ext.asyncio.AsyncSession` qualifies). Plain
		stub objects with the same shape work for tests.
		"""
		assert ctx is not None, "ExecutionContext is required"
		if not _is_postgres(session):
			return
		await session.execute(
			text("SELECT set_config('app.tenant_id', :tid, true)"),
			{"tid": ctx.tenant_id},
		)
		await session.execute(
			text("SELECT set_config('app.elevated', :elev, true)"),
			{"elev": "true" if ctx.elevated else "false"},
		)

	@asynccontextmanager
	async def elevated(self, session: Any) -> AsyncIterator[None]:
		"""Bracket a block of operator-elevated work.

		Sets ``app.elevated='true'`` on entry and clears to ``'false'`` on
		exit (even on exception).
		"""
		if not _is_postgres(session):
			yield
			return
		await session.execute(
			text("SELECT set_config('app.elevated', 'true', true)")
		)
		try:
			yield
		finally:
			await session.execute(
				text("SELECT set_config('app.elevated', 'false', true)")
			)


def _is_postgres(session: Any) -> bool:
	"""Best-effort dialect probe.

	Production sessions expose ``bind.dialect.name``; the test stub
	hands us a flag. Anything else is treated as non-PostgreSQL so we
	don't blow up under SQLite.
	"""
	flag = getattr(session, "is_postgres", None)
	if flag is not None:
		return bool(flag)
	bind = getattr(session, "bind", None)
	dialect = getattr(bind, "dialect", None)
	name = getattr(dialect, "name", None)
	return name == "postgresql"
