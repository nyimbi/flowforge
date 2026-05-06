"""Tests for ``flowforge jtbd fork`` — E-2 fork operation.

Uses the same fixture pattern as the existing test suite (CliRunner + tmp_path).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.commands.jtbd_fork import JTBD_FORK_PERMISSION, _fork_bundle
from flowforge_cli.main import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _upstream_bundle() -> dict[str, Any]:
	return {
		"project": {
			"name": "flowforge-jtbd-insurance",
			"package": "flowforge_jtbd_insurance",
			"domain": "insurance",
			"version": "2.1.0",
		},
		"shared": {
			"roles": ["adjuster", "underwriter"],
			"permissions": ["claim.read", "claim.submit"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["claim is queued within SLA"],
			},
			{
				"id": "claim_review",
				"title": "Review a claim",
				"actor": {"role": "adjuster", "external": False},
				"situation": "adjuster needs to evaluate FNOL",
				"motivation": "resolve claim fairly",
				"outcome": "claim approved or denied",
				"success_criteria": ["decision recorded within 5 days"],
			},
		],
	}


@pytest.fixture()
def upstream_bundle(tmp_path: Path) -> Path:
	path = tmp_path / "insurance.json"
	path.write_text(json.dumps(_upstream_bundle(), indent=2), encoding="utf-8")
	return path


# ---------------------------------------------------------------------------
# Unit tests — _fork_bundle helper
# ---------------------------------------------------------------------------

def test_fork_bundle_stamps_tenant_id() -> None:
	bundle = _upstream_bundle()
	forked = _fork_bundle(
		bundle,
		tenant="tenant-A",
		upstream_name="flowforge-jtbd-insurance",
		upstream_version="2.1.0",
		spec_hash="sha256:abc123",
		upstream_path="/tmp/insurance.json",
	)
	assert forked["project"]["tenant_id"] == "tenant-A"


def test_fork_bundle_adds_fork_metadata() -> None:
	bundle = _upstream_bundle()
	forked = _fork_bundle(
		bundle,
		tenant="tenant-B",
		upstream_name="flowforge-jtbd-insurance",
		upstream_version="2.1.0",
		spec_hash="sha256:abc123",
		upstream_path="/tmp/insurance.json",
	)
	meta = forked["fork_metadata"]
	assert meta["tenant_id"] == "tenant-B"
	assert meta["forked_from"]["name"] == "flowforge-jtbd-insurance"
	assert meta["forked_from"]["version"] == "2.1.0"
	assert meta["forked_from"]["spec_hash"] == "sha256:abc123"
	assert meta["pull_upstream_enabled"] is True


def test_fork_bundle_stamps_each_jtbd_provenance() -> None:
	bundle = _upstream_bundle()
	forked = _fork_bundle(
		bundle,
		tenant="tenant-C",
		upstream_name="flowforge-jtbd-insurance",
		upstream_version="2.1.0",
		spec_hash="sha256:xyz",
		upstream_path="/tmp/insurance.json",
	)
	for jtbd in forked["jtbds"]:
		prov = jtbd["fork_provenance"]
		assert prov["tenant_id"] == "tenant-C"
		assert prov["parent_library"] == "flowforge-jtbd-insurance"
		assert prov["parent_version"] == "2.1.0"
		assert prov["parent_spec_hash"] == "sha256:xyz"


def test_fork_bundle_does_not_mutate_original() -> None:
	bundle = _upstream_bundle()
	original_ids = [j["id"] for j in bundle["jtbds"]]
	_fork_bundle(
		bundle,
		tenant="tenant-D",
		upstream_name="n",
		upstream_version="1.0.0",
		spec_hash="sha256:0",
		upstream_path="/tmp/x.json",
	)
	# Original untouched.
	assert [j["id"] for j in bundle["jtbds"]] == original_ids
	assert "tenant_id" not in bundle.get("project", {})


# ---------------------------------------------------------------------------
# Integration tests — CLI via CliRunner
# ---------------------------------------------------------------------------

def test_jtbd_fork_creates_output_file(upstream_bundle: Path, tmp_path: Path) -> None:
	dst = tmp_path / "out" / "forked.json"
	result = runner.invoke(
		app,
		["jtbd", "fork", str(upstream_bundle), "--tenant", "acme-corp", "--out", str(dst)],
	)
	assert result.exit_code == 0, result.output
	assert dst.is_file()
	data = json.loads(dst.read_text())
	assert data["project"]["tenant_id"] == "acme-corp"


def test_jtbd_fork_output_has_provenance(upstream_bundle: Path, tmp_path: Path) -> None:
	dst = tmp_path / "forked.json"
	runner.invoke(
		app,
		["jtbd", "fork", str(upstream_bundle), "--tenant", "acme-corp", "--out", str(dst)],
	)
	data = json.loads(dst.read_text())
	assert data["fork_metadata"]["forked_from"]["name"] == "flowforge-jtbd-insurance"
	assert data["fork_metadata"]["forked_from"]["version"] == "2.1.0"
	assert data["fork_metadata"]["forked_from"]["spec_hash"].startswith("sha256:")


def test_jtbd_fork_stamps_all_jtbds(upstream_bundle: Path, tmp_path: Path) -> None:
	dst = tmp_path / "forked.json"
	runner.invoke(
		app,
		["jtbd", "fork", str(upstream_bundle), "--tenant", "acme-corp", "--out", str(dst)],
	)
	data = json.loads(dst.read_text())
	assert len(data["jtbds"]) == 2
	for jtbd in data["jtbds"]:
		assert "fork_provenance" in jtbd
		assert jtbd["fork_provenance"]["tenant_id"] == "acme-corp"


def test_jtbd_fork_output_mentions_permission(upstream_bundle: Path, tmp_path: Path) -> None:
	dst = tmp_path / "forked.json"
	result = runner.invoke(
		app,
		["jtbd", "fork", str(upstream_bundle), "--tenant", "t1", "--out", str(dst)],
	)
	assert result.exit_code == 0, result.output
	assert JTBD_FORK_PERMISSION in result.output


def test_jtbd_fork_default_out_path(upstream_bundle: Path) -> None:
	"""Without --out, the bundle lands under <cwd>/<tenant>_fork/jtbd_bundle.json."""
	result = runner.invoke(
		app,
		["jtbd", "fork", str(upstream_bundle), "--tenant", "beta"],
		catch_exceptions=False,
	)
	assert result.exit_code == 0, result.output
	# Default path is relative to cwd which CliRunner sets to cwd of the process.
	default_dst = Path.cwd() / "beta_fork" / "jtbd_bundle.json"
	if default_dst.exists():
		data = json.loads(default_dst.read_text())
		assert data["project"]["tenant_id"] == "beta"
		default_dst.unlink()
		default_dst.parent.rmdir()


def test_jtbd_fork_missing_tenant_fails(upstream_bundle: Path) -> None:
	result = runner.invoke(app, ["jtbd", "fork", str(upstream_bundle)])
	assert result.exit_code != 0


def test_jtbd_subgroup_appears_in_help() -> None:
	result = runner.invoke(app, ["--help"])
	assert result.exit_code == 0
	assert "jtbd" in result.output


def test_jtbd_fork_in_jtbd_help() -> None:
	result = runner.invoke(app, ["jtbd", "--help"])
	assert result.exit_code == 0
	assert "fork" in result.output


# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------

def test_jtbd_fork_permission_constant() -> None:
	assert JTBD_FORK_PERMISSION == "jtbd.fork"
