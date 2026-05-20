"""Tests for auxiliary commands: add-jtbd, regen-catalog, migrate-fork,
diff, replay, audit verify, upgrade-deps, and ai-assist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_migrate_fork_rejects_unsafe_tenant_default_path(
	workflow_ok: Path,
	tmp_path: Path,
) -> None:
	with runner.isolated_filesystem(temp_dir=tmp_path):
		r = runner.invoke(
			app,
			[
				"migrate-fork",
				str(workflow_ok),
				"--to",
				"../outside",
			],
		)

	assert r.exit_code != 0
	assert "tenant id" in r.output
	assert not (tmp_path / "outside" / "claim_intake" / "definition.json").exists()


@pytest.mark.parametrize("tenant", [".", ".."])
def test_migrate_fork_rejects_dot_segment_tenant_default_path(
	workflow_ok: Path,
	tmp_path: Path,
	tenant: str,
) -> None:
	with runner.isolated_filesystem(temp_dir=tmp_path):
		r = runner.invoke(
			app,
			[
				"migrate-fork",
				str(workflow_ok),
				"--to",
				tenant,
			],
		)

	assert r.exit_code != 0
	assert "tenant id" in r.output


def test_migrate_fork_rejects_unsafe_workflow_key_default_path(
	tmp_path: Path,
) -> None:
	upstream = tmp_path / "upstream.json"
	upstream.write_text(
		json.dumps(
			{
				"key": "../outside",
				"version": "1.0.0",
				"states": [],
				"transitions": [],
			}
		),
		encoding="utf-8",
	)

	with runner.isolated_filesystem(temp_dir=tmp_path):
		r = runner.invoke(
			app,
			[
				"migrate-fork",
				str(upstream),
				"--to",
				"tenant-A",
			],
		)

	assert r.exit_code != 0
	assert "workflow key" in r.output
	assert not (tmp_path / "outside" / "definition.json").exists()


@pytest.mark.parametrize("key", [".", ".."])
def test_migrate_fork_rejects_dot_segment_workflow_key_default_path(
	tmp_path: Path,
	key: str,
) -> None:
	upstream = tmp_path / "upstream.json"
	upstream.write_text(
		json.dumps(
			{
				"key": key,
				"version": "1.0.0",
				"states": [],
				"transitions": [],
			}
		),
		encoding="utf-8",
	)

	with runner.isolated_filesystem(temp_dir=tmp_path):
		r = runner.invoke(
			app,
			[
				"migrate-fork",
				str(upstream),
				"--to",
				"tenant-A",
			],
		)

	assert r.exit_code != 0
	assert "workflow key" in r.output


# ---------- implemented auxiliary commands ----------


def test_diff_prints_workflow_structural_diff(workflow_ok: Path, tmp_path: Path) -> None:
	b = tmp_path / "b.json"
	data = json.loads(workflow_ok.read_text(encoding="utf-8"))
	data["states"].append({"name": "rejected", "kind": "terminal_fail"})
	b.write_text(json.dumps(data), encoding="utf-8")

	r = runner.invoke(app, ["diff", str(workflow_ok), str(b)])

	assert r.exit_code == 1
	assert "+ state  rejected" in r.output


def test_replay_reconstructs_final_state(workflow_ok: Path) -> None:
	r = runner.invoke(
		app,
		["replay", "--def", str(workflow_ok), "--event", "submit", "--event", "approve"],
	)

	assert r.exit_code == 0
	assert "final state: done" in r.output


def test_upgrade_deps_inspects_workspace() -> None:
	r = runner.invoke(app, ["upgrade-deps"])
	assert r.exit_code == 0
	assert "Flowforge dependency inspection" in r.output


def test_upgrade_deps_discovers_workspace_from_package_dir(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.chdir(Path("python/flowforge-cli"))

	r = runner.invoke(app, ["upgrade-deps"])

	assert r.exit_code == 0
	assert "Flowforge dependency inspection" in r.output


def test_audit_verify_checks_jsonl_export(tmp_path: Path) -> None:
	from flowforge_audit_pg.hash_chain import compute_row_sha

	body = {
		"tenant_id": "t1",
		"actor_user_id": "u1",
		"kind": "workflow.event",
		"subject_kind": "claim",
		"subject_id": "c1",
		"occurred_at": "2026-05-20T00:00:00",
		"payload": {"state": "done"},
	}
	row = {
		"event_id": "e1",
		**body,
		"prev_sha256": None,
		"row_sha256": compute_row_sha(None, body),
	}
	export = tmp_path / "audit.jsonl"
	export.write_text(json.dumps(row) + "\n", encoding="utf-8")

	r = runner.invoke(app, ["audit", "verify", "--file", str(export)])

	assert r.exit_code == 0
	assert "audit chain ok" in r.output


def test_ai_assist_prints_authoring_prompt(jtbd_bundle: Path) -> None:
	r = runner.invoke(app, ["ai-assist", str(jtbd_bundle), "--job", "claim_intake"])

	assert r.exit_code == 0
	assert "Selected JTBD JSON" in r.output
	assert "claim_intake" in r.output


# ---------- top-level help ----------


def test_root_help_lists_commands() -> None:
	r = runner.invoke(app, ["--help"])
	assert r.exit_code == 0
	for cmd in [
		"new",
		"add-jtbd",
		"jtbd-generate",
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


# ---------- jtbd-generate (U19) ----------


def test_jtbd_generate_writes_artefacts(jtbd_bundle: Path, tmp_path: Path) -> None:
	out = tmp_path / "gen"
	r = runner.invoke(
		app,
		[
			"jtbd-generate",
			"--jtbd",
			str(jtbd_bundle),
			"--out",
			str(out),
		],
	)
	assert r.exit_code == 0, r.output
	# Per-JTBD artefacts.
	assert (out / "workflows" / "claim_intake" / "definition.json").is_file()
	assert (out / "workflows" / "claim_intake" / "form_spec.json").is_file()
	# Cross-bundle aggregations.
	assert (out / "README.md").is_file()
	assert (out / ".env.example").is_file()
	assert "jtbd-generate:" in r.output
