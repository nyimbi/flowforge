"""Tests for the per-bundle analytics-taxonomy generator (W2 item 16).

Covers:

* The generator emits exactly two files per bundle, at the documented
  paths (Python StrEnum + TS string-literal union).
* Both files enumerate the same closed set of ``<jtbd_id>.<lifecycle>``
  events, in the same order — Python and TS taxonomies cannot drift.
* Output is byte-deterministic across two invocations on each example.
* The Step.tsx real-path emits the new lifecycle hooks; the skeleton
  path stays inert (analytics-free).
* Module-level CONSUMES matches the fixture-registry entry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import analytics_taxonomy as gen
from flowforge_cli.jtbd.normalize import normalize


_REPO = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = _REPO / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = _REPO / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = _REPO / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _bundle(form_renderer: str | None = None) -> dict[str, Any]:
	"""Compact synthetic bundle reused across the closed-taxonomy assertions."""

	bundle: dict[str, Any] = {
		"project": {
			"name": "claims-demo",
			"package": "claims_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {
			"roles": ["adjuster"],
			"permissions": ["claim.read"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{"id": "claimant_name", "kind": "text", "label": "Claimant", "required": True, "pii": True},
					{"id": "loss_amount", "kind": "money", "label": "Loss", "required": True, "pii": False},
				],
			}
		],
	}
	if form_renderer is not None:
		bundle["project"]["frontend"] = {"form_renderer": form_renderer}
	return bundle


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_two_files_per_bundle() -> None:
	norm = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(norm)
	assert len(out) == 2
	paths = sorted(f.path for f in out)
	assert paths == [
		f"backend/src/{norm.project.package}/analytics.py",
		f"frontend/src/{norm.project.package}/analytics.ts",
	]


def test_per_bundle_aggregation_one_pair_for_multi_jtbd_bundle() -> None:
	"""5-JTBD building-permit bundle still emits exactly one (py, ts) pair."""

	norm = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(norm)
	assert len(out) == 2


# ---------------------------------------------------------------------------
# Closed-taxonomy invariants
# ---------------------------------------------------------------------------


def test_closed_taxonomy_python_strenum_lists_six_events_per_jtbd() -> None:
	norm = _load_normalized(_BUILDING_BUNDLE)
	(py,) = [f for f in gen.generate(norm) if f.path.endswith("analytics.py")]
	# Exactly one StrEnum line per (jtbd, suffix) tuple.
	enum_lines = [
		line for line in py.content.splitlines()
		if re.search(r'^\t[A-Z][A-Z0-9_]+ = "', line)
	]
	expected = len(norm.jtbds) * len(gen.LIFECYCLE_SUFFIXES)
	assert len(enum_lines) == expected, py.content


def test_closed_taxonomy_typescript_lists_six_events_per_jtbd() -> None:
	norm = _load_normalized(_BUILDING_BUNDLE)
	(ts,) = [f for f in gen.generate(norm) if f.path.endswith("analytics.ts")]
	# Each event becomes one line of the form `\tNAME: "x.y",` inside ANALYTICS_EVENTS.
	const_lines = [
		line for line in ts.content.splitlines()
		if re.search(r'^\t[A-Z][A-Z0-9_]+: "', line)
	]
	expected = len(norm.jtbds) * len(gen.LIFECYCLE_SUFFIXES)
	assert len(const_lines) == expected, ts.content


def test_python_and_typescript_share_the_same_event_set() -> None:
	"""Closed enums must agree byte-for-byte on the event-name set."""

	norm = _load_normalized(_BUILDING_BUNDLE)
	files = gen.generate(norm)
	(py,) = [f for f in files if f.path.endswith("analytics.py")]
	(ts,) = [f for f in files if f.path.endswith("analytics.ts")]
	py_events = set(re.findall(r'= "([^"]+)"', py.content))
	ts_events = set(re.findall(r': "([^"]+)"', ts.content))
	assert py_events == ts_events, (py_events ^ ts_events)


def test_lifecycle_suffixes_match_spec() -> None:
	"""Item 16's improvements.md spec lists six lifecycle suffixes."""

	assert gen.LIFECYCLE_SUFFIXES == (
		"field_focused",
		"field_completed",
		"validation_failed",
		"submission_started",
		"submission_succeeded",
		"form_abandoned",
	)


def test_event_names_use_dotted_jtbd_id_lifecycle_shape() -> None:
	norm = _load_normalized(_INSURANCE_BUNDLE)
	(py,) = [f for f in gen.generate(norm) if f.path.endswith("analytics.py")]
	# Insurance bundle's only JTBD is claim_intake.
	assert "claim_intake.field_focused" in py.content
	assert "claim_intake.submission_succeeded" in py.content
	assert "claim_intake.form_abandoned" in py.content


# ---------------------------------------------------------------------------
# Determinism (Principle 1 + plan §6 cumulative gate)
# ---------------------------------------------------------------------------


def test_deterministic_output_insurance_claim() -> None:
	norm = _load_normalized(_INSURANCE_BUNDLE)
	first = gen.generate(norm)
	second = gen.generate(norm)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


def test_deterministic_output_building_permit() -> None:
	norm = _load_normalized(_BUILDING_BUNDLE)
	first = gen.generate(norm)
	second = gen.generate(norm)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


def test_deterministic_output_hiring_pipeline() -> None:
	norm = _load_normalized(_HIRING_BUNDLE)
	first = gen.generate(norm)
	second = gen.generate(norm)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


# ---------------------------------------------------------------------------
# Step.tsx wiring: real path emits hooks, skeleton path stays inert
# ---------------------------------------------------------------------------


def _step_tsx(files: list[Any]) -> str:
	(step,) = [f for f in files if f.path.endswith("ClaimIntakeStep.tsx")]
	return step.content


def test_real_path_imports_analytics_module_and_fires_lifecycle_hooks() -> None:
	tsx = _step_tsx(generate(_bundle("real")))
	# Closed-taxonomy import.
	assert 'from "../../claims_demo/analytics"' in tsx, tsx
	assert "ANALYTICS_EVENTS" in tsx, tsx
	assert "AnalyticsTracker" in tsx, tsx
	# All six lifecycle suffix hooks fire.
	for suffix in gen.LIFECYCLE_SUFFIXES:
		const_name = f"EVT_{suffix.upper()}"
		assert const_name in tsx, f"missing constant {const_name} in real-path Step.tsx"


def test_skeleton_path_is_analytics_free() -> None:
	"""Skeleton path stays unchanged — no analytics import, no lifecycle hooks."""

	tsx = _step_tsx(generate(_bundle("skeleton")))
	assert "ANALYTICS_EVENTS" not in tsx, tsx
	assert "AnalyticsTracker" not in tsx, tsx
	assert "analytics.ts" not in tsx, tsx


def test_real_path_balances_braces_and_parens() -> None:
	"""Cheap syntactic sanity check — analytics hooks must not break balance."""

	tsx = _step_tsx(generate(_bundle("real")))
	assert tsx.count("{") == tsx.count("}"), tsx
	assert tsx.count("(") == tsx.count(")"), tsx


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_pipeline_emits_analytics_files_for_every_example() -> None:
	"""End-to-end: ``flowforge_cli.jtbd.generate`` includes analytics outputs."""

	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		files = generate(raw)
		paths = {f.path for f in files}
		pkg = raw["project"]["package"]
		assert f"backend/src/{pkg}/analytics.py" in paths, f"missing backend analytics for {path.name}"
		assert f"frontend/src/{pkg}/analytics.ts" in paths, f"missing frontend analytics for {path.name}"


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("analytics_taxonomy")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_analytics_taxonomy() -> None:
	assert "analytics_taxonomy" in _fixture_registry.all_generators()
