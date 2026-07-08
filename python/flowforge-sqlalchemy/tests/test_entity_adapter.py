"""Generic SqlAlchemyEntityAdapter CRUD tests."""

from __future__ import annotations

import pytest
from flowforge.ports.entity import EntityAdapter
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from flowforge_sqlalchemy import Base, EntityNotFound, SqlAlchemyEntityAdapter

pytestmark = pytest.mark.asyncio


class ClaimEntity(Base):
	__tablename__ = "entity_adapter_claims"

	id: Mapped[str] = mapped_column(String(64), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
	status: Mapped[str] = mapped_column(String(32), nullable=False)
	amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


async def test_sqlalchemy_entity_adapter_crud_roundtrip(
	session_factory: async_sessionmaker[AsyncSession],
) -> None:
	adapter = SqlAlchemyEntityAdapter(
		ClaimEntity,
		writable_fields=("id", "tenant_id", "status", "amount"),
		compensations={"delete": "delete_claim"},
	)
	assert isinstance(adapter, EntityAdapter)
	assert adapter.compensations == {"delete": "delete_claim"}

	async with session_factory() as session:
		created = await adapter.create(
			session,
			{
				"id": "claim-1",
				"tenant_id": "tenant-a",
				"status": "new",
				"amount": 10,
			},
		)
		assert created == {
			"id": "claim-1",
			"tenant_id": "tenant-a",
			"status": "new",
			"amount": 10,
		}

		updated = await adapter.update(
			session,
			"claim-1",
			{"status": "approved", "amount": 25},
		)
		assert updated["status"] == "approved"
		assert updated["amount"] == 25
		assert await adapter.lookup(session, "claim-1") == updated

		row = await session.scalar(select(ClaimEntity).where(ClaimEntity.id == "claim-1"))
		assert row is not None
		assert row.status == "approved"

		assert await adapter.delete(session, "claim-1") is True
		assert await adapter.delete(session, "claim-1") is False
		with pytest.raises(EntityNotFound):
			await adapter.lookup(session, "claim-1")


async def test_sqlalchemy_entity_adapter_rejects_unknown_fields_and_pk_update(
	session_factory: async_sessionmaker[AsyncSession],
) -> None:
	adapter = SqlAlchemyEntityAdapter(ClaimEntity)

	async with session_factory() as session:
		with pytest.raises(ValueError, match="unknown entity fields"):
			await adapter.create(
				session,
				{
					"id": "claim-2",
					"tenant_id": "tenant-a",
					"status": "new",
					"amount": 10,
					"admin": True,
				},
			)

		await adapter.create(
			session,
			{
				"id": "claim-2",
				"tenant_id": "tenant-a",
				"status": "new",
				"amount": 10,
			},
		)
		with pytest.raises(ValueError, match="cannot be updated"):
			await adapter.update(session, "claim-2", {"id": "claim-3"})


async def test_sqlalchemy_entity_adapter_validates_field_configuration() -> None:
	with pytest.raises(ValueError, match="unknown writable fields"):
		SqlAlchemyEntityAdapter(ClaimEntity, writable_fields=("missing",))
	with pytest.raises(ValueError, match="unknown readable fields"):
		SqlAlchemyEntityAdapter(ClaimEntity, readable_fields=("missing",))
