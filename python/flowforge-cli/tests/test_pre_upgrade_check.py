"""Tests for ``flowforge pre-upgrade-check`` (E-34 SK-01 F-7 mitigation)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


def test_signing_check_fails_when_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
	"""No env var, no opt-in flag → exit 1 with remediation message."""
	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)

	r = runner.invoke(app, ["pre-upgrade-check", "signing"])
	assert r.exit_code == 1
	assert "FAIL" in r.output
	assert "FLOWFORGE_SIGNING_SECRET" in r.output


def test_signing_check_passes_with_secret(monkeypatch: pytest.MonkeyPatch) -> None:
	"""``FLOWFORGE_SIGNING_SECRET`` set → exit 0."""
	monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "real-secret")
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)

	r = runner.invoke(app, ["pre-upgrade-check", "signing"])
	assert r.exit_code == 0, r.output
	assert "OK" in r.output


def test_signing_check_warns_with_insecure_opt_in(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Opt-in flag → exit 0 with WARN message naming the deprecation window."""
	monkeypatch.delenv("FLOWFORGE_SIGNING_SECRET", raising=False)
	monkeypatch.setenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", "1")

	r = runner.invoke(app, ["pre-upgrade-check", "signing"])
	assert r.exit_code == 0, r.output
	assert "WARN" in r.output
	assert "deprecation" in r.output.lower() or "minor version" in r.output.lower()


def test_pre_upgrade_check_default_runs_all(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Bare ``pre-upgrade-check`` (no arg) defaults to ``all``."""
	monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "real-secret")
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)

	r = runner.invoke(app, ["pre-upgrade-check"])
	assert r.exit_code == 0, r.output
	assert "signing" in r.output
