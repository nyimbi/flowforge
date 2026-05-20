from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge_cli.commands.add_jtbd import _merge_shared
from flowforge_cli.commands import upgrade_deps
from flowforge_cli.commands.migrate_fork import _safe_path_segment
from flowforge_cli.commands.upgrade_deps import _find_workspace_root
from flowforge_cli.main import app


runner = CliRunner()


def test_diff_exit_zero_allows_structural_differences(workflow_ok: Path, tmp_path: Path) -> None:
	changed = tmp_path / "changed.json"
	data = json.loads(workflow_ok.read_text(encoding="utf-8"))
	data["states"].append({"name": "cancelled", "kind": "terminal_fail"})
	changed.write_text(json.dumps(data), encoding="utf-8")

	r = runner.invoke(app, ["diff", str(workflow_ok), str(changed), "--exit-zero"])

	assert r.exit_code == 0
	assert "+ state  cancelled" in r.output


def test_diff_wraps_invalid_workflow_input(workflow_ok: Path, tmp_path: Path) -> None:
	invalid = tmp_path / "invalid.json"
	invalid.write_text("[1, 2, 3]", encoding="utf-8")

	r = runner.invoke(app, ["diff", str(workflow_ok), str(invalid)])

	assert r.exit_code == 2
	assert "error:" in r.output
	assert "expected a mapping" in r.output


def test_add_jtbd_creates_missing_project_bundle(jtbd_bundle: Path, tmp_path: Path) -> None:
	project = tmp_path / "project"

	r = runner.invoke(app, ["add-jtbd", str(jtbd_bundle), "--project", str(project)])

	assert r.exit_code == 0, r.output
	assert "+1 added" in r.output
	assert (project / "workflows" / "jtbd_bundle.json").is_file()
	assert (project / "workflows" / "claim_intake" / "definition.json").is_file()


def test_add_jtbd_refreshes_changed_existing_job(jtbd_bundle: Path, tmp_path: Path) -> None:
	project = tmp_path / "project"
	first = runner.invoke(app, ["add-jtbd", str(jtbd_bundle), "--project", str(project)])
	assert first.exit_code == 0, first.output

	data = json.loads(jtbd_bundle.read_text(encoding="utf-8"))
	data["jtbds"][0]["title"] = "Updated title"
	changed = tmp_path / "changed.json"
	changed.write_text(json.dumps(data), encoding="utf-8")

	r = runner.invoke(app, ["add-jtbd", str(changed), "--project", str(project)])

	assert r.exit_code == 0, r.output
	assert "~1 updated" in r.output
	workflow = json.loads((project / "workflows" / "claim_intake" / "definition.json").read_text(encoding="utf-8"))
	assert workflow["key"] == "claim_intake"

	again = runner.invoke(app, ["add-jtbd", str(changed), "--project", str(project)])
	assert again.exit_code == 0, again.output
	assert "=1 unchanged" in again.output


def test_merge_shared_empty_inputs_return_empty_mapping() -> None:
	assert _merge_shared({}, {}) == {}


def test_merge_shared_dedupes_entities_by_name_id_and_repr() -> None:
	merged = _merge_shared(
		{
			"roles": ["adjuster"],
			"permissions": ["claim.read"],
			"entities": [{"name": "claim", "a": 1}, {"id": "policy", "a": 1}],
		},
		{
			"roles": ["adjuster", "supervisor"],
			"permissions": ["claim.read", "claim.write"],
			"entities": [{"name": "claim", "a": 2}, {"kind": "anonymous"}],
		},
	)

	assert merged["roles"] == ["adjuster", "supervisor"]
	assert merged["permissions"] == ["claim.read", "claim.write"]
	assert merged["entities"] == [
		{"kind": "anonymous"},
		{"name": "claim", "a": 2},
		{"id": "policy", "a": 1},
	]


def test_safe_path_segment_accepts_clean_segment() -> None:
	assert _safe_path_segment("tenant id", "tenant_1.2-3") == "tenant_1.2-3"


def test_migrate_fork_default_destination(workflow_ok: Path, tmp_path: Path) -> None:
	with runner.isolated_filesystem(temp_dir=tmp_path):
		cwd = Path.cwd()
		r = runner.invoke(app, ["migrate-fork", str(workflow_ok), "--to", "tenant-A"])

	assert r.exit_code == 0, r.output
	assert (cwd / "workflows" / "tenant-A" / "claim_intake" / "definition.json").is_file()


def test_upgrade_deps_refuses_apply() -> None:
	r = runner.invoke(app, ["upgrade-deps", "--apply"])

	assert r.exit_code == 2
	assert "--apply is intentionally unavailable" in r.output


def test_upgrade_deps_reports_missing_workspace(tmp_path: Path) -> None:
	r = runner.invoke(app, ["upgrade-deps", "--root", str(tmp_path)])

	assert r.exit_code == 2
	assert "no Flowforge workspace found" in r.output


def test_upgrade_deps_reports_workspace_without_packages(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	workspace = tmp_path / "workspace"
	(workspace / "python").mkdir(parents=True)
	(workspace / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
	monkeypatch.setattr(upgrade_deps, "_find_workspace_root", lambda _root: workspace)

	r = runner.invoke(app, ["upgrade-deps", "--root", str(workspace)])

	assert r.exit_code == 2
	assert "no Flowforge package pyproject.toml files" in r.output


def test_find_workspace_root_returns_none_outside_checkout(tmp_path: Path) -> None:
	assert _find_workspace_root(tmp_path) is None
