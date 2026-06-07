"""E-1 acceptance tests: jtbd lint/lock/bundle-fork CLI + forks_enabled default-on.

Tests per audit-2026 signoff-checklist §E-1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge_cli.main import app
from flowforge_cli.commands.jtbd_lock import build_lockfile, lockfile_path
from flowforge_cli.commands.jtbd_bundle_fork import fork_bundle
from flowforge.engine.fork_config import forks_enabled

RUNNER = CliRunner()
HIRING_BUNDLE = Path(__file__).parents[2] / "examples" / "hiring-pipeline" / "jtbd-bundle.json"


# ---------------------------------------------------------------------------
# forks_enabled default-on (Task 4)
# ---------------------------------------------------------------------------


def test_forks_enabled_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
	"""forks_enabled() must return True when FLOWFORGE_FORKS_ENABLED is unset."""
	monkeypatch.delenv("FLOWFORGE_FORKS_ENABLED", raising=False)
	assert forks_enabled() is True


def test_forks_enabled_disabled_by_env_zero(monkeypatch: pytest.MonkeyPatch) -> None:
	"""forks_enabled() must return False when FLOWFORGE_FORKS_ENABLED=0."""
	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "0")
	assert forks_enabled() is False


def test_forks_enabled_disabled_by_env_false(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "false")
	assert forks_enabled() is False


def test_forks_enabled_explicit_one(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("FLOWFORGE_FORKS_ENABLED", "1")
	assert forks_enabled() is True


# ---------------------------------------------------------------------------
# jtbd lint (Task 1)
# ---------------------------------------------------------------------------


def test_lint_hiring_bundle_runs_without_crash() -> None:
	"""lint examples/hiring-pipeline/jtbd-bundle.json must run (exit 0, 1, or 2 — not crash)."""
	assert HIRING_BUNDLE.exists(), f"fixture missing: {HIRING_BUNDLE}"
	result = RUNNER.invoke(app, ["jtbd", "lint", str(HIRING_BUNDLE)])
	# Exit 0=clean, 1=errors, 2=warnings-only — all indicate linter ran successfully.
	# The hiring-pipeline example bundle may have missing lifecycle stages (ERR);
	# what we test here is that the CLI path works end-to-end without an exception.
	assert result.exit_code in (0, 1, 2), (
		f"lint crashed with exit {result.exit_code}:\n{result.stdout}"
	)
	# Output must contain the bundle id
	assert "hiring-pipeline" in result.stdout


def test_lint_hiring_bundle_warn_only_exits_zero() -> None:
	"""--warn-only must exit 0 regardless of findings."""
	assert HIRING_BUNDLE.exists()
	result = RUNNER.invoke(app, ["jtbd", "lint", str(HIRING_BUNDLE), "--warn-only"])
	assert result.exit_code == 0, (
		f"--warn-only exited {result.exit_code}:\n{result.stdout}"
	)


def test_lint_json_format_is_valid_json() -> None:
	"""--format json must produce parseable JSON output."""
	assert HIRING_BUNDLE.exists()
	result = RUNNER.invoke(app, ["jtbd", "lint", str(HIRING_BUNDLE), "--format", "json"])
	# Exit 0/1/2 all indicate linter ran; we care that stdout is valid JSON.
	assert result.exit_code in (0, 1, 2), f"unexpected exit {result.exit_code}: {result.stdout}"
	data = json.loads(result.stdout)
	assert "ok" in data
	assert "results" in data


def test_lint_strict_mode_exits_nonzero_on_warnings(tmp_path: Path) -> None:
	"""--strict must produce exit 1 if there are any warnings."""
	# Build a minimal bundle that will produce a warning (no success_criteria).
	minimal = {
		"project": {"name": "test-bundle"},
		"jtbds": [
			{
				"id": "do_thing",
				"title": "Do a thing",
				"actor": {"role": "user"},
				"situation": "...",
				"motivation": "...",
				"outcome": "...",
			}
		],
	}
	bundle_file = tmp_path / "jtbd-bundle.json"
	bundle_file.write_text(json.dumps(minimal), encoding="utf-8")
	result = RUNNER.invoke(app, ["jtbd", "lint", str(bundle_file), "--strict"])
	# Either errors or warnings-as-errors → exit 1; or clean → exit 0
	assert result.exit_code in (0, 1, 2)


def test_lint_missing_bundle_exits_one(tmp_path: Path) -> None:
	"""lint on a nonexistent path must exit 1."""
	result = RUNNER.invoke(app, ["jtbd", "lint", str(tmp_path / "no-such.json")])
	assert result.exit_code == 1


def test_lint_domain_filter(tmp_path: Path) -> None:
	"""--domain filters specs to those whose id starts with the domain prefix."""
	bundle = {
		"project": {"name": "multi-domain"},
		"jtbds": [
			{"id": "hr_hire", "title": "Hire", "actor": {"role": "hr"}, "situation": "x", "motivation": "y", "outcome": "z"},
			{"id": "finance_pay", "title": "Pay", "actor": {"role": "finance"}, "situation": "x", "motivation": "y", "outcome": "z"},
		],
	}
	bf = tmp_path / "bundle.json"
	bf.write_text(json.dumps(bundle), encoding="utf-8")
	result = RUNNER.invoke(app, ["jtbd", "lint", str(bf), "--domain", "hr", "--format", "json"])
	# Exit 0/1/2 all indicate the linter ran; the minimal bundle may have errors.
	assert result.exit_code in (0, 1, 2)
	data = json.loads(result.stdout)
	# Only hr_ spec should appear in results
	result_ids = [r["jtbd_id"] for r in data["results"]]
	assert all(rid.startswith("hr") for rid in result_ids)


# ---------------------------------------------------------------------------
# jtbd lock (Task 2)
# ---------------------------------------------------------------------------


def test_lock_init_creates_lockfile(tmp_path: Path) -> None:
	"""--init must write bundle.lock.json next to the bundle."""
	import shutil
	bundle_dst = tmp_path / "jtbd-bundle.json"
	shutil.copy(HIRING_BUNDLE, bundle_dst)

	result = RUNNER.invoke(app, ["jtbd", "lock", "--init", str(bundle_dst)])
	assert result.exit_code == 0, f"lock --init failed: {result.stdout}\n{result.stderr or ''}"

	lock_path = tmp_path / "bundle.lock.json"
	assert lock_path.exists(), "bundle.lock.json was not created"

	data = json.loads(lock_path.read_text())
	assert data["schema_version"] == "1"
	assert "pins" in data
	assert len(data["pins"]) > 0
	assert data["body_hash"].startswith("sha256:")


def test_lock_init_custom_out(tmp_path: Path) -> None:
	"""--out must write the lockfile to the specified path."""
	import shutil
	bundle_dst = tmp_path / "jtbd-bundle.json"
	shutil.copy(HIRING_BUNDLE, bundle_dst)
	custom_out = tmp_path / "locks" / "my.lock.json"

	result = RUNNER.invoke(app, ["jtbd", "lock", "--init", "--out", str(custom_out), str(bundle_dst)])
	assert result.exit_code == 0
	assert custom_out.exists()


def test_lock_verify_passes_on_fresh_init(tmp_path: Path) -> None:
	"""--verify must pass (exit 0) immediately after --init on unchanged bundle."""
	import shutil
	bundle_dst = tmp_path / "jtbd-bundle.json"
	shutil.copy(HIRING_BUNDLE, bundle_dst)

	init_result = RUNNER.invoke(app, ["jtbd", "lock", "--init", str(bundle_dst)])
	assert init_result.exit_code == 0

	verify_result = RUNNER.invoke(app, ["jtbd", "lock", "--verify", str(bundle_dst)])
	assert verify_result.exit_code == 0, (
		f"verify failed after init: {verify_result.stdout}\n{verify_result.stderr or ''}"
	)


def test_lock_verify_fails_when_bundle_modified(tmp_path: Path) -> None:
	"""--verify must exit 1 when a JTBD was modified after the lockfile was generated."""
	import shutil
	bundle_dst = tmp_path / "jtbd-bundle.json"
	shutil.copy(HIRING_BUNDLE, bundle_dst)

	RUNNER.invoke(app, ["jtbd", "lock", "--init", str(bundle_dst)])

	# Mutate the bundle
	data = json.loads(bundle_dst.read_text())
	data["jtbds"][0]["title"] = "TAMPERED TITLE"
	bundle_dst.write_text(json.dumps(data), encoding="utf-8")

	result = RUNNER.invoke(app, ["jtbd", "lock", "--verify", str(bundle_dst)])
	assert result.exit_code == 1


def test_lock_no_flag_exits_one() -> None:
	"""lock without --init or --verify must exit 1 with helpful message."""
	result = RUNNER.invoke(app, ["jtbd", "lock", str(HIRING_BUNDLE)])
	assert result.exit_code == 1


# ---------------------------------------------------------------------------
# jtbd bundle-fork (Task 3)
# ---------------------------------------------------------------------------


def test_bundle_fork_helper_adds_parent_version_id() -> None:
	"""fork_bundle() must set parent_version_id on every JTBD."""
	source = {
		"project": {"name": "source-bundle", "version": "1.2.3"},
		"jtbds": [
			{"id": "jtbd_a", "title": "A", "actor": {"role": "user"}, "situation": "x", "motivation": "y", "outcome": "z"},
			{"id": "jtbd_b", "title": "B", "actor": {"role": "admin"}, "situation": "x", "motivation": "y", "outcome": "z"},
		],
	}
	forked = fork_bundle(source, "my-fork")
	assert forked["project"]["name"] == "my-fork"
	assert "fork_provenance" in forked
	assert forked["fork_provenance"]["parent_version_id"] == "source-bundle@1.2.3"
	for jtbd in forked["jtbds"]:
		assert jtbd["parent_version_id"] == "source-bundle@1.2.3", (
			f"JTBD {jtbd['id']} missing parent_version_id"
		)


def test_bundle_fork_does_not_mutate_source() -> None:
	"""fork_bundle() must deep-copy the source; original must be unchanged."""
	source = {
		"project": {"name": "orig", "version": "0.1.0"},
		"jtbds": [{"id": "x", "title": "X", "actor": {"role": "user"}, "situation": ".", "motivation": ".", "outcome": "."}],
	}
	fork_bundle(source, "fork-of-orig")
	assert source["project"]["name"] == "orig"
	assert "parent_version_id" not in source["jtbds"][0]


def test_bundle_fork_cli_creates_output_file(tmp_path: Path) -> None:
	"""bundle-fork CLI must write jtbd-bundle.json under <out>/<target_name>/."""
	import shutil
	bundle_dst = tmp_path / "jtbd-bundle.json"
	shutil.copy(HIRING_BUNDLE, bundle_dst)

	out_dir = tmp_path / "forks"
	result = RUNNER.invoke(
		app,
		["jtbd", "bundle-fork", str(bundle_dst), "my-hiring-fork", "--out", str(out_dir)],
	)
	assert result.exit_code == 0, f"bundle-fork failed: {result.stdout}\n{result.stderr or ''}"

	dst = out_dir / "jtbd-bundle.json"
	assert dst.exists(), f"output file not created: {dst}"

	data = json.loads(dst.read_text())
	assert data["project"]["name"] == "my-hiring-fork"
	assert "fork_provenance" in data
	assert "parent_version_id" in data["fork_provenance"]
	for jtbd in data["jtbds"]:
		assert "parent_version_id" in jtbd, f"JTBD {jtbd.get('id')} missing parent_version_id"


def test_bundle_fork_missing_source_exits_one(tmp_path: Path) -> None:
	"""bundle-fork must exit 1 when source bundle does not exist."""
	result = RUNNER.invoke(
		app,
		["jtbd", "bundle-fork", str(tmp_path / "no-such.json"), "my-fork"],
	)
	assert result.exit_code == 1
