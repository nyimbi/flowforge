"""SingleTenantGUC — fixed tenant id, Postgres GUC binder.

Audit 2026 (E-36) hardenings live here:

- ``_GUC_KEY_RE`` validates GUC names (T-01) before any SQL is issued.
- Both the GUC name and value are bound as parameters; the SQL string
  itself is a constant — no f-string interpolation (T-01).
- ``_elevated`` is a per-instance ``ContextVar`` so concurrent async
  tasks each see their own elevation scope (T-02).
- ``bind_session`` asserts the session is inside a transaction so the
  ``SET LOCAL``-style GUC actually scopes to that tx (T-03).
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator


# Whitelist for Postgres GUC names. Mirrors PG's reserved-identifier rules and
# the audit T-01 spec exactly. Anything else raises ValueError before SQL is
# emitted, even though the value is also bound as a parameter (defence in depth).
_GUC_KEY_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9.]*$")

# Constant SQL — both name and value bound as parameters. The :k placeholder
# is required by the T-01 acceptance test.
_SET_CONFIG_SQL: str = "SELECT set_config(:k, :v, true)"


def _validate_guc_key(key: str) -> None:
	if not isinstance(key, str) or not _GUC_KEY_RE.match(key):
		raise ValueError(
			f"invalid GUC key {key!r}: must match {_GUC_KEY_RE.pattern}"
		)


def _assert_in_transaction(session: Any) -> None:
	"""T-03: refuse to bind GUCs outside a transaction.

	If the session exposes ``in_transaction()`` (real SQLAlchemy AsyncSession,
	or test stubs that opt in) we require it to return truthy. Sessions that
	don't expose the method are accepted for duck-typed call sites — the
	production path always exposes it.
	"""
	in_tx = getattr(session, "in_transaction", None)
	if in_tx is None:
		return
	assert in_tx(), (
		"flowforge-tenancy: bind_session must be called inside a transaction "
		"(set_config(..., true) only scopes to the current tx)"
	)


class SingleTenantGUC:
	"""Bind a single, fixed tenant id onto every session.

	The session is expected to be a SQLAlchemy AsyncSession (or anything
	with ``execute(sql, params)`` and ``in_transaction()``) — the binder is
	duck-typed so a stub session in tests works too.
	"""

	def __init__(self, tenant_id: str) -> None:
		assert tenant_id, "tenant_id must be non-empty"
		self._tenant_id = tenant_id
		# Per-instance ContextVar so each resolver maintains its own elevation
		# state isolated across concurrent async tasks (T-02). The id() suffix
		# keeps debug names unique when multiple resolvers exist in one process.
		self._elevated: ContextVar[bool] = ContextVar(
			f"flowforge_tenancy_elevated_single_{id(self)}", default=False
		)

	async def current_tenant(self) -> str:
		return self._tenant_id

	async def bind_session(self, session: Any, tenant_id: str) -> None:
		"""Issue ``SELECT set_config(:k, :v, true)`` for tenant_id and elevation."""
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


async def _set_config(session: Any, key: str, value: str) -> None:
	"""Run ``SELECT set_config(:k, :v, true)`` with both args bound.

	Validates ``key`` against ``_GUC_KEY_RE`` first; raises ``ValueError`` on
	mismatch (T-01). The SQL string is a constant — no f-string interpolation.
	"""
	_validate_guc_key(key)
	res = session.execute(_SET_CONFIG_SQL, {"k": key, "v": value})
	if hasattr(res, "__await__"):
		await res
