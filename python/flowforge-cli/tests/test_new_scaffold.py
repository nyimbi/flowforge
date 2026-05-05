"""Tests for ``flowforge new`` — backend scaffold from a JTBD bundle."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


def test_new_scaffolds_backend_from_bundle(jtbd_bundle: Path, tmp_path: Path) -> None:
	out_dir = tmp_path / "out"
	result = runner.invoke(
		app,
		[
			"new",
			"my-claims",
			"--jtbd",
			str(jtbd_bundle),
			"--out",
			str(out_dir),
		],
	)
	assert result.exit_code == 0, result.output

	target = out_dir / "my-claims"
	assert target.is_dir()
	# Backend skeleton
	assert (target / "backend" / "pyproject.toml").is_file()
	assert (target / "backend" / "src" / "my_claims" / "__init__.py").is_file()
	assert (target / "backend" / "src" / "my_claims" / "main.py").is_file()
	assert (target / "backend" / "src" / "my_claims" / "config.py").is_file()
	assert (target / "backend" / "src" / "my_claims" / "workflow_adapter.py").is_file()
	# Workflow stubs + bundle copy
	bundle_copy = target / "workflows" / "jtbd_bundle.json"
	assert bundle_copy.is_file()
	wf_def = target / "workflows" / "claim_intake" / "definition.json"
	assert wf_def.is_file()

	# Stub workflow is schema-valid and has the expected key.
	data = json.loads(wf_def.read_text())
	assert data["key"] == "claim_intake"
	assert data["initial_state"] == "intake"
	assert any(s["kind"] == "terminal_success" for s in data["states"])

	# Output mentions every phase.
	assert "[1/4]" in result.output
	assert "[2/4]" in result.output
	assert "[3/4]" in result.output
	assert "[4/4]" in result.output


def test_new_rejects_invalid_bundle(tmp_path: Path) -> None:
	bad = tmp_path / "bad.json"
	bad.write_text('{"project": {"name": "x"}}', encoding="utf-8")
	result = runner.invoke(
		app,
		[
			"new",
			"x",
			"--jtbd",
			str(bad),
			"--out",
			str(tmp_path / "out"),
		],
	)
	assert result.exit_code != 0
	# Typer wraps BadParameter messages in a Rich panel that line-breaks
	# the literal string; match on a stable substring instead.
	output = result.output.replace("\n", "").replace(" ", "")
	assert "JTBDbundleinvalid" in output or "invalid" in result.output.lower()


def test_new_refuses_non_empty_target(jtbd_bundle: Path, tmp_path: Path) -> None:
	target_parent = tmp_path / "out"
	target = target_parent / "my-claims"
	target.mkdir(parents=True)
	(target / "occupied.txt").write_text("nope", encoding="utf-8")

	result = runner.invoke(
		app,
		[
			"new",
			"my-claims",
			"--jtbd",
			str(jtbd_bundle),
			"--out",
			str(target_parent),
		],
	)
	assert result.exit_code != 0
	# Typer renders BadParameter inside a wrapped Rich panel; just ensure
	# the failure surfaced an error and the directory wasn't overwritten.
	assert (target / "occupied.txt").read_text() == "nope"
	assert not (target / "backend").exists()
