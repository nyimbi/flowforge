"""Tests for the per-bundle restore_runbook generator (W2 item 7)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import restore_runbook as gen
from flowforge_cli.jtbd.normalize import normalize


_INSURANCE_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "insurance_claim"
	/ "jtbd-bundle.json"
)
_BUILDING_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "building-permit"
	/ "jtbd-bundle.json"
)
_HIRING_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "hiring-pipeline"
	/ "jtbd-bundle.json"
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_one_runbook_per_bundle_insurance_claim() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	assert out.path == "docs/ops/insurance_claim_demo/restore-runbook.md"
	assert "# Restore runbook: `insurance_claim_demo`" in out.content
	# Bundle has 1 JTBD ("claim_intake").
	assert "`claim_intake`" in out.content
	# pg_dump flags appear.
	assert "--data-only" in out.content
	assert "--schema-only" in out.content
	assert "--no-owner" in out.content
	# audit verify step appears.
	assert "flowforge audit verify --tenant" in out.content
	# make target referenced.
	assert "make restore-drill" in out.content


def test_emits_one_runbook_per_bundle_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	assert out.path == "docs/ops/building_permit/restore-runbook.md"
	# 5 JTBDs in the building-permit bundle — every entity table appears.
	for jt in bundle.jtbds:
		assert f"`{jt.table_name}`" in out.content


def test_emits_one_runbook_per_bundle_hiring_pipeline() -> None:
	bundle = _load_normalized(_HIRING_BUNDLE)
	out = gen.generate(bundle)
	assert out.path == "docs/ops/hiring_pipeline/restore-runbook.md"
	for jt in bundle.jtbds:
		assert f"`{jt.table_name}`" in out.content


def test_audit_topics_appear_in_runbook() -> None:
	"""The runbook lists every audit topic the bundle emits."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	for topic in bundle.all_audit_topics:
		assert f"`{topic}`" in out.content


# ---------------------------------------------------------------------------
# FK / topological order
# ---------------------------------------------------------------------------


def test_tables_listed_in_stable_jtbd_id_order() -> None:
	"""Entity tables sort by jtbd.id; idempotency tables follow their owner."""
	bundle = _load_normalized(_BUILDING_BUNDLE)
	view = gen._table_view(bundle)
	# Entity tables follow sorted jtbd.id order.
	entity_jtbd_ids = [t["jtbd_id"] for t in view if t["kind"] == "entity"]
	assert entity_jtbd_ids == sorted({jt.id for jt in bundle.jtbds})
	# Idempotency table sits immediately after its owning entity row.
	for i, row in enumerate(view):
		if row["kind"] == "idempotency":
			prior = view[i - 1]
			assert prior["kind"] == "entity"
			assert prior["jtbd_id"] == row["jtbd_id"]
			assert row["table"] == f"{prior['table']}_idempotency_keys"


def test_idempotency_enabled_when_ttl_field_present() -> None:
	"""When project.idempotency_ttl_hours exists on the bundle, the runbook
	includes per-JTBD idempotency tables."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	# Sibling worker-idempotency landed this attribute; the runbook should
	# detect and include the idempotency cohort.
	assert hasattr(bundle.project, "idempotency_ttl_hours")
	assert gen._idempotency_enabled(bundle) is True
	out = gen.generate(bundle)
	assert "claim_intake_idempotency_keys" in out.content
	assert "Idempotency tables**: included" in out.content


def test_idempotency_gracefully_tolerated_when_attr_missing() -> None:
	"""Pre-W2 codepaths (sibling not landed) lack ``idempotency_ttl_hours``;
	the runbook still emits cleanly with entity tables only."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	# Reach into the frozen dataclass to drop the attribute, simulating
	# a bundle produced by an older normalize() that doesn't carry the
	# field. ``__delattr__`` on a frozen dataclass raises, so we
	# rebuild the project view via dataclasses.replace + explicit field
	# stripping by constructing a dummy class.
	without_ttl = type(
		"_ProjectNoIdempotency",
		(),
		{
			k: v
			for k, v in dataclasses.asdict(bundle.project).items()
			if k != "idempotency_ttl_hours"
		},
	)()
	# Splice the slimmer project onto a copy of the bundle.
	patched = dataclasses.replace(bundle, project=without_ttl)  # type: ignore[arg-type]
	# Verify the detection path returns False on the patched bundle.
	assert gen._idempotency_enabled(patched) is False
	out = gen.generate(patched)
	# Entity tables still appear; idempotency tables absent.
	assert "claim_intake" in out.content
	assert "claim_intake_idempotency_keys" not in out.content
	assert "(not enabled in this bundle" in out.content


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_output() -> None:
	"""Two invocations against the same bundle produce byte-identical output."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert first.path == second.path
	assert first.content == second.content


def test_deterministic_output_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert first.content == second.content


def test_deterministic_output_hiring_pipeline() -> None:
	bundle = _load_normalized(_HIRING_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert first.content == second.content


# ---------------------------------------------------------------------------
# pg_dump flags + restore steps
# ---------------------------------------------------------------------------


def test_pg_dump_flags_complete() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	# Schema dump command lists each --table for the bundle's tables.
	for jt in bundle.jtbds:
		assert f"--table={jt.table_name}" in out.content


def test_eight_step_procedure_present() -> None:
	"""The runbook documents the 8-step DR procedure."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	for header in (
		"### 1. Verify the dump artefacts",
		"### 2. Provision the scratch database",
		"### 3. Apply the schema",
		"### 4. Run flowforge migrations forward",
		"### 5. Load the data",
		"### 6. Re-verify audit chains",
		"### 7. Smoke test",
		"### 8. Decommission the scratch database",
	):
		assert header in out.content


def test_runbook_documents_make_target() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	assert "make restore-drill" in out.content


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	"""Module-level CONSUMES matches the fixture-registry entry."""
	registry_view = _fixture_registry.get("restore_runbook")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_restore_runbook() -> None:
	assert "restore_runbook" in _fixture_registry.all_generators()


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_pipeline_includes_restore_runbook() -> None:
	"""``pipeline.generate`` returns the restore-runbook artefact."""
	from flowforge_cli.jtbd.pipeline import generate as pipeline_generate

	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	files = pipeline_generate(raw)
	paths = {f.path for f in files}
	assert "docs/ops/insurance_claim_demo/restore-runbook.md" in paths
