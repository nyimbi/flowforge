"""Tests for the generated Hypothesis property-suite generator."""

from __future__ import annotations

from typing import Any

from flowforge_cli.jtbd.generators import _fixture_registry, property_tests
from flowforge_cli.jtbd.normalize import normalize


def _bundle_with_guard() -> dict[str, Any]:
	return {
		"project": {
			"name": "property-demo",
			"package": "property_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {"roles": ["adjuster"], "permissions": []},
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
				],
				"edge_cases": [
					{
						"id": "large_loss",
						"condition": "loss_amount > 100000",
						"handle": "branch",
						"branch_to": "senior_triage",
					},
				],
			}
		],
	}


def test_extract_guard_vars_filters_invalid_shapes_and_sorts() -> None:
	"""Only non-empty ``context.<name>`` expr guard vars are retained."""
	transitions = (
		{
			"guards": [
				{"kind": "field", "expr": {"var": "context.ignored_kind"}},
				{"kind": "expr", "expr": {"var": 3}},
				{"kind": "expr", "expr": {"var": "tenant.id"}},
				{"kind": "expr", "expr": {"var": "context."}},
				{"kind": "expr", "expr": {"var": "context.beta"}},
				{"kind": "expr", "expr": {"var": "context.alpha"}},
				{"kind": "expr", "expr": {"var": "context.beta"}},
			]
		},
		{"guards": None},
		{},
	)
	assert property_tests._extract_guard_vars(transitions) == ("alpha", "beta")


def test_extract_workflow_events_filters_invalid_names_and_sorts() -> None:
	"""Event strategies only include non-empty string event names."""
	transitions = (
		{"event": "submit"},
		{"event": ""},
		{"event": 7},
		{"event": "approve"},
		{"event": "submit"},
		{},
	)
	assert property_tests._extract_workflow_events(transitions) == ("approve", "submit")


def test_generate_emits_pinned_seed_and_guard_strategy_inputs() -> None:
	bundle = normalize(_bundle_with_guard())
	jtbd = bundle.jtbds[0]

	out = property_tests.generate(bundle, jtbd)

	assert out.path == "backend/tests/claim_intake/test_claim_intake_properties.py"
	assert f"_SEED = {property_tests.compute_seed(jtbd.id)}" in out.content
	assert f"# 0x{property_tests.compute_seed_hex(jtbd.id)}" in out.content
	assert '"large_loss",' in out.content
	assert '"submit",' in out.content
	assert '"done",' in out.content


def test_fixture_registry_mirrors_generator_consumes() -> None:
	assert set(property_tests.CONSUMES) == set(_fixture_registry.get("property_tests"))
