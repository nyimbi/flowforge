"""Tests for ``flowforge tutorial`` — E-28 interactive walkthrough."""

from __future__ import annotations

import builtins
import json
import subprocess
from pathlib import Path

import pytest
from click import unstyle
from typer.testing import CliRunner

from flowforge_cli.commands import tutorial
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


def test_tutorial_dry_run_step3_and_step4_use_valid_cli_shapes(tmp_path: Path) -> None:
	out = tmp_path / "demo"
	r3 = runner.invoke(
		app,
		["tutorial", "--out", str(out), "--step", "3", "--no-pause", "--dry-run"],
	)
	assert "validate --def" in r3.output
	assert "generated/workflows/claim_intake/definition.json" in r3.output

	r4 = runner.invoke(
		app,
		["tutorial", "--out", str(out), "--step", "4", "--no-pause", "--dry-run"],
	)
	assert "simulate --def" in r4.output
	assert "--events submit --events approve" in r4.output
	assert "submit:{}" not in r4.output


def test_tutorial_dry_run_step5_shows_lint_command(tmp_path: Path) -> None:
	r = runner.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--step", "5", "--no-pause", "--dry-run"],
	)
	assert "jtbd" in r.output
	assert "lint" in r.output


def test_validated_cwd_accepts_absolute_existing_dir(tmp_path: Path) -> None:
	assert tutorial._validated_cwd(tmp_path) == tmp_path.resolve()


def test_validated_cwd_rejects_unresolved_relative_path(monkeypatch: pytest.MonkeyPatch) -> None:
	original_resolve = Path.resolve

	def fake_resolve(self: Path, strict: bool = False) -> Path:
		if self == Path("relative"):
			return Path("relative")
		return original_resolve(self, strict=strict)

	monkeypatch.setattr(Path, "resolve", fake_resolve)

	with pytest.raises(ValueError, match="cwd must be absolute"):
		tutorial._validated_cwd(Path("relative"))


def test_run_cmd_executes_with_validated_cwd(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	calls: list[tuple[list[str], Path]] = []

	def fake_run(args: list[str], *, cwd: Path, capture_output: bool) -> subprocess.CompletedProcess[str]:
		calls.append((args, cwd))
		assert capture_output is False
		return subprocess.CompletedProcess(args, 0)

	monkeypatch.setattr(tutorial.subprocess, "run", fake_run)

	assert tutorial._run_cmd(["flowforge", "--help"], cwd=tmp_path, dry_run=False) is True
	assert calls == [(["flowforge", "--help"], tmp_path.resolve())]


def test_run_cmd_returns_false_for_nonzero_exit(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_run(args: list[str], *, cwd: Path, capture_output: bool) -> subprocess.CompletedProcess[str]:
		return subprocess.CompletedProcess(args, 2)

	monkeypatch.setattr(tutorial.subprocess, "run", fake_run)

	assert tutorial._run_cmd(["flowforge", "bad"], cwd=tmp_path, dry_run=False) is False


def test_flowforge_uses_current_argv_when_console_script_missing(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(tutorial.shutil, "which", lambda _name: None)
	monkeypatch.setattr(tutorial.sys, "argv", ["/tmp/current-flowforge"])

	assert tutorial._flowforge() == "/tmp/current-flowforge"


def test_tutorial_step2_failure_reports_summary(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(tutorial, "_run_cmd", lambda *_args, **_kwargs: False)

	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "2", "--no-pause"])

	assert r.exit_code == 1
	assert "jtbd-generate failed" in r.output
	assert "Tutorial completed with 1 error" in r.output


def test_tutorial_step3_skips_when_workflow_missing(tmp_path: Path) -> None:
	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "3", "--no-pause"])

	assert r.exit_code == 0, r.output
	assert "Skipping validate" in r.output


def test_tutorial_step4_skips_when_workflow_missing(tmp_path: Path) -> None:
	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "4", "--no-pause"])

	assert r.exit_code == 0, r.output
	assert "Skipping simulate" in r.output


def test_tutorial_step5_skips_when_bundle_missing(tmp_path: Path) -> None:
	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "5", "--no-pause"])

	assert r.exit_code == 0, r.output
	assert "Skipping lint" in r.output


def test_tutorial_step3_failure_reports_summary(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	wf = tmp_path / "demo" / "generated" / "workflows" / "claim_intake" / "definition.json"
	wf.parent.mkdir(parents=True)
	wf.write_text("{}", encoding="utf-8")
	monkeypatch.setattr(tutorial, "_run_cmd", lambda *_args, **_kwargs: False)

	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "3", "--no-pause"])

	assert r.exit_code == 1
	assert "validate failed" in r.output


def test_tutorial_step4_failure_reports_summary(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	wf = tmp_path / "demo" / "generated" / "workflows" / "claim_intake" / "definition.json"
	wf.parent.mkdir(parents=True)
	wf.write_text("{}", encoding="utf-8")
	monkeypatch.setattr(tutorial, "_run_cmd", lambda *_args, **_kwargs: False)

	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "4", "--no-pause"])

	assert r.exit_code == 1
	assert "simulate failed" in r.output


def test_tutorial_step5_failure_reports_summary(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	bundle = tmp_path / "demo" / "bundle.json"
	bundle.parent.mkdir(parents=True)
	bundle.write_text("{}", encoding="utf-8")
	monkeypatch.setattr(tutorial, "_run_cmd", lambda *_args, **_kwargs: False)

	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "5", "--no-pause"])

	assert r.exit_code == 1
	assert "jtbd lint returned non-zero" in r.output


def test_tutorial_step5_runs_lint_when_bundle_exists(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	bundle = tmp_path / "demo" / "bundle.json"
	bundle.parent.mkdir(parents=True)
	bundle.write_text("{}", encoding="utf-8")
	calls: list[list[str]] = []

	def fake_run(args: list[str], **_kwargs: object) -> bool:
		calls.append(args)
		return True

	monkeypatch.setattr(tutorial, "_run_cmd", fake_run)

	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo"), "--step", "5", "--no-pause"])

	assert r.exit_code == 0, r.output
	assert calls == [["flowforge", "jtbd", "lint", "--bundle", str(bundle), "--warn-only"]]


def test_tutorial_pause_between_steps(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	pauses: list[str] = []
	monkeypatch.setattr(tutorial, "_run_cmd", lambda *_args, **_kwargs: True)
	monkeypatch.setattr(builtins, "input", lambda prompt: pauses.append(prompt) or "")

	r = runner.invoke(app, ["tutorial", "--out", str(tmp_path / "demo")])

	assert r.exit_code == 0, r.output
	assert len(pauses) == 4


def test_tutorial_footer_uses_selected_out_and_current_docs_path(tmp_path: Path) -> None:
	out = tmp_path / "custom-demo"
	r = runner.invoke(
		app,
		["tutorial", "--out", str(out), "--no-pause", "--dry-run"],
	)
	assert f"flowforge jtbd lint --bundle {out / 'bundle.json'}" in r.output
	assert "docs/flowforge-handbook.md" in r.output
	assert "flowforge-demo/bundle.json" not in r.output
	assert "framework/docs" not in r.output


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_tutorial_help() -> None:
	r = runner.invoke(app, ["tutorial", "--help"], terminal_width=140)
	assert r.exit_code == 0
	output = unstyle(r.output)
	assert "--out" in output
	assert "--step" in output
	assert "--dry-run" in output
