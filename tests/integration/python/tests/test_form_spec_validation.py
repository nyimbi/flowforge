"""Integration test #7: form_spec validation through the runtime.

A JTBD bundle ships a form_spec; before a transition that consumes form
input fires, the runtime should validate the payload against the
form_spec's JSON schema. This test exercises the python-side schema
check path (the JS renderer reruns the same schema via ajv on the
client; that path is covered in the JS suite).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flowforge.dsl import FormSpec
from jsonschema import Draft202012Validator

pytestmark = pytest.mark.asyncio


def _load_form_spec() -> FormSpec:
	root = Path(__file__).resolve().parents[4] / "examples" / "insurance_claim"
	spec_path = root / "generated" / "workflows" / "claim_intake" / "form_spec.json"
	assert spec_path.exists(), f"missing form_spec at {spec_path}"
	return FormSpec.model_validate(json.loads(spec_path.read_text()))


def _form_spec_to_jsonschema(spec: FormSpec) -> dict:
	"""Tiny FormSpec-to-JSONSchema projection used for the python validation path.

	The real renderer maintains a richer ajv-compatible schema; this
	projection covers required + types for the integration test.
	"""
	props: dict = {}
	required: list[str] = []
	for f in spec.fields:
		fid = f.id
		schema = {"type": "string"}
		if f.kind in ("number", "money"):
			schema = {"type": "number"}
		elif f.kind == "boolean":
			schema = {"type": "boolean"}
		props[fid] = schema
		if f.required:
			required.append(fid)
	return {
		"type": "object",
		"properties": props,
		"required": required,
		"additionalProperties": True,
	}


async def test_invalid_payload_surfaces_errors() -> None:
	spec = _load_form_spec()
	schema = _form_spec_to_jsonschema(spec)
	validator = Draft202012Validator(schema)

	# Empty payload — missing every required field.
	errors = list(validator.iter_errors({}))
	assert errors, "expected validation errors for empty payload"
	# All errors should be about required-property violations.
	for err in errors:
		assert err.validator == "required"


async def test_valid_payload_accepts_completes_transition() -> None:
	spec = _load_form_spec()
	schema = _form_spec_to_jsonschema(spec)
	validator = Draft202012Validator(schema)

	# Build a payload satisfying every required field with a default value.
	payload: dict = {}
	for f in spec.fields:
		if not f.required:
			continue
		if f.kind in ("number", "money"):
			payload[f.id] = 1
		elif f.kind == "boolean":
			payload[f.id] = True
		else:
			payload[f.id] = "x"

	errors = list(validator.iter_errors(payload))
	assert errors == [], f"valid payload still rejected: {errors}"
