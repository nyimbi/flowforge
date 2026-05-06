"""Shared fixtures for the flowforge-jtbd ``tests/ci`` suite.

Mirrors the pattern in :mod:`flowforge_sqlalchemy.tests.conftest` —
async aiosqlite engine, table creation through ``Base.metadata`` (which
contains both engine + JTBD models thanks to side-effect imports), per-
test session factory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from flowforge_sqlalchemy import Base
from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)

# Side-effect import — registers JTBD ORM models into Base.metadata so
# create_all picks them up alongside the workflow tables.
import flowforge_jtbd.db  # noqa: F401


@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[object]:
	"""Per-test in-memory aiosqlite engine; tables created via metadata."""
	engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
	try:
		yield engine
	finally:
		await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine: object) -> async_sessionmaker[AsyncSession]:
	return async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]


@pytest.fixture
def tenant_id() -> str:
	return "tenant-test"
