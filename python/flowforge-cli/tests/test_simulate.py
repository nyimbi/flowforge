"""Tests for ``flowforge simulate``."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


def test_simulate_plan_commit_log_shape(workflow_ok: Path) -> None:
	result = runner.invoke(
		app,
		["simulate", "--def", str(workflow_ok), "--events", "submit"],
	)
	assert result.exit_code == 0, result.output
	out = result.output
	# §10.4 sample-output markers
	assert "event 1/1: submit" in out
	assert "plan" in out
	assert "matched: submit" in out
	assert "commit" in out
	assert "create_entity claim" in out
	assert "notify claim.submitted" in out
	assert "→ state: review" in out
	assert "simulation complete" in out
	assert "audit events:" in out
	assert "outbox rows:" in out


def test_simulate_multiple_events_terminates(workflow_ok: Path) -> None:
	result = runner.invoke(
		app,
		[
			"simulate",
			"--def",
			str(workflow_ok),
			"--events",
			"submit,approve",
		],
	)
	assert result.exit_code == 0, result.output
	# The final event drives us into a terminal state.
	assert "event 2/2: approve" in result.output
	assert "→ state: done" in result.output


def test_simulate_with_context_fixture(workflow_ok: Path, tmp_path: Path) -> None:
	ctx = tmp_path / "ctx.json"
	ctx.write_text('{"hello": "world"}', encoding="utf-8")
	result = runner.invoke(
		app,
		[
			"simulate",
			"--def",
			str(workflow_ok),
			"--context",
			str(ctx),
			"--events",
			"submit",
		],
	)
	assert result.exit_code == 0, result.output


def test_simulate_unknown_event_reports_no_match(workflow_ok: Path) -> None:
	result = runner.invoke(
		app,
		["simulate", "--def", str(workflow_ok), "--events", "nope"],
	)
	# No match doesn't error — we still print the log and exit 0.
	assert result.exit_code == 0, result.output
	assert "no matching transition" in result.output
