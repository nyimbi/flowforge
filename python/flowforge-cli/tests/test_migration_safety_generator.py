"""Tests for the per-bundle migration_safety generator (W0 item 1)."""

from __future__ import annotations

import json
from pathlib import Path

from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import migration_safety as gen
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


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_one_md_per_jtbd_insurance_claim() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	files = gen.generate(bundle)
	assert len(files) == 1
	out = files[0]
	assert out.path.startswith("backend/migrations/safety/")
	assert out.path.endswith(".md")
	assert "Migration safety:" in out.content
	assert "claim_intake" in out.content
	# The known revision id from the example output.
	assert "2a43cfa86685" in out.content


def test_emits_one_md_per_jtbd_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	files = gen.generate(bundle)
	# 5 JTBDs in the building-permit bundle.
	assert len(files) == 5
	paths = {f.path for f in files}
	assert all(p.startswith("backend/migrations/safety/") for p in paths)
	assert all(p.endswith(".md") for p in paths)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_output() -> None:
	"""Two invocations against the same bundle produce byte-identical output."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	first = gen.generate(bundle)
	second = gen.generate(bundle)
	assert len(first) == len(second)
	for a, b in zip(first, second):
		assert a.path == b.path
		assert a.content == b.content


def test_revision_matches_db_migration_revision() -> None:
	"""The safety report revision id matches the db_migration revision id."""
	from flowforge_cli.jtbd.generators import db_migration

	bundle = _load_normalized(_INSURANCE_BUNDLE)
	jt = bundle.jtbds[0]
	expected_rev = db_migration._stable_revision(bundle.project.package, jt.id)
	files = gen.generate(bundle)
	assert any(expected_rev in f.path for f in files)
	assert any(expected_rev in f.content for f in files)


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	"""Module-level CONSUMES matches the fixture-registry entry."""
	registry_view = _fixture_registry.get("migration_safety")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_migration_safety() -> None:
	assert "migration_safety" in _fixture_registry.all_generators()
