"""Tests for the per-bundle OpenAPI 3.1 generator (W1 item 8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import openapi as gen
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


def _parse_yaml(content: str) -> dict[str, Any]:
	doc = yaml.safe_load(content)
	assert isinstance(doc, dict), "openapi.yaml top-level must be a mapping"
	return doc


# ---------------------------------------------------------------------------
# Generator output shape
# ---------------------------------------------------------------------------


def test_emits_single_openapi_yaml_at_bundle_root() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	assert out.path == "openapi.yaml"
	# One operation per JTBD => insurance has 1 jtbd, 1 path.
	doc = _parse_yaml(out.content)
	assert doc["openapi"] == "3.1.0"
	assert doc["info"]["title"] == "insurance-claim-demo"
	assert doc["info"]["version"] == "0.1.0"
	assert "/claim-intake/events" in doc["paths"]


def test_one_path_per_jtbd_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	out = gen.generate(bundle)
	doc = _parse_yaml(out.content)
	# 5 JTBDs in the building-permit bundle.
	assert len(doc["paths"]) == 5
	# Every JTBD is also tagged.
	tag_names = {t["name"] for t in doc["tags"]}
	assert tag_names == {jt.id for jt in bundle.jtbds}


def test_operation_carries_flowforge_extensions() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_yaml(gen.generate(bundle).content)
	op = doc["paths"]["/claim-intake/events"]["post"]
	# Tag matches jtbd.id.
	assert op["tags"] == ["claim_intake"]
	# Stable operationId derived from jtbd.id.
	assert op["operationId"] == "claim_intake_post_event"
	# x-permissions matches the derived permissions catalog.
	jt = bundle.jtbds[0]
	assert op["x-permissions"] == list(jt.permissions)
	# x-audit-topics matches derive_audit_topics output.
	assert op["x-audit-topics"] == list(jt.audit_topics)


def test_request_body_payload_schema_is_derived_from_data_capture() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_yaml(gen.generate(bundle).content)
	body_schema = doc["paths"]["/claim-intake/events"]["post"]["requestBody"][
		"content"
	]["application/json"]["schema"]
	payload_schema = body_schema["properties"]["payload"]
	props = payload_schema["properties"]
	# Every data_capture field shows up as a payload property.
	jt = bundle.jtbds[0]
	for f in jt.fields:
		assert f.id in props, f"missing field {f.id}"
	# additionalProperties: false on payload (closed object).
	assert payload_schema["additionalProperties"] is False
	# email kind got format: email.
	assert props["contact_email"]["format"] == "email"
	# date kind got format: date.
	assert props["loss_date"]["format"] == "date"
	# money kind is numeric.
	assert props["loss_amount"]["type"] == "number"
	# Required list is the sorted set of required field ids.
	required = sorted(f.id for f in jt.fields if f.required)
	assert payload_schema["required"] == required


def test_request_body_example_uses_deterministic_placeholders() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_yaml(gen.generate(bundle).content)
	example = doc["paths"]["/claim-intake/events"]["post"]["requestBody"]["content"][
		"application/json"
	]["example"]
	assert example["event"] == "submit"
	payload = example["payload"]
	assert payload["contact_email"] == "user@example.com"
	assert payload["loss_date"] == "2024-01-01"
	assert payload["loss_amount"] == 0


def test_responses_include_standard_status_codes() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_yaml(gen.generate(bundle).content)
	op = doc["paths"]["/claim-intake/events"]["post"]
	# 200 for success, 400 for validation, 403 for permissions, 409 for
	# concurrent fire — all documented.
	assert set(op["responses"].keys()) == {"200", "400", "403", "409"}


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


# ---------------------------------------------------------------------------
# Spec validity (structural checks — OpenAPI 3.1 meta-schema requires
# the optional ``openapi-spec-validator`` package which isn't a runtime
# dep; structural assertions cover the same invariants the meta-schema
# would reject on, which is sufficient for the generation-time gate)
# ---------------------------------------------------------------------------


def test_openapi_3_1_required_top_level_keys() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	doc = _parse_yaml(gen.generate(bundle).content)
	assert doc.get("openapi", "").startswith("3.1")
	assert "info" in doc and "title" in doc["info"] and "version" in doc["info"]
	assert "paths" in doc
	assert isinstance(doc["paths"], dict)


def test_every_path_has_a_post_operation() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	doc = _parse_yaml(gen.generate(bundle).content)
	for path, item in doc["paths"].items():
		assert "post" in item, f"{path} missing post op"
		assert "operationId" in item["post"]
		assert "responses" in item["post"]


def test_yaml_round_trip_preserves_structure() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	out = gen.generate(bundle)
	# Round-trip: yaml.safe_load(yaml.safe_dump(spec)) == spec.
	# We re-dump with the same flags to verify the canonical form
	# is a fixed point of safe_dump (a stricter determinism guarantee
	# than just two calls returning the same string).
	doc = yaml.safe_load(out.content)
	redumped = yaml.safe_dump(
		doc,
		default_flow_style=False,
		sort_keys=True,
		allow_unicode=True,
		width=4096,
	)
	assert redumped == out.content


# ---------------------------------------------------------------------------
# Fixture registry coverage primer
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	"""Module-level CONSUMES matches the fixture-registry entry."""
	registry_view = _fixture_registry.get("openapi")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_openapi() -> None:
	assert "openapi" in _fixture_registry.all_generators()
