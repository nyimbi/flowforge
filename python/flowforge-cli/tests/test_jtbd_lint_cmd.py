"""Tests for ``flowforge jtbd lint`` — E-9 pre-commit / CI integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_ALL_STAGES = [
	{"name": "discover"},
	{"name": "execute"},
	{"name": "error_handle"},
	{"name": "report"},
	{"name": "audit"},
]


def _bundle(jtbds: list[dict[str, Any]], *, name: str = "test-bundle") -> dict[str, Any]:
	return {
		"project": {"name": name, "package": "test", "domain": "test"},
		"shared": {"roles": ["user"], "permissions": ["test.read"]},
		"jtbds": jtbds,
	}


def _minimal_jtbd(jtbd_id: str, *, with_stages: bool = False) -> dict[str, Any]:
	spec: dict[str, Any] = {
		"id": jtbd_id,
		"actor": {"role": "user"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["sc"],
	}
	if with_stages:
		spec["stages"] = list(_ALL_STAGES)
	return spec


def _clean_jtbd(jtbd_id: str) -> dict[str, Any]:
	"""Fully lint-clean JTBD with all required stages and declared shared role."""
	return {
		"id": jtbd_id,
		"jtbd_id": jtbd_id,
		"version": "1.0.0",
		"actor": {"role": "analyst"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["sc"],
		"stages": list(_ALL_STAGES),
	}


def _clean_bundle(jtbds: list[dict[str, Any]], *, name: str = "test-bundle") -> dict[str, Any]:
	return {
		"project": {"name": name, "package": "test", "domain": "test"},
		"shared": {
			"roles": ["analyst"],
			"permissions": ["test.read"],
		},
		"bundle_id": name,
		"jtbds": jtbds,
	}


@pytest.fixture()
def ok_bundle(tmp_path: Path) -> Path:
	data = _clean_bundle([_clean_jtbd("claim_intake")])
	p = tmp_path / "jtbd-bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


@pytest.fixture()
def bundle_with_requires(tmp_path: Path) -> Path:
	"""Bundle where 'b' declares requires=['a'] — dependency graph is valid."""
	a = _clean_jtbd("a")
	b = dict(_clean_jtbd("b"))
	b["requires"] = ["a"]
	data = _clean_bundle([a, b])
	p = tmp_path / "jtbd-bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


@pytest.fixture()
def bundle_with_missing_requires(tmp_path: Path) -> Path:
	"""Bundle where 'b' requires 'ghost' which doesn't exist — should error."""
	b = dict(_clean_jtbd("b"))
	b["requires"] = ["ghost"]
	data = _clean_bundle([b])
	p = tmp_path / "jtbd-bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


@pytest.fixture()
def cycle_bundle(tmp_path: Path) -> Path:
	"""Bundle where a→b→a creates a dependency cycle — should error."""
	a = dict(_clean_jtbd("a"))
	a["requires"] = ["b"]
	b = dict(_clean_jtbd("b"))
	b["requires"] = ["a"]
	data = _clean_bundle([a, b])
	p = tmp_path / "jtbd-bundle.json"
	p.write_text(json.dumps(data), encoding="utf-8")
	return p


# ---------------------------------------------------------------------------
# Basic lint tests
# ---------------------------------------------------------------------------


def test_lint_ok_bundle_exits_0(ok_bundle: Path) -> None:
	r = runner.invoke(app, ["jtbd", "lint", "--bundle", str(ok_bundle)])
	assert r.exit_code == 0, r.output
	assert "ok" in r.output


def test_lint_ok_bundle_with_valid_requires(bundle_with_requires: Path) -> None:
	r = runner.invoke(app, ["jtbd", "lint", "--bundle", str(bundle_with_requires)])
	assert r.exit_code == 0, r.output


def test_lint_missing_requires_exits_1(bundle_with_missing_requires: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "lint", "--bundle", str(bundle_with_missing_requires)]
	)
	assert r.exit_code == 1


def test_lint_cycle_exits_1(cycle_bundle: Path) -> None:
	r = runner.invoke(app, ["jtbd", "lint", "--bundle", str(cycle_bundle)])
	assert r.exit_code == 1


def test_lint_missing_bundle_exits_1(tmp_path: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "lint", "--bundle", str(tmp_path / "nope.json")]
	)
	assert r.exit_code == 1


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_lint_json_format_is_valid(ok_bundle: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "lint", "--bundle", str(ok_bundle), "--format", "json"]
	)
	assert r.exit_code == 0, r.output
	data = json.loads(r.output)
	assert data["ok"] is True
	assert "results" in data
	assert "bundle_issues" in data


def test_lint_json_format_includes_bundle_id(ok_bundle: Path) -> None:
	r = runner.invoke(
		app, ["jtbd", "lint", "--bundle", str(ok_bundle), "--format", "json"]
	)
	data = json.loads(r.output)
	assert data["bundle_id"] == "test-bundle"


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_lint_warn_only_does_not_exit_1(bundle_with_missing_requires: Path) -> None:
	r = runner.invoke(
		app,
		["jtbd", "lint", "--bundle", str(bundle_with_missing_requires), "--warn-only"],
	)
	# --warn-only means exit 0 even on errors
	assert r.exit_code == 0


def test_lint_help_lists_options() -> None:
	r = runner.invoke(app, ["jtbd", "lint", "--help"])
	assert r.exit_code == 0
	assert "--bundle" in r.output
	assert "--strict" in r.output
	assert "--format" in r.output
