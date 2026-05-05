"""Shared async-SQLite fixtures for the flowforge-sqlalchemy test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)

from flowforge_sqlalchemy import Base


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
	"""``async_sessionmaker`` bound to the per-test engine."""
	return async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]


@pytest.fixture
def tenant_id() -> str:
	return "tenant-test"
