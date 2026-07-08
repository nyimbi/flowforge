"""Tests for the Rich CLI UX additions."""

from __future__ import annotations

import json
from pathlib import Path

from click import unstyle
from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


def test_root_help_lists_global_verbosity_and_new_commands() -> None:
	result = runner.invoke(app, ["--help"], terminal_width=140)

	assert result.exit_code == 0, result.output
	output = unstyle(result.output)
	assert "--verbose" in output
	assert "--quiet" in output
	assert "status" in output
	assert "lint-jtbd" in output
	assert "new-workflow" in output


def test_global_verbose_and_quiet_conflict() -> None:
	result = runner.invoke(app, ["--verbose", "--quiet", "status"])

	assert result.exit_code == 2
	assert "Error" in result.output
	assert "Hint" in result.output


def test_status_json_reports_packages_and_tests(tmp_path: Path) -> None:
	(tmp_path / "pyproject.toml").write_text("[project]\nname='root'\n", encoding="utf-8")
	package = tmp_path / "python" / "flowforge-cli"
	package.mkdir(parents=True)
	(package / "pyproject.toml").write_text(
		"[project]\nname='flowforge-cli'\nversion='9.9.9'\n",
		encoding="utf-8",
	)
	tests = tmp_path / "tests"
	tests.mkdir()
	(tests / "test_smoke.py").write_text("def test_one():\n\tassert True\n", encoding="utf-8")

	result = runner.invoke(app, ["status", "--root", str(tmp_path), "--json"])

	assert result.exit_code == 0, result.output
	payload = json.loads(result.output)
	assert payload["version"] == "9.9.9"
	assert payload["package_count"] == 1
	assert payload["test_count"] == 1


def test_new_workflow_creates_minimal_workflow_def(tmp_path: Path) -> None:
	out = tmp_path / "workflow_def.json"

	result = runner.invoke(app, ["new-workflow", "claim-intake", "--out", str(out)])

	assert result.exit_code == 0, result.output
	data = json.loads(out.read_text(encoding="utf-8"))
	assert data["key"] == "claim_intake"
	assert data["initial_state"] == "draft"
	assert len(data["states"]) == 3
	assert "Success" in result.output


def test_lint_jtbd_accepts_single_spec(tmp_path: Path) -> None:
	spec = {
		"id": "claim_intake",
		"jtbd_id": "claim_intake",
		"version": "1.0.0",
		"actor": {"role": "analyst"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["sc"],
		"stages": [
			{"name": "discover"},
			{"name": "execute"},
			{"name": "error_handle"},
			{"name": "report"},
			{"name": "audit"},
		],
	}
	path = tmp_path / "claim_intake.json"
	path.write_text(json.dumps(spec), encoding="utf-8")

	result = runner.invoke(app, ["lint-jtbd", str(path), "--shared-role", "analyst"])

	assert result.exit_code == 0, result.output
	assert "JTBD Validation Report" in result.output
	assert "Success" in result.output


def test_lint_jtbd_help_has_example_epilog() -> None:
	result = runner.invoke(app, ["lint-jtbd", "--help"], terminal_width=140)

	assert result.exit_code == 0, result.output
	assert "--example" in unstyle(result.output)
