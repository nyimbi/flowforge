"""Tests for the remaining commands: add-jtbd, regen-catalog, migrate-fork,
and the skeleton stubs.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.main import app


runner = CliRunner()


# ---------- add-jtbd ----------


def test_add_jtbd_appends_and_is_idempotent(jtbd_bundle: Path, tmp_path: Path) -> None:
	# Scaffold an initial project.
	out_dir = tmp_path / "out"
	r = runner.invoke(
		app, ["new", "my-claims", "--jtbd", str(jtbd_bundle), "--out", str(out_dir)]
	)
	assert r.exit_code == 0, r.output
	project = out_dir / "my-claims"

	# Add a second JTBD.
	new_bundle = json.loads(jtbd_bundle.read_text())
	new_bundle["jtbds"][0]["id"] = "claim_payout"
	new_bundle["jtbds"][0]["title"] = "Pay claim"
	added = tmp_path / "extra.json"
	added.write_text(json.dumps(new_bundle), encoding="utf-8")

	r2 = runner.invoke(app, ["add-jtbd", str(added), "--project", str(project)])
	assert r2.exit_code == 0, r2.output
	assert "+1 added" in r2.output

	merged = json.loads((project / "workflows" / "jtbd_bundle.json").read_text())
	ids = {j["id"] for j in merged["jtbds"]}
	assert {"claim_intake", "claim_payout"} <= ids
	assert (project / "workflows" / "claim_payout" / "definition.json").is_file()

	# Re-running with the same bundle is a no-op (no added/updated).
	r3 = runner.invoke(app, ["add-jtbd", str(added), "--project", str(project)])
	assert r3.exit_code == 0
	assert "+0 added" in r3.output
	assert "~0 updated" in r3.output


# ---------- regen-catalog ----------


def test_regen_catalog_writes_subjects_summary(workflows_dir_ok: Path) -> None:
	r = runner.invoke(app, ["regen-catalog", "--root", str(workflows_dir_ok)])
	assert r.exit_code == 0, r.output

	catalog = json.loads((workflows_dir_ok / "catalog.json").read_text())
	subjects = catalog["subjects"]
	assert "claim" in subjects
	assert "payment" in subjects
	# permissions deduped + sorted
	for entry in subjects.values():
		assert entry["permissions"] == sorted(set(entry["permissions"]))


def test_regen_catalog_no_definitions(tmp_path: Path) -> None:
	r = runner.invoke(app, ["regen-catalog", "--root", str(tmp_path / "missing")])
	assert r.exit_code == 1
	assert "no definitions" in r.output


# ---------- migrate-fork ----------


def test_migrate_fork_copies_with_metadata(workflow_ok: Path, tmp_path: Path) -> None:
	dst = tmp_path / "out" / "fork.json"
	r = runner.invoke(
		app,
		[
			"migrate-fork",
			str(workflow_ok),
			"--to",
			"tenant-A",
			"--out",
			str(dst),
		],
	)
	assert r.exit_code == 0, r.output
	data = json.loads(dst.read_text())
	assert data["metadata"]["tenant_id"] == "tenant-A"
	assert data["metadata"]["forked_from"]["key"] == "claim_intake"


# ---------- skeleton stubs ----------


def test_diff_is_skeleton(tmp_path: Path) -> None:
	a = tmp_path / "a.json"
	b = tmp_path / "b.json"
	a.write_text("{}")
	b.write_text("{}")
	r = runner.invoke(app, ["diff", str(a), str(b)])
	assert r.exit_code != 0
	# Click/Typer surfaces the exception trace; the message must mention NotImplemented.
	assert isinstance(r.exception, NotImplementedError) or "not yet implemented" in r.output


def test_replay_is_skeleton() -> None:
	r = runner.invoke(app, ["replay", "--event", "abc"])
	assert r.exit_code != 0
	assert isinstance(r.exception, NotImplementedError) or "not yet implemented" in r.output


def test_upgrade_deps_is_skeleton() -> None:
	r = runner.invoke(app, ["upgrade-deps"])
	assert r.exit_code != 0
	assert isinstance(r.exception, NotImplementedError) or "not yet implemented" in r.output


def test_audit_verify_is_skeleton() -> None:
	r = runner.invoke(app, ["audit", "verify", "--range", "2024-01..2024-02"])
	assert r.exit_code != 0
	assert isinstance(r.exception, NotImplementedError) or "not yet implemented" in r.output


def test_ai_assist_is_skeleton(tmp_path: Path) -> None:
	jtbd = tmp_path / "j.json"
	jtbd.write_text("{}")
	r = runner.invoke(app, ["ai-assist", str(jtbd)])
	assert r.exit_code != 0
	assert isinstance(r.exception, NotImplementedError) or "not yet implemented" in r.output


# ---------- top-level help ----------


def test_root_help_lists_commands() -> None:
	r = runner.invoke(app, ["--help"])
	assert r.exit_code == 0
	for cmd in [
		"new",
		"add-jtbd",
		"validate",
		"simulate",
		"regen-catalog",
		"migrate-fork",
		"diff",
		"replay",
		"upgrade-deps",
		"ai-assist",
		"audit",
	]:
		assert cmd in r.output, f"missing {cmd!r} in help: {r.output}"
