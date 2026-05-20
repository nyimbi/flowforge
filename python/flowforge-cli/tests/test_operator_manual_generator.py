"""Tests for the per-JTBD operator manual generator."""

from __future__ import annotations

import json
from pathlib import Path

from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import operator_manual as gen
from flowforge_cli.jtbd.normalize import normalize


_INSURANCE_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "insurance_claim"
	/ "jtbd-bundle.json"
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


def test_generate_emits_operator_manual_mdx_for_jtbd() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jtbd,) = bundle.jtbds

	out = gen.generate(bundle, jtbd)

	assert out.path == "docs/jtbd/claim_intake.mdx"
	assert "# File an insurance claim (FNOL)" in out.content
	assert "```mermaid" in out.content
	assert "stateDiagram-v2" in out.content


def test_permission_summary_handles_shared_permission_without_prefix() -> None:
	assert gen._permission_summary("claim.read") == "read records owned by this JTBD"
	assert gen._permission_summary("platform.admin") == (
		"perform `admin` on records for this JTBD"
	)
	assert gen._permission_summary("global_admin") == (
		"holds the shared permission `global_admin`"
	)


def test_audit_topic_summary_handles_returned_edge_case() -> None:
	assert gen._audit_topic_summary("claim_intake.more_info_returned", "claim_intake") == (
		"Loop-back event — the `more info` branch returned the record for revision."
	)


def test_consumes_declared_in_fixture_registry() -> None:
	assert _fixture_registry.get("operator_manual") == gen.CONSUMES


def test_fixture_registry_lists_operator_manual() -> None:
	assert "operator_manual" in _fixture_registry.all_generators()
