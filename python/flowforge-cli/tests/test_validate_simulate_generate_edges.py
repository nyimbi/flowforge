from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge.compiler.validator import ValidationReport
from flowforge.dsl import Effect, WorkflowDef
from flowforge.engine.fire import FireResult, Instance
from flowforge_cli.commands import jtbd_generate, simulate
from flowforge_cli.commands.validate import _check_one, _print_report
from flowforge_cli.jtbd import GeneratedFile
from flowforge_cli.main import app


runner = CliRunner()


def test_validate_check_one_reports_read_errors(tmp_path: Path) -> None:
	path = tmp_path / "not-a-map.json"
	path.write_text("[1, 2, 3]", encoding="utf-8")

	header, report = _check_one(path)

	assert header == str(path)
	assert report.errors
	assert "could not read" in report.errors[0]


def test_validate_print_report_includes_success_warnings(capsys: pytest.CaptureFixture[str]) -> None:
	report = ValidationReport(warnings=["optional warning"])

	_print_report(report)

	out = capsys.readouterr().out
	assert "schema valid" in out
	assert "optional warning" in out


def test_validate_print_report_includes_error_warnings(capsys: pytest.CaptureFixture[str]) -> None:
	report = ValidationReport(errors=["bad graph"], warnings=["still useful"])

	_print_report(report)

	out = capsys.readouterr().out
	assert "bad graph" in out
	assert "still useful" in out


def test_simulate_flattens_repeatable_comma_separated_events() -> None:
	assert simulate._flatten_events([" submit,approve ", "", " close "]) == ["submit", "approve", "close"]


def test_simulate_reports_unknown_matched_transition(
	workflow_ok: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	instance = Instance(id="i1", def_key="claim_intake", def_version="1.0.0", state="review")
	result = FireResult(
		instance=instance,
		matched_transition_id="missing-transition",
		planned_effects=[],
		new_state="review",
		terminal=False,
	)

	async def fake_run(
		_wd: WorkflowDef,
		_initial_context: dict[str, object],
		_events: list[str],
	) -> list[tuple[str, FireResult]]:
		return [("submit", result)]

	monkeypatch.setattr(simulate, "_run", fake_run)

	r = runner.invoke(app, ["simulate", "--def", str(workflow_ok), "--events", "submit"])

	assert r.exit_code == 0, r.output
	assert "matched: missing-transition" in r.output


def test_simulate_run_stops_after_terminal_event(workflow_ok: Path) -> None:
	wd = WorkflowDef.model_validate(json.loads(workflow_ok.read_text(encoding="utf-8")))

	results = asyncio.run(simulate._run(wd, {}, ["submit", "approve", "ignored"]))

	assert [event for event, _ in results] == ["submit", "approve"]
	assert results[-1][1].terminal is True


def test_simulate_log_effects_covers_supported_effect_kinds(capsys: pytest.CaptureFixture[str]) -> None:
	instance = Instance(id="i1", def_key="wf", def_version="1", state="s")
	result = FireResult(
		instance=instance,
		matched_transition_id="t1",
		planned_effects=[
			Effect(kind="set", target="context.status", expr="ready"),
			Effect(kind="audit", template="audit.template"),
			Effect(kind="emit_signal", signal="done"),
			Effect(kind="start_subworkflow", subworkflow_key="child"),
			Effect(kind="compensate", compensation_kind="undo"),
			Effect(kind="http_call", url="https://example.test/hook"),
			Effect(kind="update_entity"),
		],
		new_state="s",
		terminal=False,
	)

	simulate._log_effects(result)

	out = capsys.readouterr().out
	assert "set context.status = 'ready'" in out
	assert "audit audit.template" in out
	assert "emit_signal done" in out
	assert "start_subworkflow child" in out
	assert "compensate undo" in out
	assert "http_call https://example.test/hook" in out
	assert "update_entity" in out


def test_jtbd_generate_rejects_non_empty_target_without_force(
	jtbd_bundle: Path,
	tmp_path: Path,
) -> None:
	out = tmp_path / "out"
	out.mkdir()
	(out / "existing.txt").write_text("keep", encoding="utf-8")

	r = runner.invoke(app, ["jtbd-generate", "--jtbd", str(jtbd_bundle), "--out", str(out)])

	assert r.exit_code != 0
	assert "exists and is not empty" in r.output


def test_jtbd_generate_wraps_generator_value_errors(
	jtbd_bundle: Path,
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def fake_generate(*_args: object, **_kwargs: object) -> list[GeneratedFile]:
		raise ValueError("invalid bundle")

	monkeypatch.setattr(jtbd_generate, "generate", fake_generate)

	r = runner.invoke(app, ["jtbd-generate", "--jtbd", str(jtbd_bundle), "--out", str(tmp_path / "out")])

	assert r.exit_code != 0
	assert "invalid bundle" in r.output


def test_jtbd_generate_force_allows_non_empty_target(
	jtbd_bundle: Path,
	tmp_path: Path,
) -> None:
	out = tmp_path / "out"
	out.mkdir()
	(out / "existing.txt").write_text("keep", encoding="utf-8")

	r = runner.invoke(app, ["jtbd-generate", "--jtbd", str(jtbd_bundle), "--out", str(out), "--force"])

	assert r.exit_code == 0, r.output
	assert (out / "existing.txt").read_text(encoding="utf-8") == "keep"
	assert "jtbd-generate:" in r.output
