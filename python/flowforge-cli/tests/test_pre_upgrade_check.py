"""Tests for ``flowforge pre-upgrade-check`` (E-34 SK-01 F-7 mitigation).

W0/v0.3.0 adds the ``alembic-chain`` subcheck (item 1 of
``docs/improvements.md``); tests for that lane live alongside the
existing ``signing`` checks.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


def _write_migration(dir_: Path, name: str, body: str) -> Path:
	path = dir_ / name
	path.write_text(textwrap.dedent(body), encoding="utf-8")
	return path


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
	# Override versions dir so the default `backend/migrations/versions`
	# probe doesn't accidentally hit a real chain on the dev machine.
	monkeypatch.setenv("FLOWFORGE_PRE_UPGRADE_VERSIONS_DIR", "/nonexistent/path")
	# Same for the pyproject probe (W4a/v0.3.0 item 4 subcheck) so the
	# default ``pyproject.toml`` lookup doesn't pick up the dev tree.
	monkeypatch.setenv("FLOWFORGE_PRE_UPGRADE_PYPROJECT", "/nonexistent/pyproject.toml")

	r = runner.invoke(app, ["pre-upgrade-check"])
	assert r.exit_code == 0, r.output
	assert "signing" in r.output
	assert "pyproject" in r.output


# ---------------------------------------------------------------------------
# alembic-chain subcheck (W0 item 1)
# ---------------------------------------------------------------------------


def test_alembic_chain_skip_when_dir_missing(
	monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
	"""Missing versions dir → SKIP with hint, exit 0."""
	monkeypatch.delenv("FLOWFORGE_PRE_UPGRADE_VERSIONS_DIR", raising=False)
	bogus = tmp_path / "no-such-dir"
	r = runner.invoke(
		app,
		["pre-upgrade-check", "alembic-chain", "--versions-dir", str(bogus)],
	)
	assert r.exit_code == 0, r.output
	assert "SKIP" in r.output


def test_alembic_chain_passes_single_head(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"a.py",
		"""
		revision = "a"
		down_revision = None


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"b.py",
		"""
		revision = "b"
		down_revision = "a"


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	r = runner.invoke(
		app,
		["pre-upgrade-check", "alembic-chain", "--versions-dir", str(d)],
	)
	assert r.exit_code == 0, r.output
	assert "alembic-chain: OK" in r.output


def test_alembic_chain_fails_multi_head(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"root.py",
		"""
		revision = "root"
		down_revision = None


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"head_a.py",
		"""
		revision = "head_a"
		down_revision = "root"


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"head_b.py",
		"""
		revision = "head_b"
		down_revision = "root"


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	r = runner.invoke(
		app,
		["pre-upgrade-check", "alembic-chain", "--versions-dir", str(d)],
	)
	assert r.exit_code == 1, r.output
	assert "FAIL" in r.output
	assert "Multiple heads" in r.output or "head" in r.output.lower()


def test_alembic_chain_flag_force_includes_in_signing_run(
	monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
	"""``--alembic-chain`` while the positional argument is ``signing``
	should still run the alembic-chain subcheck."""
	monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "real-secret")
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"a.py",
		"""
		revision = "a"
		down_revision = None


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	r = runner.invoke(
		app,
		[
			"pre-upgrade-check",
			"signing",
			"--alembic-chain",
			"--versions-dir",
			str(d),
		],
	)
	assert r.exit_code == 0, r.output
	assert "signing" in r.output
	assert "alembic-chain" in r.output


# ---------------------------------------------------------------------------
# pyproject subcheck (W4a/v0.3.0 item 4 — z3 reachability extra contract)
# ---------------------------------------------------------------------------


def _write_pyproject(path: Path, body: str) -> Path:
	path.write_text(textwrap.dedent(body), encoding="utf-8")
	return path


def test_pyproject_check_skip_when_file_missing(
	monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
	"""Missing pyproject.toml → SKIP with hint, exit 0."""
	monkeypatch.delenv("FLOWFORGE_PRE_UPGRADE_PYPROJECT", raising=False)
	bogus = tmp_path / "no-such-file.toml"
	r = runner.invoke(
		app,
		["pre-upgrade-check", "pyproject", "--pyproject-path", str(bogus)],
	)
	assert r.exit_code == 0, r.output
	assert "SKIP" in r.output


def test_pyproject_check_passes_when_z3_absent(tmp_path: Path) -> None:
	"""pyproject.toml without z3-solver → OK, exit 0."""
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"
		dependencies = ["fastapi", "sqlalchemy"]
		""",
	)
	r = runner.invoke(
		app, ["pre-upgrade-check", "pyproject", "--pyproject-path", str(p)]
	)
	assert r.exit_code == 0, r.output
	assert "OK" in r.output


def test_pyproject_check_passes_when_z3_only_in_canonical_extra(
	tmp_path: Path,
) -> None:
	"""z3-solver only in [project.optional-dependencies] reachability → OK."""
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"
		dependencies = ["fastapi"]

		[project.optional-dependencies]
		reachability = [
			"z3-solver==4.13.4.0",
		]
		""",
	)
	r = runner.invoke(
		app, ["pre-upgrade-check", "pyproject", "--pyproject-path", str(p)]
	)
	assert r.exit_code == 0, r.output
	assert "OK" in r.output


def test_pyproject_check_passes_with_flowforge_cli_extra(tmp_path: Path) -> None:
	"""``flowforge-cli[reachability]`` reference → OK (transitive opt-in)."""
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"

		[dependency-groups]
		dev = [
			"flowforge-cli[reachability]",
		]
		""",
	)
	r = runner.invoke(
		app, ["pre-upgrade-check", "pyproject", "--pyproject-path", str(p)]
	)
	assert r.exit_code == 0, r.output
	assert "OK" in r.output


def test_pyproject_check_warns_when_z3_in_top_level_dependencies(
	tmp_path: Path,
) -> None:
	"""z3-solver in [project] dependencies → WARN, exit 1."""
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"
		dependencies = [
			"fastapi",
			"z3-solver>=4.13",
		]
		""",
	)
	r = runner.invoke(
		app, ["pre-upgrade-check", "pyproject", "--pyproject-path", str(p)]
	)
	assert r.exit_code == 1, r.output
	assert "WARN" in r.output
	assert "ADR-004" in r.output


def test_pyproject_check_warns_when_z3_in_dev_group(tmp_path: Path) -> None:
	"""z3-solver direct-pinned in dev group → WARN (not via the extra)."""
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"

		[dependency-groups]
		dev = [
			"pytest",
			"z3-solver>=4.13",
		]
		""",
	)
	r = runner.invoke(
		app, ["pre-upgrade-check", "pyproject", "--pyproject-path", str(p)]
	)
	assert r.exit_code == 1, r.output
	assert "WARN" in r.output


def test_pyproject_check_warns_when_z3_in_non_canonical_extra(
	tmp_path: Path,
) -> None:
	"""z3-solver in a non-canonical [project.optional-dependencies] block."""
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"

		[project.optional-dependencies]
		lint = [
			"z3-solver>=4.13",
		]
		""",
	)
	r = runner.invoke(
		app, ["pre-upgrade-check", "pyproject", "--pyproject-path", str(p)]
	)
	assert r.exit_code == 1, r.output
	assert "WARN" in r.output


def test_check_pyproject_flag_force_includes_in_signing_run(
	monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
	"""``--check-pyproject`` while the positional arg is ``signing``."""
	monkeypatch.setenv("FLOWFORGE_SIGNING_SECRET", "real-secret")
	monkeypatch.delenv("FLOWFORGE_ALLOW_INSECURE_DEFAULT", raising=False)
	p = _write_pyproject(
		tmp_path / "pyproject.toml",
		"""
		[project]
		name = "host-app"
		version = "0.0.1"
		dependencies = ["fastapi"]
		""",
	)
	r = runner.invoke(
		app,
		[
			"pre-upgrade-check",
			"signing",
			"--check-pyproject",
			"--pyproject-path",
			str(p),
		],
	)
	assert r.exit_code == 0, r.output
	assert "signing" in r.output
	assert "pyproject" in r.output
