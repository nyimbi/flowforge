"""E-37 — Audit-chain hardening regression tests (AU-01, AU-02, AU-03).

Audit findings (audit-fix-plan.md §4.2 AU-01..AU-03, §1.4 AU-03 escalation):

- **AU-01 (P1)** — concurrent record race: two callers reading the chain
  head simultaneously could both write rows with the same `prev_sha256`,
  forking the chain. Fix: a per-tenant serialisation point (PG advisory
  lock on PG; `asyncio.Lock` on the sqlite test path) plus a
  `UNIQUE(tenant_id, ordinal)` constraint as defence in depth.

- **AU-02 (P1)** — full-table materialisation in `verify_chain()`. Fix:
  iterate in 10K-row chunks (keyset paginated by `(occurred_at, event_id)`)
  so peak memory is bounded by chunk size, not row count.

- **AU-03 (P1, escalated SOX/HIPAA)** — canonical bytes drift across
  releases. Fix: ship a committed golden-bytes fixture under
  ``framework/tests/audit_2026/fixtures/canonical_golden.bin`` containing
  the canonical-JSON and sha256 outputs for a fixed input vector. The
  fixture begins with its own sha256 envelope; load refuses on mismatch.

Plan reference: framework/docs/audit-fix-plan.md §4.2 AU-01/02/03, §7 E-37.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from flowforge.ports.types import AuditEvent
from flowforge_audit_pg import PgAuditSink, create_tables


_async = pytest.mark.asyncio  # apply per-test so sync tests don't warn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(
	*,
	kind: str = "workflow.fired",
	subject_kind: str = "workflow_instance",
	subject_id: str = "wf-1",
	tenant_id: str = "tenant-A",
	actor_user_id: str | None = "user-1",
	payload: dict | None = None,
	occurred_at: datetime | None = None,
) -> AuditEvent:
	return AuditEvent(
		kind=kind,
		subject_kind=subject_kind,
		subject_id=subject_id,
		tenant_id=tenant_id,
		actor_user_id=actor_user_id,
		payload=payload or {},
		occurred_at=occurred_at or datetime.now(timezone.utc),
	)


@pytest_asyncio.fixture
async def sqlite_sink(tmp_path):
	"""Fresh on-disk SQLite sink per test (in-memory db doesn't share across conns)."""
	db_path = tmp_path / "audit_e37.db"
	engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
	async with engine.begin() as conn:
		await create_tables(conn)
	sink = PgAuditSink(engine)
	yield sink
	await engine.dispose()


# ---------------------------------------------------------------------------
# AU-01 — Concurrent record race blocked
# ---------------------------------------------------------------------------


@_async
async def test_AU_01_concurrent_record_no_chain_break(sqlite_sink) -> None:
	"""100 concurrent ``record()`` calls for one tenant produce a fork-free chain.

	Pre-fix: two coroutines could both read the same ``MAX(occurred_at)``
	chain head and write rows with identical ``prev_sha256``, forking the
	chain. Post-fix: a per-tenant lock serialises the read+write pair, and
	``UNIQUE(tenant_id, ordinal)`` blocks regressions at the schema layer.
	"""
	N = 100
	tenant = "tenant-concurrent"

	async def _writer(idx: int) -> str:
		# Distinct occurred_at per row so order is well-defined post-write.
		ts = datetime(2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc) + timedelta(microseconds=idx)
		return await sqlite_sink.record(
			_make_event(
				kind=f"concurrent.{idx}",
				subject_id=f"wf-{idx}",
				tenant_id=tenant,
				occurred_at=ts,
				payload={"idx": idx},
			)
		)

	event_ids = await asyncio.gather(*(_writer(i) for i in range(N)))
	assert len(set(event_ids)) == N, "event ids must be unique"

	# Verify chain is intact under concurrency.
	verdict = await sqlite_sink.verify_chain()
	assert verdict.ok is True, (
		f"chain forked under concurrency: bad_id={verdict.first_bad_event_id}"
	)
	assert verdict.checked_count == N

	# Each row's prev_sha256 must equal the predecessor's row_sha256 — i.e.
	# no two rows share the same prev_sha256 (the fork signature).
	from flowforge_audit_pg.sink import ff_audit_events

	async with sqlite_sink._engine.connect() as conn:
		rows = (
			await conn.execute(
				sa.select(ff_audit_events)
				.where(ff_audit_events.c.tenant_id == tenant)
				.order_by(ff_audit_events.c.ordinal.asc())
			)
		).fetchall()

	prev_shas = [r.prev_sha256 for r in rows if r.prev_sha256 is not None]
	assert len(prev_shas) == len(set(prev_shas)), "duplicate prev_sha256 → fork"

	# Ordinals are dense and monotonic per tenant.
	ordinals = [r.ordinal for r in rows]
	assert ordinals == list(range(1, N + 1)), f"ordinals not dense: {ordinals[:5]}..."


@_async
async def test_AU_01_unique_tenant_ordinal_constraint(sqlite_sink) -> None:
	"""``UNIQUE(tenant_id, ordinal)`` blocks duplicate ordinal at the schema layer."""
	from sqlalchemy.exc import IntegrityError

	from flowforge_audit_pg.sink import ff_audit_events

	# Insert two valid rows.
	await sqlite_sink.record(_make_event(tenant_id="t", kind="a"))
	await sqlite_sink.record(_make_event(tenant_id="t", kind="b"))

	# Direct INSERT trying to reuse an ordinal must violate the UNIQUE.
	with pytest.raises(IntegrityError):
		async with sqlite_sink._engine.begin() as conn:
			await conn.execute(
				ff_audit_events.insert().values(
					event_id="duplicate-attempt",
					tenant_id="t",
					actor_user_id="x",
					kind="dup",
					subject_kind="x",
					subject_id="x",
					occurred_at=datetime.now(timezone.utc),
					payload={},
					prev_sha256=None,
					row_sha256="x" * 64,
					ordinal=1,  # duplicates the first row's ordinal
				)
			)


# ---------------------------------------------------------------------------
# AU-02 — Chunked verify keeps peak memory bounded
# ---------------------------------------------------------------------------


@_async
async def test_AU_02_chunked_verify_memory_bound(sqlite_sink) -> None:
	"""Peak python-allocated memory during verify scales with chunk size, not row count.

	We can't run 10M rows in CI, so we run the same workload twice — once
	with a small chunk size and once with a chunk size larger than the row
	count — and assert the small-chunk run is materially cheaper. This
	validates that chunking is wired up without committing to absolute
	byte numbers (which depend on Python release, sqlalchemy version, etc.).
	"""
	from flowforge_audit_pg import sink as sink_mod

	N = 500
	for i in range(N):
		# 1 KiB-ish payload per row to make the materialisation cost visible.
		await sqlite_sink.record(
			_make_event(
				kind=f"e.{i}",
				subject_id=f"wf-{i}",
				payload={"blob": "x" * 1024, "idx": i},
			)
		)

	original_chunk = sink_mod.VERIFY_CHUNK_SIZE

	async def _verify_with_chunk(chunk: int) -> tuple[int, int]:
		sink_mod.VERIFY_CHUNK_SIZE = chunk  # type: ignore[attr-defined]
		tracemalloc.start()
		tracemalloc.clear_traces()
		try:
			verdict = await sqlite_sink.verify_chain()
			_, peak = tracemalloc.get_traced_memory()
		finally:
			tracemalloc.stop()
		return verdict.checked_count, peak

	try:
		small_count, small_peak = await _verify_with_chunk(50)
		big_count, big_peak = await _verify_with_chunk(N + 100)
	finally:
		sink_mod.VERIFY_CHUNK_SIZE = original_chunk  # type: ignore[attr-defined]

	assert small_count == big_count == N

	# Chunked run must be at least 30% cheaper than the unchunked baseline.
	# A regression to materialising the full result set would push the peaks
	# to within a few percent of each other.
	assert small_peak < big_peak * 0.7, (
		f"verify_chain not honouring chunk size: small_peak={small_peak} bytes "
		f"vs big_peak={big_peak} bytes (expected small < 0.7 * big)"
	)


# ---------------------------------------------------------------------------
# AU-03 — Canonical golden bytes
# ---------------------------------------------------------------------------


_GOLDEN_PATH = (
	Path(__file__).resolve().parent / "fixtures" / "canonical_golden.bin"
)


def test_AU_03_canonical_golden_bytes_fixture_exists() -> None:
	"""The committed golden fixture exists and is non-empty."""
	assert _GOLDEN_PATH.is_file(), (
		f"missing canonical golden fixture at {_GOLDEN_PATH} — "
		"regenerate with `python -m flowforge_audit_pg._golden write`"
	)
	assert _GOLDEN_PATH.stat().st_size > 0


def test_AU_03_canonical_golden_bytes_envelope_hash_valid() -> None:
	"""Loader refuses on outer-hash mismatch; this asserts the committed file is intact."""
	from flowforge_audit_pg._golden import load_golden, GoldenIntegrityError

	# Should not raise on the committed bytes.
	bundle = load_golden(_GOLDEN_PATH)
	assert bundle.rows, "golden bundle has no rows"
	assert bundle.envelope_sha is not None

	# Tampered bytes must raise.
	tampered = _GOLDEN_PATH.read_bytes() + b"\x00"
	import tempfile

	with tempfile.NamedTemporaryFile(delete=False) as tmp:
		tmp.write(tampered)
		tmp.flush()
		with pytest.raises(GoldenIntegrityError):
			load_golden(Path(tmp.name))


def test_AU_03_canonical_golden_bytes_match_in_process() -> None:
	"""In-process canonical_json + sha256 must match the committed golden bytes.

	If this fails it means a release accidentally changed the canonical
	encoding (sort_keys, separators, default encoder, etc.) which would
	invalidate every existing audit row's row_sha256. SOX/HIPAA gate.
	"""
	from flowforge_audit_pg._golden import load_golden, recompute_row

	bundle = load_golden(_GOLDEN_PATH)
	for row in bundle.rows:
		got_canonical, got_sha = recompute_row(row.prev_sha256, row.input)
		assert got_canonical == row.canonical_json_bytes, (
			f"canonical_json drift for row {row.event_id}:\n"
			f"  expected: {row.canonical_json_bytes!r}\n"
			f"  got:      {got_canonical!r}"
		)
		assert got_sha == row.row_sha256, (
			f"row_sha256 drift for {row.event_id}: expected {row.row_sha256} got {got_sha}"
		)
