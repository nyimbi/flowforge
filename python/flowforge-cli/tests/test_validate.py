"""Tests for ``flowforge validate``."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


def test_validate_ok_definition(workflow_ok: Path) -> None:
	result = runner.invoke(app, ["validate", "--def", str(workflow_ok)])
	assert result.exit_code == 0, result.output
	out = result.output
	assert "claim_intake@1.0.0" in out
	# Sample-output markers per §10.3
	assert "schema valid" in out
	assert "no unreachable states" in out
	assert "no dead-end transitions" in out
	assert "duplicate-priority check" in out
	assert "lookup-permission check" in out
	assert "subworkflow cycle check" in out
	assert "validation ok" in out


def test_validate_reports_errors(workflow_broken: Path) -> None:
	result = runner.invoke(app, ["validate", "--def", str(workflow_broken)])
	assert result.exit_code == 1, result.output
	out = result.output
	# duplicate priority detected
	assert "duplicate priority" in out
	# unreachable state detected
	assert "unreachable" in out
	assert "validation failed" in out


def test_validate_root_directory(workflows_dir_ok: Path) -> None:
	result = runner.invoke(app, ["validate", "--root", str(workflows_dir_ok)])
	assert result.exit_code == 0, result.output
	out = result.output
	assert "checking 2 definitions" in out
	assert "claim_intake@1.0.0" in out
	assert "claim_payout@1.0.0" in out


def test_validate_no_definitions_found(tmp_path: Path) -> None:
	result = runner.invoke(app, ["validate", "--root", str(tmp_path / "nope")])
	assert result.exit_code == 1
	assert "no workflow definitions" in result.output
