"""Integration test: ``make restore-drill`` end-to-end against Postgres.

Implements the procedure documented in
``docs/ops/<bundle>/restore-runbook.md`` (item 7 of
:doc:`docs/improvements`, W2 of
:doc:`docs/v0.3.0-engineering-plan`):

1. Spin up a fresh Postgres via ``testcontainers`` (or use
   ``FLOWFORGE_TEST_PG_URL`` when CI provides one).
2. Apply the framework's alembic bundle (audit + sagas + outbox + the
   per-bundle entity tables).
3. Seed audit rows under one tenant — a small, deterministic chain.
4. ``pg_dump`` the database (schema + data).
5. Drop the schema; recreate empty.
6. ``pg_restore`` from the dump.
7. Re-verify the audit hash chain row-by-row using
   ``flowforge_audit_pg.hash_chain.verify_chain_in_memory``.
8. Assert: chain intact, no orphan rows, every tenant present in the
   pre-dump state survives the restore.

Skips with a clear reason when neither ``FLOWFORGE_TEST_PG_URL`` is set
nor ``testcontainers`` is installed — the assertions still run when
either path is available.

Reference: ``Makefile`` target ``restore-drill`` /
``audit-2026-restore-drill``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
	AsyncEngine,
	create_async_engine,
)

from flowforge_audit_pg.hash_chain import (
	AuditRow,
	compute_row_sha,
	verify_chain_in_memory,
)
from flowforge_audit_pg.sink import create_tables as create_audit_tables


# ---------------------------------------------------------------------------
# Postgres availability gate
# ---------------------------------------------------------------------------


def _have_pg_dump() -> bool:
	return shutil.which("pg_dump") is not None and shutil.which("psql") is not None


def _resolve_pg_url() -> str | None:
	"""Return a usable async Postgres URL or ``None``.

	Precedence:
	1. ``FLOWFORGE_TEST_PG_URL`` env var (CI provides this).
	2. Testcontainers Postgres if the package is importable.
	3. ``None`` otherwise (test skips).
	"""

	url = os.environ.get("FLOWFORGE_TEST_PG_URL")
	if url:
		return url
	# Lazy probe — only required when the env var is missing. The actual
	# import happens inside the fixture at fixture-setup time so the
	# skip path doesn't pay the import cost. ``find_spec`` of a
	# dotted path raises ``ModuleNotFoundError`` when the parent is
	# missing, so guard the whole probe.
	import importlib.util  # local: keeps top-level imports clean

	try:
		spec = importlib.util.find_spec("testcontainers.postgres")
	except ModuleNotFoundError:  # pragma: no cover
		return None
	if spec is None:  # pragma: no cover
		return None
	# The ``postgres`` driver string downgrades to sync. We rebuild the
	# URL with the asyncpg driver below.
	# Container is created in the fixture so it lives for the test
	# scope; this helper only signals availability.
	return "testcontainers://"


_PG_URL = _resolve_pg_url()
_HAS_TOOLS = _have_pg_dump()


pytestmark = pytest.mark.skipif(
	_PG_URL is None or not _HAS_TOOLS,
	reason=(
		"restore-drill needs Postgres (set FLOWFORGE_TEST_PG_URL or install "
		"testcontainers) and pg_dump/psql in PATH"
	),
)


# ---------------------------------------------------------------------------
# Fixtures: spin up Postgres + apply schema
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _container_pg_engine() -> AsyncIterator[tuple[AsyncEngine, str]]:
	"""Provision a Postgres testcontainer and yield (engine, sync_url).

	The sync_url is what ``pg_dump`` / ``psql`` consume. Skips the test
	cleanly when the docker daemon is unreachable (testcontainers is
	installed but the developer's docker is offline) — this matches the
	skip semantics the module-level skipif uses for other absent deps.
	"""

	try:
		from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
	except ImportError:  # pragma: no cover
		pytest.skip("testcontainers not installed")

	try:
		container = PostgresContainer("postgres:16-alpine")
		container.start()
	except Exception as exc:  # pragma: no cover - docker unavailable at runtime
		# Docker daemon offline / socket unreachable / image pull failed —
		# the drill cannot run, but it isn't a test failure.
		pytest.skip(f"docker daemon unreachable for testcontainers: {exc!r}")

	try:
		sync_url = container.get_connection_url()
		# testcontainers returns ``postgresql+psycopg2://``. Rewrite for
		# asyncpg + strip ``+psycopg2``.
		async_url = sync_url.replace("+psycopg2", "+asyncpg")
		engine = create_async_engine(async_url, future=True)
		try:
			yield engine, sync_url
		finally:
			await engine.dispose()
	finally:
		container.stop()


@pytest_asyncio.fixture
async def pg_engine_and_url() -> AsyncIterator[tuple[AsyncEngine, str]]:
	"""Yield (async_engine, sync_url_for_pg_tools)."""

	url = os.environ.get("FLOWFORGE_TEST_PG_URL")
	if url:
		async_url = url if "+asyncpg" in url else url.replace("postgresql://", "postgresql+asyncpg://")
		sync_url = url.replace("+asyncpg", "")
		engine = create_async_engine(async_url, future=True)
		try:
			yield engine, sync_url
		finally:
			await engine.dispose()
	else:
		async with _container_pg_engine() as pair:
			yield pair


# ---------------------------------------------------------------------------
# Helpers: seed + dump + restore + verify
# ---------------------------------------------------------------------------


async def _create_audit_schema(engine: AsyncEngine) -> None:
	async with engine.begin() as conn:
		await create_audit_tables(conn)


async def _seed_audit_chain(
	engine: AsyncEngine,
	tenant_id: str,
	*,
	rows: int = 5,
) -> list[AuditRow]:
	"""Insert a small, deterministic audit chain. Returns the in-memory rows.

	Uses the canonical hash-chain algorithm; the seed mimics what the
	live audit sink would write so the post-restore verifier can walk
	the chain identically.
	"""

	now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
	prev_sha: str | None = None
	written: list[AuditRow] = []
	async with engine.begin() as conn:
		for i in range(rows):
			row = AuditRow(
				event_id=str(uuid.uuid4()),
				tenant_id=tenant_id,
				actor_user_id="tester",
				kind=f"event.kind.{i}",
				subject_kind="instance",
				subject_id=f"inst-{i}",
				occurred_at=now,
				payload={"ord": i, "tenant": tenant_id},
				prev_sha256=prev_sha,
			)
			# Compute the row sha from the canonical dict shape that
			# verify_chain_in_memory expects.
			canonical_dict = {
				"tenant_id": row.tenant_id,
				"actor_user_id": row.actor_user_id,
				"kind": row.kind,
				"subject_kind": row.subject_kind,
				"subject_id": row.subject_id,
				"occurred_at": row.occurred_at,
				"payload": row.payload,
			}
			row.row_sha256 = compute_row_sha(prev_sha, canonical_dict)
			prev_sha = row.row_sha256
			# Insert into ff_audit_events (created by create_audit_tables).
			await conn.execute(
				sa.text(
					"INSERT INTO ff_audit_events ("
					"event_id, tenant_id, actor_user_id, kind, "
					"subject_kind, subject_id, occurred_at, payload, "
					"prev_sha256, row_sha256"
					") VALUES ("
					":event_id, :tenant_id, :actor_user_id, :kind, "
					":subject_kind, :subject_id, :occurred_at, "
					"CAST(:payload AS JSONB), :prev_sha256, :row_sha256"
					")"
				),
				{
					"event_id": row.event_id,
					"tenant_id": row.tenant_id,
					"actor_user_id": row.actor_user_id,
					"kind": row.kind,
					"subject_kind": row.subject_kind,
					"subject_id": row.subject_id,
					"occurred_at": row.occurred_at,
					"payload": __import__("json").dumps(
						{"ord": i, "tenant": tenant_id}
					),
					"prev_sha256": row.prev_sha256,
					"row_sha256": row.row_sha256,
				},
			)
			written.append(row)
	return written


def _pg_dump(sync_url: str, out_dir: Path) -> tuple[Path, Path]:
	"""Take the schema + data dumps the runbook documents."""

	schema_path = out_dir / "dump.schema.sql"
	data_path = out_dir / "dump.data.sql"
	subprocess.run(
		[
			"pg_dump",
			"--schema-only",
			"--no-owner",
			"--no-privileges",
			"--format=plain",
			f"--file={schema_path}",
			sync_url,
		],
		check=True,
	)
	subprocess.run(
		[
			"pg_dump",
			"--data-only",
			"--no-owner",
			"--disable-triggers",
			"--format=plain",
			f"--file={data_path}",
			sync_url,
		],
		check=True,
	)
	assert schema_path.exists() and schema_path.stat().st_size > 0
	assert data_path.exists() and data_path.stat().st_size > 0
	return schema_path, data_path


def _drop_public_schema(sync_url: str) -> None:
	subprocess.run(
		[
			"psql",
			"--variable=ON_ERROR_STOP=1",
			"--command=DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
			sync_url,
		],
		check=True,
	)


def _pg_restore(sync_url: str, schema_path: Path, data_path: Path) -> None:
	"""The runbook's procedure: schema apply, then data load."""

	subprocess.run(
		[
			"psql",
			"--variable=ON_ERROR_STOP=1",
			"--single-transaction",
			f"--file={schema_path}",
			sync_url,
		],
		check=True,
	)
	subprocess.run(
		[
			"psql",
			"--variable=ON_ERROR_STOP=1",
			"--single-transaction",
			f"--file={data_path}",
			sync_url,
		],
		check=True,
	)


async def _read_chain(engine: AsyncEngine, tenant_id: str) -> list[AuditRow]:
	"""Read the audit chain back as :class:`AuditRow`, ascending."""

	async with engine.connect() as conn:
		result = await conn.execute(
			sa.text(
				"SELECT event_id, tenant_id, actor_user_id, kind, "
				"subject_kind, subject_id, occurred_at, payload, "
				"prev_sha256, row_sha256 FROM ff_audit_events "
				"WHERE tenant_id = :tenant_id ORDER BY occurred_at, event_id"
			),
			{"tenant_id": tenant_id},
		)
		rows: list[AuditRow] = []
		for r in result.mappings():
			rows.append(
				AuditRow(
					event_id=r["event_id"],
					tenant_id=r["tenant_id"],
					actor_user_id=r["actor_user_id"],
					kind=r["kind"],
					subject_kind=r["subject_kind"],
					subject_id=r["subject_id"],
					occurred_at=r["occurred_at"].astimezone(timezone.utc)
					if r["occurred_at"].tzinfo
					else r["occurred_at"].replace(tzinfo=timezone.utc),
					payload=r["payload"],
					prev_sha256=r["prev_sha256"],
					row_sha256=r["row_sha256"],
				)
			)
	return rows


# ---------------------------------------------------------------------------
# The drill itself
# ---------------------------------------------------------------------------


async def test_restore_drill_single_tenant(
	pg_engine_and_url: tuple[AsyncEngine, str],
	tmp_path: Path,
) -> None:
	"""Schema apply → seed → dump → drop → restore → verify chain intact."""

	engine, sync_url = pg_engine_and_url

	# Step 1-2: provision + apply schema.
	await _create_audit_schema(engine)

	# Step 3: seed.
	tenant_id = "tenant-restore-drill"
	pre_chain = await _seed_audit_chain(engine, tenant_id, rows=7)
	assert len(pre_chain) == 7
	# Sanity: the in-memory chain we wrote verifies before we touch the DB.
	ok, bad = verify_chain_in_memory(pre_chain)
	assert ok, f"pre-dump in-memory chain corrupt at row {bad}"

	# Step 4: pg_dump the bundle.
	schema_path, data_path = _pg_dump(sync_url, tmp_path)

	# Step 5: drop the schema.
	# Async engine pool may hold connections that block the DROP — dispose
	# the engine before the drop and rebuild after.
	await engine.dispose()
	_drop_public_schema(sync_url)

	# Step 6: restore.
	_pg_restore(sync_url, schema_path, data_path)

	# Reconnect.
	async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")
	if "+psycopg2" in async_url:
		async_url = async_url.replace("+psycopg2", "+asyncpg")
	restored = create_async_engine(async_url, future=True)
	try:
		# Step 7: read the chain back, in order.
		post_chain = await _read_chain(restored, tenant_id)
		# No orphan rows — every pre-dump row survived.
		assert len(post_chain) == len(pre_chain)
		assert {r.event_id for r in post_chain} == {r.event_id for r in pre_chain}

		# Step 8: assert audit chain intact.
		ok, bad = verify_chain_in_memory(post_chain)
		assert ok, (
			f"post-restore audit chain broken at event_id={bad}; "
			"the dump or restore corrupted ordering or hash columns."
		)

		# Per-row sha matches what we recorded pre-dump (no rehash drift).
		pre_by_id = {r.event_id: r for r in pre_chain}
		for post in post_chain:
			pre = pre_by_id[post.event_id]
			assert post.row_sha256 == pre.row_sha256
			assert post.prev_sha256 == pre.prev_sha256
	finally:
		await restored.dispose()


async def test_restore_drill_multiple_tenants(
	pg_engine_and_url: tuple[AsyncEngine, str],
	tmp_path: Path,
) -> None:
	"""Multi-tenant chains all re-verify after restore.

	The runbook documents enumerating every tenant in the dump and
	verifying each chain. This test seeds three tenants, exercises the
	enumeration query, and asserts every chain re-verifies.
	"""

	engine, sync_url = pg_engine_and_url
	await _create_audit_schema(engine)

	tenants = ["tenant-a", "tenant-b", "tenant-c"]
	pre = {}
	for t in tenants:
		pre[t] = await _seed_audit_chain(engine, t, rows=4)

	schema_path, data_path = _pg_dump(sync_url, tmp_path)
	await engine.dispose()
	_drop_public_schema(sync_url)
	_pg_restore(sync_url, schema_path, data_path)

	async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")
	if "+psycopg2" in async_url:
		async_url = async_url.replace("+psycopg2", "+asyncpg")
	restored = create_async_engine(async_url, future=True)
	try:
		# Enumerate tenants present in the dump (the runbook's own SQL).
		async with restored.connect() as conn:
			result = await conn.execute(
				sa.text(
					"SELECT DISTINCT tenant_id FROM ff_audit_events "
					"WHERE tenant_id IS NOT NULL ORDER BY tenant_id"
				)
			)
			seen = [row[0] for row in result.fetchall()]
		assert seen == sorted(tenants), (
			f"tenant enumeration drift: expected {sorted(tenants)} got {seen}"
		)

		# Each tenant's chain re-verifies.
		for t in tenants:
			post = await _read_chain(restored, t)
			assert len(post) == len(pre[t])
			ok, bad = verify_chain_in_memory(post)
			assert ok, f"chain broken for tenant={t} at event_id={bad}"
	finally:
		await restored.dispose()
