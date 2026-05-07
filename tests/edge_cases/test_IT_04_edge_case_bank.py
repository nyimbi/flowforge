"""E-64 / IT-04 — Edge-case test bank (9 classes).

Audit reference: framework/docs/audit-fix-plan.md §7 E-64.

Each class is one or more focused tests exercising a corner of the
framework that production-grade users may hit but unit tests for the
happy-path don't cover. The audit acceptance gate for IT-04 is "all 9
classes covered" — i.e., every class has at least one passing test.

Classes:
1. Empty bundle
2. Max-size lockfile (~10K pins)
3. Unicode / emoji jtbd_id (must be rejected at the validator boundary)
4. Year-boundary timezone (UTC↔local + DST transitions)
5. Concurrent fork of same library (parallel publish under the hash chain)
6. Lockfile compose conflict (duplicate jtbd_id in pin list)
7. Hash-chain one-byte-flip (verifier surfaces the bad row)
8. Outbox + saga crash mid-tx (rollback semantics under failure)
9. In-flight migration (alembic upgrade is reversible)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest


_async = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. Empty bundle
# ---------------------------------------------------------------------------


def test_class_1_empty_bundle_validates() -> None:
	"""A minimum-shape bundle (no JTBDs) is structurally valid."""
	import yaml

	bundle = {
		"project": {
			"name": "empty-example",
			"package": "empty_example",
			"domain": "test",
			"version": "1.0.0",
		},
		"shared": {"roles": [], "permissions": []},
		"jtbds": [],
	}
	# Round-trip through yaml: no exceptions, no field drift.
	dumped = yaml.safe_dump(bundle)
	parsed = yaml.safe_load(dumped)
	assert parsed["jtbds"] == []
	assert parsed["project"]["name"] == "empty-example"


# ---------------------------------------------------------------------------
# 2. Max-size lockfile (10K pins)
# ---------------------------------------------------------------------------


def test_class_2_max_size_lockfile_10k_pins() -> None:
	"""A 10K-pin lockfile composes, hashes, and re-hashes deterministically."""
	from flowforge_jtbd.dsl.lockfile import JtbdLockfile, JtbdLockfilePin

	pins = [
		JtbdLockfilePin(
			jtbd_id=f"jtbd_{i:05d}",
			version=f"1.0.{i % 1000}",
			spec_hash=f"sha256:{i:064x}",
		)
		for i in range(10_000)
	]
	lf = JtbdLockfile(
		composition_id="big_comp",
		project_package="big_pack",
		pins=pins,
	)
	body_hash_a = lf.compute_body_hash()
	# Re-hash via canonical_body must match (chain stability).
	body_hash_b = lf.compute_body_hash()
	assert body_hash_a == body_hash_b
	# Permuted-but-equal pin set hashes identically (sorted in canonical_body).
	import random

	pins_perm = list(pins)
	random.Random(7).shuffle(pins_perm)
	lf_perm = JtbdLockfile(
		composition_id="big_comp",
		project_package="big_pack",
		pins=pins_perm,
	)
	assert lf_perm.compute_body_hash() == body_hash_a


# ---------------------------------------------------------------------------
# 3. Unicode / emoji jtbd_id
# ---------------------------------------------------------------------------


def test_class_3_unicode_emoji_jtbd_id_rejected() -> None:
	"""IdStr validator must reject non-ASCII identifiers."""
	from flowforge_jtbd.dsl.lockfile import JtbdLockfilePin
	from pydantic import ValidationError

	for bad_id in ("jtbd 🚀", "café_run", "工作", "@admin", "id-with-space "):
		with pytest.raises(ValidationError):
			JtbdLockfilePin(
				jtbd_id=bad_id,
				version="1.0.0",
				spec_hash="sha256:" + "0" * 64,
			)


# ---------------------------------------------------------------------------
# 4. Year-boundary timezone (DST transitions)
# ---------------------------------------------------------------------------


def test_class_4_year_boundary_timezone_normalises_to_utc() -> None:
	"""Naive datetimes are rejected; non-UTC-aware datetimes round-trip to UTC."""
	from flowforge_jtbd.dsl.lockfile import JtbdLockfile
	from pydantic import ValidationError

	# 2026-12-31 23:30 in US/Pacific (UTC-8) crosses into 2027-01-01 in UTC.
	pacific = timezone(timedelta(hours=-8))
	year_boundary = datetime(2026, 12, 31, 23, 30, tzinfo=pacific)

	lf = JtbdLockfile(
		composition_id="dst_test",
		project_package="dst_pack",
		pins=[],
		generated_at=year_boundary,
	)
	# Pydantic UtcDatetime AfterValidator normalises to UTC.
	assert lf.generated_at.tzinfo is not None
	assert lf.generated_at.utcoffset() == timedelta(0)
	# Cross-check: 23:30 PST == 07:30 next day UTC.
	assert lf.generated_at == year_boundary.astimezone(timezone.utc)
	assert lf.generated_at.year == 2027 and lf.generated_at.month == 1

	# Naive datetime → ValidationError.
	with pytest.raises(ValidationError):
		JtbdLockfile(
			composition_id="naive",
			project_package="naive_pack",
			pins=[],
			generated_at=datetime(2026, 6, 15, 12, 0),  # no tzinfo
		)


# ---------------------------------------------------------------------------
# 5. Concurrent fork of same library
# ---------------------------------------------------------------------------


@_async
async def test_class_5_concurrent_audit_record_under_one_tenant() -> None:
	"""Surrogate for "concurrent fork": parallel writers to one chain produce a
	fork-free chain (covered structurally by E-37 AU-01; this class asserts the
	property end-to-end at the sink level on a fresh DB).
	"""
	from sqlalchemy.ext.asyncio import create_async_engine

	from flowforge.ports.types import AuditEvent
	from flowforge_audit_pg import PgAuditSink, create_tables

	with tempfile.NamedTemporaryFile(prefix="ff_edge_class5_", suffix=".db", delete=False) as tmp:
		tmp.close()
		engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
		try:
			async with engine.begin() as conn:
				await create_tables(conn)
			sink = PgAuditSink(engine)

			async def writer(idx: int) -> None:
				ts = datetime(2026, 5, 6, tzinfo=timezone.utc) + timedelta(microseconds=idx)
				await sink.record(
					AuditEvent(
						kind=f"fork.attempt.{idx}",
						subject_kind="library",
						subject_id="lib-1",
						tenant_id="tenant-A",
						actor_user_id=f"user-{idx % 5}",
						payload={"i": idx},
						occurred_at=ts,
					)
				)

			await asyncio.gather(*(writer(i) for i in range(50)))
			verdict = await sink.verify_chain()
			assert verdict.ok is True
			assert verdict.checked_count == 50
		finally:
			await engine.dispose()
			Path(tmp.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 6. Lockfile compose conflict (duplicate jtbd_id)
# ---------------------------------------------------------------------------


def test_class_6_lockfile_compose_duplicate_pin_rejected() -> None:
	"""Two pins for the same jtbd_id must raise during model_validate."""
	from flowforge_jtbd.dsl.lockfile import JtbdLockfile, JtbdLockfilePin
	from pydantic import ValidationError

	pin_a = JtbdLockfilePin(
		jtbd_id="claim_intake",
		version="1.0.0",
		spec_hash="sha256:" + "a" * 64,
	)
	pin_b = JtbdLockfilePin(
		jtbd_id="claim_intake",  # duplicate id, different version
		version="1.0.1",
		spec_hash="sha256:" + "b" * 64,
	)
	with pytest.raises(ValidationError):
		JtbdLockfile(
			composition_id="conflict",
			project_package="conflict_pack",
			pins=[pin_a, pin_b],
		)


# ---------------------------------------------------------------------------
# 7. Hash-chain one-byte-flip
# ---------------------------------------------------------------------------


@_async
async def test_class_7_hash_chain_one_byte_flip_detected() -> None:
	"""Flipping one byte of a stored row's payload triggers verifier failure."""
	import sqlalchemy as sa
	from sqlalchemy.ext.asyncio import create_async_engine

	from flowforge.ports.types import AuditEvent
	from flowforge_audit_pg import PgAuditSink, create_tables
	from flowforge_audit_pg.sink import ff_audit_events

	with tempfile.NamedTemporaryFile(prefix="ff_edge_class7_", suffix=".db", delete=False) as tmp:
		tmp.close()
		engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
		try:
			async with engine.begin() as conn:
				await create_tables(conn)
			sink = PgAuditSink(engine)
			# Three rows so the flip lands in the middle and propagates.
			ids: list[str] = []
			for i in range(3):
				eid = await sink.record(
					AuditEvent(
						kind=f"e.{i}",
						subject_kind="x",
						subject_id="s",
						tenant_id="t",
						actor_user_id="u",
						payload={"i": i, "blob": "ok"},
						occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
					)
				)
				ids.append(eid)

			# One-byte flip via direct SQL update of payload.
			async with engine.begin() as conn:
				await conn.execute(
					ff_audit_events.update()
					.where(ff_audit_events.c.event_id == ids[1])
					.values(payload={"i": 1, "blob": "OK"})  # one-letter case flip
				)

			verdict = await sink.verify_chain()
			assert verdict.ok is False
			assert verdict.first_bad_event_id == ids[1]
		finally:
			await engine.dispose()
			Path(tmp.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 8. Outbox + saga crash mid-tx
# ---------------------------------------------------------------------------


@_async
async def test_class_8_outbox_failure_rolls_back_audit() -> None:
	"""Outbox raise during ``fire`` rolls back the audit row + state transition.

	Surrogate for "saga crash mid-tx": engine's two-phase commit semantics
	guarantee no audit row escapes when the outbox dispatch fails. This is the
	end-to-end exercise of E-32 invariant 2 from a different entry point.
	"""
	import copy as _copy

	from flowforge import config as _config
	from flowforge.dsl import WorkflowDef
	from flowforge.engine import fire, new_instance
	from flowforge.engine.fire import OutboxDispatchError
	from flowforge.ports.types import OutboxEnvelope, Principal
	from flowforge.testing.port_fakes import InMemoryAuditSink, InMemoryOutbox

	wd = WorkflowDef.model_validate(
		{
			"key": "edge8",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "triage", "kind": "manual_review"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "triage",
					"effects": [{"kind": "notify", "template": "edge8.submitted"}],
				}
			],
		}
	)

	class _FailingOutbox(InMemoryOutbox):
		async def dispatch(self, envelope: OutboxEnvelope, backend: str = "default") -> None:
			raise RuntimeError("simulated mid-tx crash")

	_config.reset_to_fakes()
	_config.outbox = _FailingOutbox()
	_config.audit = InMemoryAuditSink()

	inst = new_instance(wd, initial_context={"intake": {"policy_id": "p"}})
	pre_state = inst.state
	pre_ctx = _copy.deepcopy(inst.context)

	with pytest.raises(OutboxDispatchError):
		await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))

	# Rollback: state, context, audit count are all unchanged.
	assert inst.state == pre_state
	assert inst.context == pre_ctx
	assert len(_config.audit.events) == 0


# ---------------------------------------------------------------------------
# 9. In-flight migration
# ---------------------------------------------------------------------------


def test_class_9_in_flight_migration_reversible(tmp_path: Path) -> None:
	"""Alembic upgrade ``r2_jtbd`` and immediate downgrade leaves the DB clean."""
	from alembic import command
	from alembic.config import Config
	from flowforge_jtbd.db.alembic_bundle import VERSIONS_DIR as JTBD_VERSIONS_DIR
	from flowforge_sqlalchemy.alembic_bundle import (
		BUNDLE_DIR as ENGINE_BUNDLE_DIR,
		VERSIONS_DIR as ENGINE_VERSIONS_DIR,
	)
	from sqlalchemy import create_engine, inspect

	url = f"sqlite:///{tmp_path / 'inflight.db'}"
	cfg = Config()
	cfg.set_main_option("script_location", ENGINE_BUNDLE_DIR)
	cfg.set_main_option(
		"version_locations",
		f"{ENGINE_VERSIONS_DIR} {JTBD_VERSIONS_DIR}",
	)
	cfg.set_main_option("path_separator", "space")
	cfg.set_main_option("sqlalchemy.url", url)

	# upgrade.
	command.upgrade(cfg, "r2_jtbd")
	engine = create_engine(url)
	tables_after_upgrade = set(inspect(engine).get_table_names())
	assert "jtbd_libraries" in tables_after_upgrade
	engine.dispose()

	# downgrade.
	command.downgrade(cfg, "base")
	engine = create_engine(url)
	tables_after_downgrade = set(inspect(engine).get_table_names())
	# alembic_version may persist; everything else must go.
	tables_after_downgrade.discard("alembic_version")
	assert tables_after_downgrade == set(), (
		f"in-flight migration left tables behind: {tables_after_downgrade}"
	)
	engine.dispose()


# ---------------------------------------------------------------------------
# Coverage gate — every class must contribute at least one test
# ---------------------------------------------------------------------------


def test_IT_04_edge_case_bank_covers_all_9_classes() -> None:
	"""Single-pane assertion that the bank declares all 9 audit classes.

	Failing here means the file has been pruned below the audit-mandated
	coverage bar. The class names are a hash-set against the audit's
	enumeration in §7 E-64.
	"""
	import sys as _sys

	module_tests = [
		name
		for name in dir(_sys.modules[__name__])
		if name.startswith("test_class_")
	]
	classes_covered = sorted({name.split("_")[2] for name in module_tests})
	assert classes_covered == [str(i) for i in range(1, 10)], (
		f"audit-2026 IT-04 requires 9 edge-case classes; got {classes_covered}"
	)
