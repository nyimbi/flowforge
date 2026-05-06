"""Tests for the project-level llm.txt generator (E-29).

Covers:

* Pure rendering (``flowforge_cli.llmtxt.render_llmtxt``) — content
  shape, JTBD enumeration, role / permission listing, deterministic
  timestamp via injected clock.
* The standalone CLI (``flowforge generate-llmtxt``) — happy path,
  default paths, --force, --bundle-label, missing-bundle exit, refuse-
  to-overwrite-without-force.
* Integration with ``flowforge new --emit-llmtxt`` — flag opt-in,
  default new omits, output path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.llmtxt import render_llmtxt, write_llmtxt
from flowforge_cli.main import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _default_jtbds() -> list[dict[str, Any]]:
	return [
		{
			"id": "claim_intake",
			"version": "1.0.0",
			"actor": {"role": "intake_clerk"},
			"situation": "A claimant submits a new claim through the portal.",
			"motivation": "Capture intake details and route for triage.",
			"outcome": "A claim record exists with status=intake.",
			"success_criteria": [
				"claim_id generated within 5 seconds",
				"intake form persisted",
			],
			"requires": [],
			"compliance": ["SOX"],
			"data_sensitivity": ["PII"],
		},
	]


def _bundle(jtbds: list[dict[str, Any]] | None = None) -> dict[str, Any]:
	return {
		"project": {
			"name": "demo-claims",
			"package": "demo_claims",
			"domain": "insurance",
			"tenancy": "multi",
			"languages": ["en", "fr"],
		},
		"shared": {
			"roles": ["intake_clerk", "adjuster"],
			"permissions": ["claim.submit", "claim.approve"],
		},
		"jtbds": _default_jtbds() if jtbds is None else jtbds,
	}


def _frozen_clock() -> datetime:
	return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture
def sample_bundle_file(tmp_path: Path) -> Path:
	bundle_path = tmp_path / "jtbd-bundle.json"
	bundle_path.write_text(json.dumps(_bundle()))
	return bundle_path


# ---------------------------------------------------------------------------
# render_llmtxt — pure function
# ---------------------------------------------------------------------------


def test_render_llmtxt_includes_project_facts() -> None:
	out = render_llmtxt(_bundle(), now=_frozen_clock)
	assert "demo-claims" in out
	assert "demo_claims" in out
	assert "insurance" in out
	assert "Tenancy mode**: multi" in out
	assert "Languages**: en, fr" in out
	assert "JTBD count**: 1" in out
	assert "2026-01-02 03:04:05" in out


def test_render_llmtxt_lists_each_jtbd() -> None:
	bundle = _bundle(jtbds=[
		{
			"id": "a",
			"version": "1.0.0",
			"actor": {"role": "clerk"},
			"situation": "s1",
			"motivation": "m1",
			"outcome": "o1",
			"success_criteria": ["sc1"],
		},
		{
			"id": "b",
			"version": "2.1.0",
			"actor": {"role": "manager", "tier": 2},
			"situation": "s2",
			"motivation": "m2",
			"outcome": "o2",
			"success_criteria": ["sc2"],
			"compliance": ["HIPAA"],
		},
	])
	out = render_llmtxt(bundle, now=_frozen_clock)
	assert "### a@1.0.0" in out
	assert "### b@2.1.0" in out
	assert "tier 2" in out
	assert "HIPAA" in out
	# Each JTBD links to its definition file.
	assert "workflows/a/definition.json" in out
	assert "workflows/b/definition.json" in out


def test_render_llmtxt_lists_shared_roles_and_permissions() -> None:
	out = render_llmtxt(_bundle(), now=_frozen_clock)
	assert "intake_clerk, adjuster" in out
	assert "claim.submit, claim.approve" in out


def test_render_llmtxt_handles_empty_shared_block() -> None:
	bundle = _bundle()
	bundle["shared"] = {}
	out = render_llmtxt(bundle, now=_frozen_clock)
	assert "(none declared)" in out


def test_render_llmtxt_records_bundle_path_label() -> None:
	out = render_llmtxt(
		_bundle(),
		bundle_path="custom/path/to/bundle.yaml",
		now=_frozen_clock,
	)
	assert "custom/path/to/bundle.yaml" in out


def test_render_llmtxt_requires_project_name_and_package() -> None:
	bundle = _bundle()
	del bundle["project"]["name"]
	with pytest.raises(AssertionError):
		render_llmtxt(bundle)


def test_render_llmtxt_handles_no_jtbds() -> None:
	bundle = _bundle(jtbds=[])
	out = render_llmtxt(bundle, now=_frozen_clock)
	assert "JTBD count**: 0" in out
	# No KeyError / template crash on empty jtbds.
	assert "<jtbd>" in out  # placeholder in the simulate sample command


def test_write_llmtxt_writes_to_disk(tmp_path: Path) -> None:
	dst = tmp_path / "nested" / "llm.txt"
	written = write_llmtxt(_bundle(), out_path=dst, now=_frozen_clock)
	assert written == dst
	assert dst.exists()
	assert "demo-claims" in dst.read_text()


# ---------------------------------------------------------------------------
# CLI: generate-llmtxt
# ---------------------------------------------------------------------------


def test_generate_llmtxt_writes_file(sample_bundle_file: Path, tmp_path: Path) -> None:
	out_path = tmp_path / "llm.txt"
	result = runner.invoke(app, [
		"generate-llmtxt",
		"--bundle", str(sample_bundle_file),
		"--out", str(out_path),
	])
	assert result.exit_code == 0, result.output
	assert "wrote" in result.output
	assert out_path.exists()
	assert "demo-claims" in out_path.read_text()


def test_generate_llmtxt_missing_bundle_exits_1(tmp_path: Path) -> None:
	result = runner.invoke(app, [
		"generate-llmtxt",
		"--bundle", str(tmp_path / "nope.json"),
		"--out", str(tmp_path / "llm.txt"),
	])
	assert result.exit_code == 1
	assert "not found" in result.output


def test_generate_llmtxt_refuses_to_overwrite_without_force(
	sample_bundle_file: Path,
	tmp_path: Path,
) -> None:
	out_path = tmp_path / "llm.txt"
	out_path.write_text("pre-existing")
	result = runner.invoke(app, [
		"generate-llmtxt",
		"--bundle", str(sample_bundle_file),
		"--out", str(out_path),
	])
	assert result.exit_code == 1
	assert "already exists" in result.output
	# Original content preserved.
	assert out_path.read_text() == "pre-existing"


def test_generate_llmtxt_force_overwrites(
	sample_bundle_file: Path,
	tmp_path: Path,
) -> None:
	out_path = tmp_path / "llm.txt"
	out_path.write_text("pre-existing")
	result = runner.invoke(app, [
		"generate-llmtxt",
		"--bundle", str(sample_bundle_file),
		"--out", str(out_path),
		"--force",
	])
	assert result.exit_code == 0
	assert "demo-claims" in out_path.read_text()


def test_generate_llmtxt_bundle_label_overrides_path(
	sample_bundle_file: Path,
	tmp_path: Path,
) -> None:
	out_path = tmp_path / "llm.txt"
	result = runner.invoke(app, [
		"generate-llmtxt",
		"--bundle", str(sample_bundle_file),
		"--out", str(out_path),
		"--bundle-label", "workflows/jtbd_bundle.json",
	])
	assert result.exit_code == 0
	text = out_path.read_text()
	assert "workflows/jtbd_bundle.json" in text
	assert str(sample_bundle_file) not in text


# ---------------------------------------------------------------------------
# Integration: flowforge new --emit-llmtxt
# ---------------------------------------------------------------------------


def _new_bundle_for_scaffold(tmp_path: Path) -> Path:
	"""Build a bundle that satisfies the JTBD JSON schema enforced by `new`."""
	bundle = {
		"project": {
			"name": "demo-claims",
			"package": "demo_claims",
			"domain": "insurance",
		},
		"shared": {
			"roles": ["intake_clerk"],
			"permissions": ["claim.submit"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"actor": {"role": "intake_clerk"},
				"situation": "A claimant submits a new claim.",
				"motivation": "Capture intake.",
				"outcome": "claim record exists.",
				"success_criteria": ["claim_id generated"],
			},
		],
	}
	path = tmp_path / "input-bundle.json"
	path.write_text(json.dumps(bundle))
	return path


def test_new_with_emit_llmtxt_writes_llm_txt(tmp_path: Path) -> None:
	bundle_path = _new_bundle_for_scaffold(tmp_path)
	result = runner.invoke(app, [
		"new", "demo-claims",
		"--jtbd", str(bundle_path),
		"--out", str(tmp_path / "scaffold"),
		"--emit-llmtxt",
	])
	assert result.exit_code == 0, result.output
	llmtxt = tmp_path / "scaffold" / "demo-claims" / "llm.txt"
	assert llmtxt.exists(), result.output
	text = llmtxt.read_text()
	assert "demo-claims" in text
	assert "claim_intake" in text
	# Bundle path embedded in the rendered text points at the project-
	# relative copy, not the source bundle the user passed in.
	assert "workflows/jtbd_bundle.json" in text


def test_new_without_emit_llmtxt_omits_file(tmp_path: Path) -> None:
	bundle_path = _new_bundle_for_scaffold(tmp_path)
	result = runner.invoke(app, [
		"new", "demo-claims",
		"--jtbd", str(bundle_path),
		"--out", str(tmp_path / "scaffold"),
	])
	assert result.exit_code == 0, result.output
	llmtxt = tmp_path / "scaffold" / "demo-claims" / "llm.txt"
	assert not llmtxt.exists()
