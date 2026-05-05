"""PgRlsBinder issues set_config calls on a stub session."""

from __future__ import annotations

from typing import Any

import pytest
from flowforge.ports.types import ExecutionContext, Principal

from flowforge_sqlalchemy import PgRlsBinder

pytestmark = pytest.mark.asyncio


class _StubSession:
	"""Minimal async-session stand-in. Records ``execute()`` invocations."""

	def __init__(self, *, is_postgres: bool = True) -> None:
		self.is_postgres = is_postgres
		self.calls: list[tuple[str, dict[str, Any] | None]] = []

	async def execute(self, clause: Any, params: dict[str, Any] | None = None) -> None:
		# ``clause`` is a sqlalchemy.text() construct; render to string for
		# inspection without standing up an Engine.
		self.calls.append((str(clause), params))


def _ctx(*, tenant_id: str = "t-1", elevated: bool = False) -> ExecutionContext:
	return ExecutionContext(
		tenant_id=tenant_id,
		principal=Principal(user_id="u-1", is_system=False),
		elevated=elevated,
	)


async def test_bind_emits_tenant_and_elevated_for_postgres() -> None:
	binder = PgRlsBinder()
	session = _StubSession(is_postgres=True)

	await binder.bind(session, _ctx())

	assert len(session.calls) == 2
	first_sql, first_params = session.calls[0]
	second_sql, second_params = session.calls[1]
	assert "set_config('app.tenant_id'" in first_sql
	assert first_params == {"tid": "t-1"}
	assert "set_config('app.elevated'" in second_sql
	assert second_params == {"elev": "false"}


async def test_bind_passes_elevated_true() -> None:
	binder = PgRlsBinder()
	session = _StubSession(is_postgres=True)

	await binder.bind(session, _ctx(elevated=True))

	_, params = session.calls[1]
	assert params == {"elev": "true"}


async def test_bind_is_noop_on_non_postgres() -> None:
	binder = PgRlsBinder()
	session = _StubSession(is_postgres=False)

	await binder.bind(session, _ctx())

	assert session.calls == []


async def test_elevated_context_sets_and_clears() -> None:
	binder = PgRlsBinder()
	session = _StubSession(is_postgres=True)

	async with binder.elevated(session):
		# entry call
		assert len(session.calls) == 1
		assert "set_config('app.elevated', 'true'" in session.calls[0][0]
	# exit call
	assert len(session.calls) == 2
	assert "set_config('app.elevated', 'false'" in session.calls[1][0]


async def test_elevated_context_clears_on_exception() -> None:
	binder = PgRlsBinder()
	session = _StubSession(is_postgres=True)

	with pytest.raises(RuntimeError):
		async with binder.elevated(session):
			raise RuntimeError("boom")

	assert len(session.calls) == 2
	assert "set_config('app.elevated', 'false'" in session.calls[1][0]


async def test_elevated_context_is_noop_on_non_postgres() -> None:
	binder = PgRlsBinder()
	session = _StubSession(is_postgres=False)

	async with binder.elevated(session):
		pass

	assert session.calls == []
