"""Tests for ``flowforge tutorial`` — E-28 interactive walkthrough."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# --dry-run mode (no files written, all steps shown)
# ---------------------------------------------------------------------------


def test_tutorial_dry_run_all_steps(tmp_path: Path) -> None:
	r = runner.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--no-pause", "--dry-run"],
	)
	assert r.exit_code == 0, r.output
	for n in range(1, 6):
		assert f"Step {n}/5" in r.output
	assert "Tutorial complete" in r.output


def test_tutorial_dry_run_prints_banner(tmp_path: Path) -> None:
	r = runner.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--no-pause", "--dry-run"],
	)
	assert "flowforge interactive tutorial" in r.output


def test_tutorial_dry_run_mentions_output_dir(tmp_path: Path) -> None:
	out = tmp_path / "my-demo"
	r = runner.invoke(
		app,
		["tutorial", "--out", str(out), "--no-pause", "--dry-run"],
	)
	assert str(out) in r.output


# ---------------------------------------------------------------------------
# Step 1 actually writes bundle.json
# ---------------------------------------------------------------------------


def test_tutorial_step1_writes_bundle(tmp_path: Path) -> None:
	out = tmp_path / "demo"
	r = runner.invoke(
		app,
		["tutorial", "--out", str(out), "--step", "1", "--no-pause"],
	)
	assert r.exit_code == 0, r.output
	bundle = out / "bundle.json"
	assert bundle.is_file()
	data = json.loads(bundle.read_text())
	assert data["project"]["package"] == "insurance_demo"
	assert any(j["id"] == "claim_intake" for j in data["jtbds"])


def test_tutorial_step1_bundle_has_data_capture(tmp_path: Path) -> None:
	out = tmp_path / "demo"
	runner.invoke(app, ["tutorial", "--out", str(out), "--step", "1", "--no-pause"])
	data = json.loads((out / "bundle.json").read_text())
	fields = data["jtbds"][0]["data_capture"]
	field_ids = [f["id"] for f in fields]
	assert "claimant_name" in field_ids
	assert "loss_amount" in field_ids


def test_tutorial_step1_shows_bundle_summary(tmp_path: Path) -> None:
	out = tmp_path / "demo"
	r = runner.invoke(app, ["tutorial", "--out", str(out), "--step", "1", "--no-pause"])
	assert "claim_intake" in r.output
	assert "policyholder" in r.output


# ---------------------------------------------------------------------------
# Single-step selection
# ---------------------------------------------------------------------------


def test_tutorial_invalid_step_exits_1(tmp_path: Path) -> None:
	r = runner.invoke(
		app,
		["tutorial", "--out", str(tmp_path), "--step", "9", "--no-pause"],
	)
	assert r.exit_code == 1


def test_tutorial_step1_only_runs_one_step(tmp_path: Path) -> None:
	out = tmp_path / "demo"
	r = runner.invoke(app, ["tutorial", "--out", str(out), "--step", "1", "--no-pause"])
	# Only step 1 header appears
	assert "Step 1/5" in r.output
	assert "Step 2/5" not in r.output


# ---------------------------------------------------------------------------
# Dry-run per step
# ---------------------------------------------------------------------------


def test_tutorial_dry_run_step2_shows_command(tmp_path: Path) -> None:
	r = runner.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--step", "2", "--no-pause", "--dry-run"],
	)
	assert "jtbd-generate" in r.output
	assert "dry-run" in r.output


def test_tutorial_dry_run_step5_shows_lint_command(tmp_path: Path) -> None:
	r = runner.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--step", "5", "--no-pause", "--dry-run"],
	)
	assert "jtbd" in r.output
	assert "lint" in r.output


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_tutorial_help() -> None:
	r = runner.invoke(app, ["tutorial", "--help"])
	assert r.exit_code == 0
	assert "--out" in r.output
	assert "--step" in r.output
	assert "--dry-run" in r.output
