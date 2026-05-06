"""E-1 integration test: JTBD bundle → alembic-migrated storage → reload.

Drives an end-to-end path that pulls in the alembic bundle, the
SQLAlchemy ORM, the canonical-JSON helper, and the pydantic models in
one go:

1. Run ``alembic upgrade r2_jtbd`` against an isolated SQLite file —
   creates engine + JTBD tables in one chain.
2. Build a :class:`JtbdBundle` in Python; compute every spec hash via
   :func:`flowforge_jtbd.dsl.canonical.spec_hash`.
3. Persist a :class:`JtbdLibrary`, a row per :class:`JtbdSpec`, a
   :class:`JtbdCompositionRow` plus its pins, and a generated
   :class:`JtbdLockfileRow`.
4. Reload everything in a fresh session and re-validate the JSONB body
   back into a :class:`JtbdSpec`; confirm ``compute_hash`` matches the
   stored ``spec_hash``.

The point is to catch any drift between the canonical-JSON encoder,
the pydantic model boundary, and the JSONB column round-trip — three
layers that historically have one of them silently change.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from flowforge_jtbd.db import (
	JtbdCompositionPin,
	JtbdCompositionRow,
	JtbdLibrary,
	JtbdLockfileRow,
	JtbdSpecRow,
)
from flowforge_jtbd.db.alembic_bundle import VERSIONS_DIR as JTBD_VERSIONS_DIR
from flowforge_jtbd.dsl import (
	JtbdActor,
	JtbdBundle,
	JtbdField,
	JtbdLockfile,
	JtbdLockfilePin,
	JtbdProject,
	JtbdSpec,
	canonical_json,
	spec_hash,
)
from flowforge_sqlalchemy.alembic_bundle import (
	BUNDLE_DIR as ENGINE_BUNDLE_DIR,
	VERSIONS_DIR as ENGINE_VERSIONS_DIR,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio


def _alembic_cfg(url: str) -> Config:
	cfg = Config()
	cfg.set_main_option("script_location", ENGINE_BUNDLE_DIR)
	cfg.set_main_option(
		"version_locations",
		f"{ENGINE_VERSIONS_DIR} {JTBD_VERSIONS_DIR}",
	)
	cfg.set_main_option("path_separator", "space")
	cfg.set_main_option("sqlalchemy.url", url)
	return cfg


def _build_bundle() -> JtbdBundle:
	return JtbdBundle(
		project=JtbdProject(
			name="claims-intake-e2e",
			package="claims_intake_e2e",
			domain="insurance",
			tenancy="multi",
		),
		jtbds=[
			JtbdSpec(
				id="claim_intake",
				title="Submit a new motor claim",
				actor=JtbdActor(role="intake_clerk"),
				situation="Policyholder calls in.",
				motivation="Open claim quickly.",
				outcome="Triage-ready record.",
				success_criteria=["docs uploaded", "loss captured"],
				data_capture=[
					JtbdField(id="policy_id", kind="party_ref", pii=False),
					JtbdField(id="claimant_name", kind="text", pii=True),
				],
			),
			JtbdSpec(
				id="claim_triage",
				title="Triage a new claim",
				actor=JtbdActor(role="triage_officer"),
				situation="Fresh claim arrives in queue.",
				motivation="Route within SLA.",
				outcome="Assignee set, severity tagged.",
				success_criteria=["severity assigned"],
			),
		],
	).with_hashes()


async def test_jtbd_storage_roundtrip_via_alembic(tmp_path: Path) -> None:
	# Run the alembic chain (engine → JTBD) on a temp SQLite file. The
	# integration test deliberately does not pre-create tables via
	# Base.metadata.create_all — we want the full migration path.
	db_path = tmp_path / "ff.sqlite"
	url = f"sqlite:///{db_path}"
	cfg = _alembic_cfg(url)
	command.upgrade(cfg, "r2_jtbd")

	# Build the bundle + lockfile.
	bundle = _build_bundle()
	tenant_id = "tenant-acme"
	lib_id = str(uuid.uuid4())
	composition_id = str(uuid.uuid4())

	# Persist using async SQLAlchemy against the migrated DB.
	engine = create_async_engine(url.replace("sqlite:", "sqlite+aiosqlite:"))
	sf = async_sessionmaker(engine, expire_on_commit=False)

	async with sf() as session:
		session.add(
			JtbdLibrary(
				id=lib_id,
				tenant_id=tenant_id,
				name="claims-intake-e2e",
				domain="insurance",
				status="active",
			)
		)
		for spec in bundle.jtbds:
			assert spec.spec_hash is not None
			session.add(
				JtbdSpecRow(
					id=str(uuid.uuid4()),
					tenant_id=tenant_id,
					library_id=lib_id,
					jtbd_id=spec.id,
					version=spec.version,
					spec=spec.model_dump(mode="json"),
					spec_hash=spec.spec_hash,
					status="published",
					created_by="user-e2e",
				)
			)
		session.add(
			JtbdCompositionRow(
				id=composition_id,
				tenant_id=tenant_id,
				name="claims-intake-bundle",
				project_package="claims_intake_e2e",
				status="published",
			)
		)
		for spec in bundle.jtbds:
			assert spec.spec_hash is not None
			session.add(
				JtbdCompositionPin(
					composition_id=composition_id,
					jtbd_id=spec.id,
					tenant_id=tenant_id,
					version=spec.version,
					spec_hash=spec.spec_hash,
					source="local",
				)
			)
		lockfile = JtbdLockfile(
			composition_id=composition_id,
			project_package="claims_intake_e2e",
			pins=[
				JtbdLockfilePin(
					jtbd_id=spec.id,
					version=spec.version,
					spec_hash=spec.spec_hash or "",
					source="local",
				)
				for spec in bundle.jtbds
			],
			generated_by="user-e2e",
		).with_body_hash()
		assert lockfile.body_hash is not None
		session.add(
			JtbdLockfileRow(
				id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				composition_id=composition_id,
				body_hash=lockfile.body_hash,
				body=lockfile.model_dump(mode="json"),
				pin_count=len(lockfile.pins),
				generated_by="user-e2e",
				generated_at=lockfile.generated_at,
			)
		)
		await session.commit()

	# Re-read everything fresh and validate the canonical model
	# round-trips through the JSONB column without drift.
	async with sf() as session:
		spec_rows = (
			await session.scalars(
				select(JtbdSpecRow).where(JtbdSpecRow.tenant_id == tenant_id)
			)
		).all()
		assert {r.jtbd_id for r in spec_rows} == {"claim_intake", "claim_triage"}
		for row in spec_rows:
			parsed = JtbdSpec.model_validate(row.spec)
			assert parsed.id == row.jtbd_id
			assert parsed.version == row.version
			# The hash on the row must match a freshly-computed hash
			# of the persisted body — proves the JSONB column did not
			# alter the canonical bytes.
			assert parsed.compute_hash() == row.spec_hash

		pins = (
			await session.scalars(
				select(JtbdCompositionPin).where(
					JtbdCompositionPin.composition_id == composition_id
				)
			)
		).all()
		assert len(pins) == 2

		locks = (
			await session.scalars(
				select(JtbdLockfileRow).where(
					JtbdLockfileRow.composition_id == composition_id
				)
			)
		).all()
		assert len(locks) == 1
		row = locks[0]
		# Re-hash the persisted body via the lockfile model and verify
		# byte equality.
		reloaded = JtbdLockfile.model_validate(row.body)
		assert reloaded.compute_body_hash() == row.body_hash
		# canonical_json applied to the reloaded lockfile body matches
		# the one we hashed before write — pure determinism check.
		assert canonical_json(reloaded.canonical_body()) == canonical_json(
			lockfile.canonical_body()
		)

	await engine.dispose()


async def test_canonical_hash_matches_dsl_helper_on_persisted_body(
	tmp_path: Path,
) -> None:
	"""Stored ``spec_hash`` derives from the same canonical JSON the
	helper computes on the live model.

	A regression here would mean that the JSONB column is silently
	rewriting the body (key reorder, type coercion, …) such that the
	persisted bytes no longer hash to the value computed before write.
	"""
	db_path = tmp_path / "ff.sqlite"
	url = f"sqlite:///{db_path}"
	command.upgrade(_alembic_cfg(url), "r2_jtbd")

	bundle = _build_bundle()
	engine = create_async_engine(url.replace("sqlite:", "sqlite+aiosqlite:"))
	sf = async_sessionmaker(engine, expire_on_commit=False)
	tenant_id = "tenant-zzz"
	lib_id = str(uuid.uuid4())

	async with sf() as session:
		session.add(
			JtbdLibrary(
				id=lib_id,
				tenant_id=tenant_id,
				name="claims-intake-e2e",
				domain="insurance",
			)
		)
		row_id = str(uuid.uuid4())
		spec = bundle.jtbds[0]
		assert spec.spec_hash is not None
		session.add(
			JtbdSpecRow(
				id=row_id,
				tenant_id=tenant_id,
				library_id=lib_id,
				jtbd_id=spec.id,
				version=spec.version,
				spec=spec.model_dump(mode="json"),
				spec_hash=spec.spec_hash,
				status="published",
			)
		)
		await session.commit()

	async with sf() as session:
		row = await session.scalar(
			select(JtbdSpecRow).where(JtbdSpecRow.id == row_id)
		)
		assert row is not None
		# Independently compute via the canonical helper on the
		# persisted body shape (the dict view).
		body = dict(row.spec)
		# Mimic ``hash_body``'s exclusion set so we hash the same
		# canonical surface the dsl helper does.
		for excluded in (
			"spec_hash",
			"parent_version_id",
			"status",
			"created_by",
			"published_by",
		):
			body.pop(excluded, None)
		assert spec_hash(body) == row.spec_hash

	await engine.dispose()
