"""SQLAlchemy ORM models compile + round-trip on async SQLite."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from flowforge_jtbd.db import (
	JtbdCompositionPin,
	JtbdCompositionRow,
	JtbdDomain,
	JtbdLibrary,
	JtbdLockfileRow,
	JtbdSpecRow,
)
from flowforge_jtbd.dsl import JtbdActor, JtbdSpec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _spec_dict(jtbd_id: str = "claim_intake") -> dict[str, object]:
	spec = JtbdSpec(
		id=jtbd_id,
		actor=JtbdActor(role="intake_clerk"),
		situation="s",
		motivation="m",
		outcome="o",
		success_criteria=["sc"],
	).with_hash()
	return spec.model_dump(mode="json")


async def test_library_roundtrip(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	lib_id = str(uuid.uuid4())
	async with session_factory() as session:
		session.add(
			JtbdLibrary(
				id=lib_id,
				tenant_id=tenant_id,
				name="claims-intake",
				domain="insurance",
				status="active",
				description="claims intake JTBDs",
			)
		)
		await session.commit()

	async with session_factory() as session:
		row = await session.scalar(
			select(JtbdLibrary).where(JtbdLibrary.id == lib_id)
		)
		assert row is not None
		assert row.tenant_id == tenant_id
		assert row.name == "claims-intake"
		assert row.domain == "insurance"
		assert isinstance(row.created_at, datetime)


async def test_catalogue_tier_library_has_null_tenant(
	session_factory: async_sessionmaker[AsyncSession],
) -> None:
	lib_id = str(uuid.uuid4())
	async with session_factory() as session:
		session.add(
			JtbdLibrary(
				id=lib_id,
				tenant_id=None,
				name="catalogue-claims",
				domain="insurance",
			)
		)
		await session.commit()

	async with session_factory() as session:
		row = await session.scalar(
			select(JtbdLibrary).where(JtbdLibrary.id == lib_id)
		)
		assert row is not None
		assert row.tenant_id is None


async def test_spec_row_roundtrip_with_jsonb_body(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	lib_id = str(uuid.uuid4())
	spec_id = str(uuid.uuid4())
	body = _spec_dict()
	async with session_factory() as session:
		session.add(
			JtbdLibrary(
				id=lib_id,
				tenant_id=tenant_id,
				name="claims-intake",
				domain="insurance",
			)
		)
		session.add(
			JtbdSpecRow(
				id=spec_id,
				tenant_id=tenant_id,
				library_id=lib_id,
				jtbd_id="claim_intake",
				version="1.0.0",
				spec=body,
				spec_hash=body["spec_hash"],
				status="draft",
				created_by="user-1",
			)
		)
		await session.commit()

	async with session_factory() as session:
		row = await session.scalar(
			select(JtbdSpecRow).where(JtbdSpecRow.id == spec_id)
		)
		assert row is not None
		assert row.spec_hash == body["spec_hash"]
		assert row.spec["actor"]["role"] == "intake_clerk"


async def test_unique_constraint_on_spec_version(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	from sqlalchemy.exc import IntegrityError

	lib_id = str(uuid.uuid4())
	body = _spec_dict()
	async with session_factory() as session:
		session.add(
			JtbdLibrary(
				id=lib_id,
				tenant_id=tenant_id,
				name="claims-intake",
				domain="insurance",
			)
		)
		session.add(
			JtbdSpecRow(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				library_id=lib_id,
				jtbd_id="claim_intake",
				version="1.0.0",
				spec=body,
				spec_hash=body["spec_hash"],
			)
		)
		await session.commit()

	async with session_factory() as session:
		session.add(
			JtbdSpecRow(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				library_id=lib_id,
				jtbd_id="claim_intake",
				version="1.0.0",
				spec=body,
				spec_hash=body["spec_hash"],
			)
		)
		with pytest.raises(IntegrityError):
			await session.commit()


async def test_composition_and_pins_roundtrip(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	comp_id = str(uuid.uuid4())
	async with session_factory() as session:
		session.add(
			JtbdCompositionRow(
				id=comp_id,
				tenant_id=tenant_id,
				name="claims-intake",
				project_package="claims_intake",
				status="draft",
			)
		)
		session.add(
			JtbdCompositionPin(
				composition_id=comp_id,
				jtbd_id="claim_intake",
				tenant_id=tenant_id,
				version="1.0.0",
				spec_hash="sha256:" + ("0" * 64),
				source="local",
			)
		)
		session.add(
			JtbdCompositionPin(
				composition_id=comp_id,
				jtbd_id="claim_triage",
				tenant_id=tenant_id,
				version="2.1.0",
				spec_hash="sha256:" + ("1" * 64),
				source="jtbd-hub",
				source_ref="acme/claims@2.1.0",
			)
		)
		await session.commit()

	async with session_factory() as session:
		pins = (
			await session.scalars(
				select(JtbdCompositionPin).where(
					JtbdCompositionPin.composition_id == comp_id
				)
			)
		).all()
		assert len(pins) == 2
		ids = {p.jtbd_id for p in pins}
		assert ids == {"claim_intake", "claim_triage"}


async def test_lockfile_row_unique_on_composition_body_hash(
	session_factory: async_sessionmaker[AsyncSession], tenant_id: str
) -> None:
	from sqlalchemy.exc import IntegrityError

	comp_id = str(uuid.uuid4())
	body_hash = "sha256:" + ("a" * 64)
	body = {"schema_version": "1", "pins": []}

	async with session_factory() as session:
		session.add(
			JtbdCompositionRow(
				id=comp_id,
				tenant_id=tenant_id,
				name="x",
				project_package="x",
			)
		)
		session.add(
			JtbdLockfileRow(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				composition_id=comp_id,
				body_hash=body_hash,
				body=body,
				pin_count=0,
				generated_by="user-1",
				generated_at=datetime.now(timezone.utc),
			)
		)
		await session.commit()

	async with session_factory() as session:
		session.add(
			JtbdLockfileRow(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				composition_id=comp_id,
				body_hash=body_hash,
				body=body,
				pin_count=0,
				generated_by="user-2",
				generated_at=datetime.now(timezone.utc),
			)
		)
		with pytest.raises(IntegrityError):
			await session.commit()


async def test_domain_unique_on_name(
	session_factory: async_sessionmaker[AsyncSession],
) -> None:
	from sqlalchemy.exc import IntegrityError

	async with session_factory() as session:
		session.add(
			JtbdDomain(
				id=str(uuid.uuid4()),
				name="insurance",
				display_name="Insurance",
				description="claims/UW/reins",
				regulator_hints=["NAIC", "Lloyds"],
				default_compliance=["GDPR"],
			)
		)
		await session.commit()

	async with session_factory() as session:
		session.add(
			JtbdDomain(
				id=str(uuid.uuid4()),
				name="insurance",
				display_name="Insurance again",
				regulator_hints=[],
				default_compliance=[],
			)
		)
		with pytest.raises(IntegrityError):
			await session.commit()
