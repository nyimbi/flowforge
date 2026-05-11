"""Tests for the per-bundle i18n generator (W4b item 17).

Covers:

* Per-bundle aggregation: one set of files emitted regardless of
  JTBD count.
* Output paths land under ``frontend/src/<pkg>/i18n/``.
* English catalog is fully populated from the bundle (field labels,
  transition event button text, audit topics, SLA copy).
* Non-English catalogs are STRUCTURALLY IDENTICAL — same keys, same
  ordering, empty string values (the lint targets).
* Default language tuple ``("en",)`` applied when ``project.languages``
  is missing.
* JSON output is deterministic (``sort_keys=True`` + trailing newline).
* The ``useT.ts`` hook source contains the closed key union.
* Step.tsx (real path) imports ``useT.ts`` and renders the title +
  field labels through ``t()``; skeleton path stays inert.
* Module-level ``CONSUMES`` matches the fixture-registry entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import i18n as gen
from flowforge_cli.jtbd.normalize import normalize


_REPO = Path(__file__).resolve().parents[3]
_INSURANCE_BUNDLE = _REPO / "examples" / "insurance_claim" / "jtbd-bundle.json"
_BUILDING_BUNDLE = _REPO / "examples" / "building-permit" / "jtbd-bundle.json"
_HIRING_BUNDLE = _REPO / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def _bundle(
	*,
	languages: list[str] | None = None,
	compliance: list[str] | None = None,
	form_renderer: str | None = None,
) -> dict[str, Any]:
	"""Compact synthetic bundle for the generator unit tests."""

	bundle: dict[str, Any] = {
		"project": {
			"name": "claims-demo",
			"package": "claims_demo",
			"domain": "claims",
			"tenancy": "single",
		},
		"shared": {"roles": ["adjuster"], "permissions": ["claim.read"]},
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
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
					{
						"id": "policy_number",
						"kind": "text",
						"label": "Policy number",
						"required": True,
						"pii": False,
					},
				],
				"sla": {"warn_pct": 80, "breach_seconds": 86400},
			}
		],
	}
	if languages is not None:
		bundle["project"]["languages"] = languages
	if compliance is not None:
		bundle["jtbds"][0]["compliance"] = compliance
	if form_renderer is not None:
		bundle["project"].setdefault("frontend", {})["form_renderer"] = form_renderer
	return bundle


# ---------------------------------------------------------------------------
# Output shape: one set of files per bundle
# ---------------------------------------------------------------------------


def test_default_language_emits_en_only() -> None:
	"""Bundles without ``project.languages`` get an ``en.json`` + useT.ts pair."""

	norm = normalize(_bundle())
	out = gen.generate(norm)
	paths = sorted(f.path for f in out)
	assert paths == [
		"frontend/src/claims_demo/i18n/en.json",
		"frontend/src/claims_demo/i18n/useT.ts",
	]


def test_multi_language_emits_one_catalog_per_language_plus_useT() -> None:
	"""Each declared language gets its own JSON; useT.ts is per-bundle."""

	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	out = gen.generate(norm)
	paths = sorted(f.path for f in out)
	assert paths == [
		"frontend/src/claims_demo/i18n/en.json",
		"frontend/src/claims_demo/i18n/fr-CA.json",
		"frontend/src/claims_demo/i18n/useT.ts",
	]


def test_per_bundle_aggregation_with_multi_jtbd_bundle() -> None:
	"""5-JTBD building-permit bundle still emits one i18n set, not five."""

	norm = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(norm)
	# Per declared languages (default 'en' for building-permit) + useT.ts
	languages = norm.project.languages
	assert len(out) == len(languages) + 1


# ---------------------------------------------------------------------------
# English catalog is fully populated
# ---------------------------------------------------------------------------


def test_english_catalog_includes_field_labels() -> None:
	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	cat = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	assert cat["jtbd.claim_intake.field.claimant_name.label"] == "Claimant"
	assert cat["jtbd.claim_intake.field.policy_number.label"] == "Policy number"


def test_english_catalog_includes_button_text_per_transition_event() -> None:
	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	cat = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	# derive_transitions always emits ``submit`` and ``approve``.
	assert cat["jtbd.claim_intake.button.submit"] == "Submit"
	assert cat["jtbd.claim_intake.button.approve"] == "Approve"


def test_english_catalog_includes_sla_copy_when_declared() -> None:
	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	cat = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	assert "SLA approaching" in cat["jtbd.claim_intake.sla.warn"]
	assert "80%" in cat["jtbd.claim_intake.sla.warn"]
	assert "SLA breached" in cat["jtbd.claim_intake.sla.breach"]


def test_english_catalog_includes_audit_topic_humanized() -> None:
	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	cat = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	assert cat["audit.claim_intake.submitted"] == "Claim Intake submitted"
	assert cat["audit.claim_intake.approved"] == "Claim Intake approved"


def test_english_catalog_includes_title() -> None:
	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	cat = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	assert cat["jtbd.claim_intake.title"] == "File a claim"


# ---------------------------------------------------------------------------
# Non-English catalogs are structurally identical with empty values
# ---------------------------------------------------------------------------


def test_non_english_catalog_keys_match_english_catalog() -> None:
	"""Same key set; the lint targets are the values, not the schema."""

	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	en = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	fr = json.loads(files["frontend/src/claims_demo/i18n/fr-CA.json"])
	assert sorted(en.keys()) == sorted(fr.keys())


def test_non_english_catalog_values_are_all_empty() -> None:
	"""Empty values are the lint targets."""

	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	fr = json.loads(files["frontend/src/claims_demo/i18n/fr-CA.json"])
	assert fr  # non-empty (i.e. has keys)
	for value in fr.values():
		assert value == "", value


def test_english_catalog_values_are_never_empty() -> None:
	"""English is the source of truth; every key has a populated value."""

	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	en = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	for key, value in en.items():
		assert value != "", f"empty English value for {key!r}"


# ---------------------------------------------------------------------------
# Determinism (Principle 1 + plan §6 cumulative gate)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bundle_path", [_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE])
def test_deterministic_output(bundle_path: Path) -> None:
	"""Two regens against the same bundle produce identical files."""

	norm = _load_normalized(bundle_path)
	first = gen.generate(norm)
	second = gen.generate(norm)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


@pytest.mark.parametrize("flag", ["skeleton", "real"])
@pytest.mark.parametrize("bundle_path", [_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE])
def test_pipeline_deterministic_across_form_renderer_flag(
	bundle_path: Path, flag: str
) -> None:
	"""End-to-end pipeline is deterministic across both form_renderer values."""

	raw = json.loads(bundle_path.read_text(encoding="utf-8"))
	raw.setdefault("project", {}).setdefault("frontend", {})["form_renderer"] = flag
	first = generate(raw)
	second = generate(raw)
	assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


def test_json_uses_sort_keys_and_trailing_newline() -> None:
	"""``sort_keys=True`` + trailing ``\\n`` is the byte-determinism contract."""

	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	for path in (
		"frontend/src/claims_demo/i18n/en.json",
		"frontend/src/claims_demo/i18n/fr-CA.json",
	):
		body = files[path]
		assert body.endswith("\n"), path
		parsed = json.loads(body)
		dumped = json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
		assert body == dumped, f"json drift in {path}"


# ---------------------------------------------------------------------------
# useT.ts hook surface
# ---------------------------------------------------------------------------


def test_useT_imports_default_language_catalog() -> None:
	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	tsx = files["frontend/src/claims_demo/i18n/useT.ts"]
	assert 'import enCatalog from "./en.json";' in tsx


def test_useT_exposes_string_literal_key_union() -> None:
	norm = normalize(_bundle())
	files = {f.path: f.content for f in gen.generate(norm)}
	tsx = files["frontend/src/claims_demo/i18n/useT.ts"]
	# Every English key shows up in the TranslationKey union.
	en = json.loads(files["frontend/src/claims_demo/i18n/en.json"])
	assert "export type TranslationKey =" in tsx
	for key in en.keys():
		assert f'| "{key}"' in tsx, f"missing key in TranslationKey union: {key}"


def test_useT_lists_available_languages() -> None:
	norm = normalize(_bundle(languages=["en", "fr-CA"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	tsx = files["frontend/src/claims_demo/i18n/useT.ts"]
	assert "AVAILABLE_LANGUAGES" in tsx
	assert '"en"' in tsx
	assert '"fr-CA"' in tsx


def test_useT_exports_default_language_constant() -> None:
	norm = normalize(_bundle(languages=["fr-CA", "en"]))
	files = {f.path: f.content for f in gen.generate(norm)}
	tsx = files["frontend/src/claims_demo/i18n/useT.ts"]
	# First entry is the default; here that's fr-CA.
	assert 'export const DEFAULT_LANGUAGE = "fr-CA";' in tsx


# ---------------------------------------------------------------------------
# Step.tsx wiring (real path imports useT and renders through it)
# ---------------------------------------------------------------------------


def _step_tsx(files: list[Any]) -> str:
	(step,) = [f for f in files if f.path.endswith("ClaimIntakeStep.tsx")]
	return step.content


def test_real_path_imports_useT_hook() -> None:
	tsx = _step_tsx(generate(_bundle(form_renderer="real")))
	assert 'import { useT } from "../../claims_demo/i18n/useT";' in tsx


def test_real_path_uses_t_for_title_and_buttons() -> None:
	tsx = _step_tsx(generate(_bundle(form_renderer="real")))
	assert 't("jtbd.claim_intake.title")' in tsx
	assert 't("jtbd.claim_intake.button.submit")' in tsx
	assert 't("jtbd.claim_intake.button.approve")' in tsx


def test_skeleton_path_stays_i18n_free() -> None:
	"""Skeleton path is unchanged — no useT import."""

	tsx = _step_tsx(generate(_bundle(form_renderer="skeleton")))
	assert "useT" not in tsx, tsx


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_pipeline_emits_i18n_files_for_every_example() -> None:
	"""End-to-end: ``generate(bundle)`` includes the i18n + useT files."""

	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		files = generate(raw)
		paths = {f.path for f in files}
		pkg = raw["project"]["package"]
		languages = raw["project"].get("languages") or ["en"]
		for lang in languages:
			assert f"frontend/src/{pkg}/i18n/{lang}.json" in paths, (
				f"{path.name}: missing i18n catalog for {lang}"
			)
		assert f"frontend/src/{pkg}/i18n/useT.ts" in paths


def test_insurance_claim_bundle_emits_fr_CA_catalog() -> None:
	"""The W4b example: insurance_claim declares ``["en", "fr-CA"]``."""

	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	assert raw["project"]["languages"] == ["en", "fr-CA"], (
		"insurance_claim/jtbd-bundle.json must declare both languages to "
		"exercise the multi-language path."
	)
	files = generate(raw)
	paths = {f.path for f in files}
	assert "frontend/src/insurance_claim_demo/i18n/fr-CA.json" in paths


# ---------------------------------------------------------------------------
# Fixture-registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("i18n")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_i18n_generator() -> None:
	assert "i18n" in _fixture_registry.all_generators()


# ---------------------------------------------------------------------------
# Humanizer helpers
# ---------------------------------------------------------------------------


def test_humanize_topic_subject_verb() -> None:
	assert gen.humanize_topic("claim_intake.submitted") == "Claim Intake submitted"
	assert gen.humanize_topic("claim_intake.approved") == "Claim Intake approved"
	assert gen.humanize_topic("claim_intake.escalated") == "Claim Intake escalated"


def test_humanize_topic_branch_annotation() -> None:
	assert gen.humanize_topic("claim_intake.large_loss") == "Claim Intake: large loss"


def test_humanize_topic_rejected_suffix() -> None:
	assert (
		gen.humanize_topic("claim_intake.lapsed_rejected")
		== "Claim Intake lapsed rejected"
	)


def test_humanize_event_underscore_to_space() -> None:
	assert gen.humanize_event("submit") == "Submit"
	assert gen.humanize_event("branch_large_loss") == "Branch large loss"


# ---------------------------------------------------------------------------
# Compliance + lint behaviour (catalog shape; gate logic lives in
# scripts/i18n/check_coverage.py + tested separately)
# ---------------------------------------------------------------------------


def test_compliance_does_not_alter_catalog_shape() -> None:
	"""``compliance:`` is a lint *gate*, not a generator input — the
	catalog is identical with or without it."""

	without = gen.generate(normalize(_bundle(languages=["en", "fr-CA"])))
	with_ = gen.generate(
		normalize(_bundle(languages=["en", "fr-CA"], compliance=["HIPAA"]))
	)
	assert [(f.path, f.content) for f in without] == [
		(f.path, f.content) for f in with_
	]
