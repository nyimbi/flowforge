"""Tests for the per-bundle lineage / provenance generator (W3 item 11).

Covers:

* output shape — single ``lineage.json`` at the bundle root, schema_version
  pinned, JTBDs sorted by id, fields sorted by id, stages emitted in the
  canonical five-stage order.
* PII detection — both signals (``pii: true`` *and* ``kind`` in
  :data:`~flowforge_cli.jtbd.generators.lineage.SENSITIVE_FIELD_KINDS`).
* Retention windows — HIPAA / SOX → 7y, GDPR / CCPA / unspecified → 3y,
  ``project.lineage.retention_years`` overrides every JTBD.
* Redaction strategy — every PII field carries the canonical mapping plus
  a per-stage ``redaction`` annotation.
* Exposure surfaces — every shared role × the two read surfaces.
* Determinism — two regens against the same bundle produce byte-identical
  output (Principle 1 of the v0.3.0 engineering plan + W3 acceptance
  criterion).
* Fixture-registry coverage primer — module-level CONSUMES matches the
  registry entry.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import lineage as gen
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


def _load_raw(path: Path) -> dict[str, Any]:
	return json.loads(path.read_text(encoding="utf-8"))


def _load_normalized(path: Path):
	return normalize(_load_raw(path))


def _parse_lineage(content: str) -> dict[str, Any]:
	doc = json.loads(content)
	assert isinstance(doc, dict), "lineage.json top-level must be a mapping"
	return doc


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_single_lineage_json_at_bundle_root() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	assert out.path == "lineage.json"
	doc = _parse_lineage(out.content)
	assert doc["schema_version"] == "1.0.0"
	assert doc["bundle"]["name"] == "insurance-claim-demo"
	assert doc["bundle"]["package"] == "insurance_claim_demo"
	# 1 JTBD in insurance_claim.
	assert len(doc["jtbds"]) == 1
	assert doc["jtbds"][0]["id"] == "claim_intake"


def test_one_jtbd_record_per_jtbd_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	# 5 JTBDs in building-permit.
	assert len(doc["jtbds"]) == 5
	# Sorted by jtbd id (deterministic emission).
	jtbd_ids = [j["id"] for j in doc["jtbds"]]
	assert jtbd_ids == sorted(jtbd_ids)


def test_canonical_stage_order_for_every_field() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	expected_stages = (
		"form_input",
		"service_layer",
		"orm_column",
		"audit_event_payload",
		"outbox_envelope",
	)
	for jt in doc["jtbds"]:
		for f in jt["fields"]:
			actual = tuple(s["stage"] for s in f["stages"])
			assert actual == expected_stages, f"{jt['id']}.{f['id']} stage order"


def test_top_level_stages_and_sensitive_kinds_listed() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	assert doc["stages"] == [
		"form_input",
		"service_layer",
		"orm_column",
		"audit_event_payload",
		"outbox_envelope",
	]
	# sensitive_field_kinds is the sorted SENSITIVE_FIELD_KINDS set.
	assert doc["sensitive_field_kinds"] == sorted(gen.SENSITIVE_FIELD_KINDS)


def test_fields_sorted_by_id_within_each_jtbd() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	for jt in doc["jtbds"]:
		ids = [f["id"] for f in jt["fields"]]
		assert ids == sorted(ids), f"{jt['id']} fields not sorted by id"


# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------


def test_pii_field_detected_via_pii_flag() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	by_id = {f["id"]: f for f in jt["fields"]}
	# claimant_name is text + pii: true → PII.
	assert by_id["claimant_name"]["pii"] is True
	# policy_number is text + pii: false → not PII (text is not in the
	# kind-only sensitive set).
	assert by_id["policy_number"]["pii"] is False


def test_pii_field_detected_via_sensitive_kind() -> None:
	"""Even when ``pii`` is unset, ``email`` / ``phone`` / etc. count as PII."""
	# Synthetic bundle — file kind without an explicit pii flag still
	# triggers PII detection through SENSITIVE_FIELD_KINDS.
	raw = _make_synthetic_bundle(
		fields=[
			{"id": "doc", "kind": "file", "label": "Upload", "required": False, "pii": False},
		],
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	field = doc["jtbds"][0]["fields"][0]
	# kind=file is in SENSITIVE_FIELD_KINDS → PII regardless of the flag.
	assert field["pii"] is True


def test_non_pii_text_field_skips_redaction_strategy() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	by_id = {f["id"]: f for f in doc["jtbds"][0]["fields"]}
	policy = by_id["policy_number"]
	assert policy["pii"] is False
	# Non-PII field omits redaction_strategy + retention_window_years +
	# exposure_surfaces to keep the JSON compact.
	assert "redaction_strategy" not in policy
	assert "retention_window_years" not in policy
	assert "exposure_surfaces" not in policy
	# Stage-level ``redaction`` is also omitted on non-PII stages.
	for st in policy["stages"]:
		assert "redaction" not in st


# ---------------------------------------------------------------------------
# Retention windows (HIPAA / SOX / GDPR / CCPA / override)
# ---------------------------------------------------------------------------


def test_retention_default_is_three_years_when_no_compliance_declared() -> None:
	"""insurance_claim has no compliance: [...] → PII fields get 3y."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	pii_fields = [f for f in jt["fields"] if f["pii"]]
	assert pii_fields, "claim_intake has at least one PII field"
	for f in pii_fields:
		assert f["retention_window_years"] == 3


def test_retention_jumps_to_seven_for_hipaa() -> None:
	raw = _make_synthetic_bundle(
		jtbd_overrides={"compliance": ["HIPAA"]},
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	assert pii_fields
	for f in pii_fields:
		assert f["retention_window_years"] == 7


def test_retention_jumps_to_seven_for_sox() -> None:
	raw = _make_synthetic_bundle(
		jtbd_overrides={"compliance": ["SOX"]},
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	for f in pii_fields:
		assert f["retention_window_years"] == 7


def test_retention_stays_three_for_gdpr_only() -> None:
	"""GDPR alone does not bump the retention window above 3y by default."""
	raw = _make_synthetic_bundle(
		jtbd_overrides={"compliance": ["GDPR"]},
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	for f in pii_fields:
		assert f["retention_window_years"] == 3


def test_retention_stays_three_for_ccpa_only() -> None:
	"""CCPA alone does not bump the retention window above 3y by default."""
	raw = _make_synthetic_bundle(
		jtbd_overrides={"compliance": ["CCPA"]},
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	for f in pii_fields:
		assert f["retention_window_years"] == 3


def test_retention_uses_long_window_when_any_listed_regime_matches() -> None:
	"""HIPAA + PCI-DSS still triggers the 7y window via HIPAA."""
	raw = _make_synthetic_bundle(
		jtbd_overrides={"compliance": ["HIPAA", "PCI-DSS"]},
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	for f in pii_fields:
		assert f["retention_window_years"] == 7


def test_project_lineage_retention_years_overrides_compliance() -> None:
	"""``bundle.project.lineage.retention_years`` wins over compliance defaults."""
	raw = _make_synthetic_bundle(
		project_overrides={"lineage": {"retention_years": 10}},
		jtbd_overrides={"compliance": ["HIPAA"]},  # Would be 7y otherwise.
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	for f in pii_fields:
		assert f["retention_window_years"] == 10
	# Override is also surfaced on the bundle preamble.
	assert doc["bundle"]["retention_years_override"] == 10


def test_override_applies_even_when_no_compliance_declared() -> None:
	raw = _make_synthetic_bundle(
		project_overrides={"lineage": {"retention_years": 5}},
	)
	bundle = normalize(raw)
	doc = _parse_lineage(gen.generate(bundle).content)
	pii_fields = [f for f in doc["jtbds"][0]["fields"] if f["pii"]]
	for f in pii_fields:
		assert f["retention_window_years"] == 5


# ---------------------------------------------------------------------------
# Redaction strategy
# ---------------------------------------------------------------------------


def test_pii_redaction_strategy_carries_canonical_mapping() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	pii_field = next(f for f in jt["fields"] if f["pii"])
	rs = pii_field["redaction_strategy"]
	assert rs == {
		"form_input": "visible",
		"service_layer": "stored_as_is",
		"orm_column": "stored_as_is",
		"audit_event_payload": "redacted_mask",
		"outbox_envelope": "redacted_mask",
	}


def test_per_stage_redaction_matches_strategy_block() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	pii_field = next(f for f in jt["fields"] if f["pii"])
	per_stage = {st["stage"]: st["redaction"] for st in pii_field["stages"]}
	assert per_stage == pii_field["redaction_strategy"]


# ---------------------------------------------------------------------------
# Exposure surfaces
# ---------------------------------------------------------------------------


def test_exposure_surfaces_enumerate_role_x_surface_pairs() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	pii_field = next(f for f in jt["fields"] if f["pii"])
	pairs = pii_field["exposure_surfaces"]
	# Sorted by (role, surface) tuple — assert the contract directly.
	assert pairs == sorted(pairs, key=lambda p: (p["role"], p["surface"]))
	# Exactly the cartesian product of {actor + shared_roles} × surfaces.
	expected_roles = sorted(set(bundle.shared_roles) | {bundle.jtbds[0].actor_role})
	expected = [
		{"role": role, "surface": surface}
		for role in expected_roles
		for surface in ("admin_console.audit_viewer", "service.read")
	]
	assert pairs == expected


def test_exposure_surfaces_include_audit_viewer_and_service_read() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	pii_field = next(f for f in jt["fields"] if f["pii"])
	surfaces = {p["surface"] for p in pii_field["exposure_surfaces"]}
	assert surfaces == {"admin_console.audit_viewer", "service.read"}


# ---------------------------------------------------------------------------
# Stage detail content
# ---------------------------------------------------------------------------


def test_stage_records_carry_expected_locations() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	by_id = {f["id"]: f for f in jt["fields"]}
	# Use a non-PII field so we still check location; both PII and non-PII
	# emit the same paths.
	field = by_id["policy_number"]
	by_stage = {st["stage"]: st for st in field["stages"]}
	assert (
		by_stage["form_input"]["location"]
		== "frontend/src/insurance_claim_demo/claim_intake/Step.tsx"
	)
	assert (
		by_stage["service_layer"]["location"]
		== "backend/src/insurance_claim_demo/claim_intake/service.py"
	)
	assert by_stage["service_layer"]["entrypoint"] == "ClaimIntakeService.fire"
	assert by_stage["orm_column"]["table"] == "claim_intake"
	assert by_stage["orm_column"]["column"] == "policy_number"
	# Audit-payload + outbox stages list the JTBD's audit topics.
	assert by_stage["audit_event_payload"]["topics"] == sorted(
		by_stage["audit_event_payload"]["topics"]
	)
	# Outbox stage carries the notification targets.
	notif_targets = by_stage["outbox_envelope"]["notification_targets"]
	assert all("channel" in n and "audience" in n and "trigger" in n for n in notif_targets)


# ---------------------------------------------------------------------------
# Insurance-claim acceptance: every PII field documents retention + exposure
# ---------------------------------------------------------------------------


def test_insurance_claim_every_pii_field_has_retention_and_exposure() -> None:
	"""W3 acceptance: insurance_claim/lineage.json documents each PII field's
	retention window and exposure surfaces."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_lineage(gen.generate(bundle).content)
	jt = doc["jtbds"][0]
	assert jt["pii_field_count"] >= 1
	for f in jt["fields"]:
		if not f["pii"]:
			continue
		assert isinstance(f["retention_window_years"], int)
		assert f["retention_window_years"] >= 1
		assert isinstance(f["exposure_surfaces"], list)
		assert f["exposure_surfaces"], f"{f['id']} has no exposure surfaces"
		assert f["redaction_strategy"]


# ---------------------------------------------------------------------------
# Determinism (Principle 1 + plan §6 cumulative gate)
# ---------------------------------------------------------------------------


def test_deterministic_output_insurance_claim() -> None:
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


def test_deterministic_output_under_form_renderer_flag_flip() -> None:
	"""Lineage is invariant under the ``form_renderer = "skeleton" | "real"`` flag."""
	raw_real = _load_raw(_INSURANCE_BUNDLE)
	raw_skeleton = copy.deepcopy(raw_real)
	# Force the alternate flag value.
	raw_skeleton["project"].setdefault("frontend", {})["form_renderer"] = "skeleton"
	out_real = gen.generate(normalize(raw_real))
	out_skel = gen.generate(normalize(raw_skeleton))
	assert out_real.content == out_skel.content


def test_json_round_trip_preserves_canonical_form() -> None:
	"""``json.dumps(json.loads(...))`` is a fixed point of the canonical dump."""
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	doc = json.loads(out.content)
	redumped = json.dumps(doc, indent=2, sort_keys=True) + "\n"
	assert redumped == out.content


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("lineage")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_lineage() -> None:
	assert "lineage" in _fixture_registry.all_generators()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_bundle(
	*,
	project_overrides: dict[str, Any] | None = None,
	jtbd_overrides: dict[str, Any] | None = None,
	fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
	"""Build a minimal valid JTBD bundle for compliance / retention tests.

	The bundle has one JTBD with two PII-by-default fields (an email and a
	phone) plus one explicitly non-PII field. Tests merge ``project_overrides``
	into ``project`` and ``jtbd_overrides`` into the single JTBD; ``fields``
	overrides ``data_capture`` wholesale.
	"""

	default_fields = [
		{
			"id": "contact_email",
			"kind": "email",
			"label": "Contact email",
			"required": True,
			"pii": True,
		},
		{
			"id": "contact_phone",
			"kind": "phone",
			"label": "Contact phone",
			"required": False,
			"pii": True,
		},
		{
			"id": "ref",
			"kind": "text",
			"label": "Reference",
			"required": False,
			"pii": False,
		},
	]
	bundle: dict[str, Any] = {
		"project": {
			"name": "synthetic",
			"package": "synthetic_pkg",
			"domain": "test",
			"tenancy": "single",
		},
		"shared": {
			"roles": ["admin", "viewer"],
			"permissions": [],
		},
		"jtbds": [
			{
				"id": "synthetic_intake",
				"title": "Synthetic intake",
				"actor": {"role": "viewer", "external": False},
				"situation": "test situation",
				"motivation": "test motivation",
				"outcome": "test outcome",
				"success_criteria": ["passes"],
				"data_capture": fields if fields is not None else default_fields,
			}
		],
	}
	if project_overrides:
		bundle["project"].update(project_overrides)
	if jtbd_overrides:
		bundle["jtbds"][0].update(jtbd_overrides)
	return bundle
