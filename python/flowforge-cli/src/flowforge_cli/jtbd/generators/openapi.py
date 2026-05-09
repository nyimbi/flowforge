"""Per-bundle generator: emit ``openapi.yaml`` at the bundle root.

Bundle-derived OpenAPI 3.1 spec, one operation per JTBD's
``POST /<url_segment>/events`` route. The spec is produced directly
from the normalized bundle — no FastAPI introspection — so downstream
tooling (client SDK generation, contract tests, postman collections,
LLM tool descriptors) can consume it without booting the app.

Operations are tagged by ``jtbd_id``. Each operation carries two
flowforge-specific extensions:

* ``x-audit-topics``: list of audit topic strings the operation may
  emit (sourced from :func:`transforms.derive_audit_topics`).
* ``x-permissions``: list of permission strings the gate evaluates
  (sourced from :func:`transforms.derive_permissions`).

Request bodies derive a JSON-schema payload skeleton from each JTBD's
``data_capture`` fields; an ``example`` value is built deterministically
from each field's kind and (when present) its ``validation`` range.

Item 8 of :doc:`docs/improvements`, W1 of
:doc:`docs/v0.3.0-engineering-plan`. The fixture-registry primer at
:mod:`._fixture_registry` records the attribute paths this generator
reads; the bidirectional coverage test (Pre-mortem Scenario 1)
cross-checks generator and registry.
"""

from __future__ import annotations

from typing import Any

import yaml  # type: ignore[import-untyped]

from ..normalize import NormalizedBundle, NormalizedField, NormalizedJTBD
from .._types import GeneratedFile


# Bidirectional fixture-registry primer (executor residual risk #2 in
# v0.3.0-engineering-plan.md §11). Mirrors the entry in
# ``_fixture_registry._REGISTRY``; the W0+ test asserts they agree.
CONSUMES: tuple[str, ...] = (
	"jtbds[].audit_topics",
	"jtbds[].fields",
	"jtbds[].fields[].id",
	"jtbds[].fields[].kind",
	"jtbds[].fields[].label",
	"jtbds[].fields[].required",
	"jtbds[].fields[].validation",
	"jtbds[].id",
	"jtbds[].permissions",
	"jtbds[].title",
	"jtbds[].url_segment",
	"project.name",
)


# Static stub used as the canonical info.version for the bundle. Bundles
# don't carry a version field today; pin to a stable string so the spec
# regenerates byte-identically. Hosts that need a real version should
# rewrite this field downstream rather than re-derive it here.
_INFO_VERSION = "0.1.0"


# Deterministic, kind-keyed JSON-schema fragments. Keep this dict
# closed: the form_spec generator already enumerates the legal kinds,
# and we want unknown kinds to fall through to a string default rather
# than silently emit ``additionalProperties: true``.
_KIND_TO_SCHEMA: dict[str, dict[str, Any]] = {
	"text": {"type": "string"},
	"textarea": {"type": "string"},
	"email": {"type": "string", "format": "email"},
	"phone": {"type": "string"},
	"date": {"type": "string", "format": "date"},
	"datetime": {"type": "string", "format": "date-time"},
	"url": {"type": "string", "format": "uri"},
	"number": {"type": "number"},
	"integer": {"type": "integer"},
	"money": {"type": "number"},
	"boolean": {"type": "boolean"},
	"address": {"type": "string"},
	"select": {"type": "string"},
	"multiselect": {"type": "array", "items": {"type": "string"}},
}


# Deterministic placeholder values per kind. The ``example`` block is
# advisory in OpenAPI but downstream tooling (Postman, contract tests)
# fills request bodies from it, so each field needs a value that
# round-trips through the field's JSON-schema fragment.
_KIND_TO_EXAMPLE: dict[str, Any] = {
	"text": "example",
	"textarea": "Example description text.",
	"email": "user@example.com",
	"phone": "+15555550100",
	"date": "2024-01-01",
	"datetime": "2024-01-01T00:00:00Z",
	"url": "https://example.com",
	"number": 0,
	"integer": 0,
	"money": 0,
	"boolean": False,
	"address": "1 Example St",
	"select": "option_a",
	"multiselect": [],
}


def _field_schema(field: NormalizedField) -> dict[str, Any]:
	"""Translate one ``data_capture`` field into a JSON-schema fragment.

	``validation`` keys recognised here:

	* ``min``/``max`` → ``minimum``/``maximum`` for numeric kinds,
	  ``minLength``/``maxLength`` for string-shaped kinds.
	* ``pattern`` → ``pattern`` (string kinds only).
	* ``enum`` → ``enum`` (passed through).

	Unknown validation keys are dropped silently; any future expansion
	belongs in the form_spec validator first, then mirrored here.
	"""

	base = dict(_KIND_TO_SCHEMA.get(field.kind, {"type": "string"}))
	base["title"] = field.label
	base["x-flowforge-kind"] = field.kind

	v = field.validation or {}
	is_numeric = base.get("type") in ("number", "integer")
	is_stringlike = base.get("type") == "string"
	if "min" in v:
		if is_numeric:
			base["minimum"] = v["min"]
		elif is_stringlike:
			base["minLength"] = v["min"]
	if "max" in v:
		if is_numeric:
			base["maximum"] = v["max"]
		elif is_stringlike:
			base["maxLength"] = v["max"]
	if "pattern" in v and is_stringlike:
		base["pattern"] = v["pattern"]
	if "enum" in v:
		base["enum"] = list(v["enum"])
	return base


def _field_example(field: NormalizedField) -> Any:
	"""Deterministic example value for *field* — used by the operation example."""

	v = field.validation or {}
	# Honour validation min for numeric kinds so the example sits
	# inside any documented range.
	if "min" in v and field.kind in ("number", "integer", "money"):
		return v["min"]
	if "enum" in v:
		options = list(v["enum"])
		if options:
			return options[0]
	return _KIND_TO_EXAMPLE.get(field.kind, "")


def _payload_schema(jtbd: NormalizedJTBD) -> dict[str, Any]:
	"""Build the ``payload`` object schema from a JTBD's ``data_capture``."""

	properties: dict[str, dict[str, Any]] = {}
	required: list[str] = []
	# Sort by id so the emitted spec is stable regardless of declaration
	# order in the bundle.
	for f in sorted(jtbd.fields, key=lambda x: x.id):
		properties[f.id] = _field_schema(f)
		if f.required:
			required.append(f.id)
	schema: dict[str, Any] = {
		"type": "object",
		"additionalProperties": False,
		"properties": properties,
	}
	if required:
		schema["required"] = sorted(required)
	return schema


def _payload_example(jtbd: NormalizedJTBD) -> dict[str, Any]:
	"""Deterministic example payload for the operation."""

	out: dict[str, Any] = {}
	for f in sorted(jtbd.fields, key=lambda x: x.id):
		out[f.id] = _field_example(f)
	return out


def _operation(jtbd: NormalizedJTBD) -> dict[str, Any]:
	"""Build a single OpenAPI operation object for one JTBD."""

	payload_schema = _payload_schema(jtbd)
	payload_example = _payload_example(jtbd)
	op: dict[str, Any] = {
		"operationId": f"{jtbd.id}_post_event",
		"summary": f"Fire an event for {jtbd.title}",
		"tags": [jtbd.id],
		"x-audit-topics": list(jtbd.audit_topics),
		"x-permissions": list(jtbd.permissions),
		"requestBody": {
			"required": True,
			"content": {
				"application/json": {
					"schema": {
						"type": "object",
						"additionalProperties": False,
						"required": ["event"],
						"properties": {
							"event": {
								"type": "string",
								"description": "Workflow event name.",
							},
							"payload": payload_schema,
						},
					},
					"example": {
						"event": "submit",
						"payload": payload_example,
					},
				},
			},
		},
		"responses": {
			"200": {
				"description": "Event accepted; engine returned the post-fire snapshot.",
				"content": {
					"application/json": {
						"schema": {
							"type": "object",
							"additionalProperties": True,
						},
					},
				},
			},
			"400": {
				"description": "Validation error — payload failed schema or expression guard.",
			},
			"403": {
				"description": "Permission denied — principal lacks one of the gate permissions.",
			},
			"409": {
				"description": "Concurrent fire rejected — another fire is in flight for this instance.",
			},
		},
	}
	return op


def _build_spec(bundle: NormalizedBundle) -> dict[str, Any]:
	"""Assemble the complete OpenAPI 3.1 document from *bundle*."""

	paths: dict[str, dict[str, Any]] = {}
	tags: list[dict[str, str]] = []
	# Sort JTBDs by id so iteration order is stable.
	for jt in sorted(bundle.jtbds, key=lambda j: j.id):
		paths[f"/{jt.url_segment}/events"] = {"post": _operation(jt)}
		tags.append({"name": jt.id, "description": jt.title})

	return {
		"openapi": "3.1.0",
		"info": {
			"title": bundle.project.name,
			"version": _INFO_VERSION,
			"description": (
				f"Bundle-derived OpenAPI spec for {bundle.project.name}. "
				"Generated by flowforge — do not edit by hand."
			),
		},
		"tags": tags,
		"paths": paths,
		"components": {
			"schemas": {},
		},
	}


def _dump_yaml(spec: dict[str, Any]) -> str:
	"""Serialise *spec* to a deterministic YAML string."""

	# ``sort_keys=True`` + ``default_flow_style=False`` is the canonical
	# deterministic combination for safe_dump. ``allow_unicode=True``
	# avoids escaping in case downstream tools embed non-ASCII labels.
	# ``width`` set high so long URLs / descriptions don't fold mid-line.
	return yaml.safe_dump(
		spec,
		default_flow_style=False,
		sort_keys=True,
		allow_unicode=True,
		width=4096,
	)


def generate(bundle: NormalizedBundle) -> GeneratedFile:
	"""Emit the bundle-level ``openapi.yaml`` document.

	One file at the bundle root, regardless of how many JTBDs the bundle
	declares — per the engineering plan's principle 2 (per-bundle
	generators must be aggregations).
	"""

	spec = _build_spec(bundle)
	content = _dump_yaml(spec)
	return GeneratedFile(path="openapi.yaml", content=content)
