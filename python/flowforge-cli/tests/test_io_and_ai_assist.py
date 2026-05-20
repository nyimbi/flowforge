from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge_cli._io import (
	discover_workflow_defs,
	load_structured,
	safe_output_path,
	write_json,
)
from flowforge_cli.commands.ai_assist import _select_jtbd
from flowforge_cli.main import app


runner = CliRunner()


def test_load_structured_reads_yaml_mapping(tmp_path: Path) -> None:
	path = tmp_path / "bundle.yaml"
	path.write_text("project:\n  name: claims\n", encoding="utf-8")

	assert load_structured(path) == {"project": {"name": "claims"}}


def test_load_structured_falls_back_to_yaml_for_unknown_suffix(tmp_path: Path) -> None:
	path = tmp_path / "bundle.data"
	path.write_text("project:\n  name: claims\n", encoding="utf-8")

	assert load_structured(path) == {"project": {"name": "claims"}}


def test_load_structured_rejects_non_mapping_json(tmp_path: Path) -> None:
	path = tmp_path / "bundle.json"
	path.write_text(json.dumps(["not", "a", "mapping"]), encoding="utf-8")

	with pytest.raises(ValueError, match="expected a mapping"):
		load_structured(path)


def test_write_json_creates_parent_and_sorts_keys(tmp_path: Path) -> None:
	path = tmp_path / "nested" / "data.json"

	write_json(path, {"b": 2, "a": 1})

	assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


@pytest.mark.parametrize("relative_path", ["/tmp/escape.txt", "../escape.txt", Path("nested/../escape.txt")])
def test_safe_output_path_rejects_absolute_and_parent_segments(
	tmp_path: Path,
	relative_path: str | Path,
) -> None:
	with pytest.raises(ValueError, match="unsafe generated path"):
		safe_output_path(tmp_path, relative_path)


def test_safe_output_path_rejects_symlink_escape(tmp_path: Path) -> None:
	root = tmp_path / "root"
	root.mkdir()
	outside = tmp_path / "outside"
	outside.mkdir()
	(root / "link").symlink_to(outside, target_is_directory=True)

	with pytest.raises(ValueError, match="unsafe generated path"):
		safe_output_path(root, "link/file.txt")


def test_safe_output_path_accepts_nested_relative_path(tmp_path: Path) -> None:
	root = tmp_path / "root"

	assert safe_output_path(root, "nested/file.txt") == root.resolve(strict=False) / "nested" / "file.txt"


def test_discover_workflow_defs_returns_sorted_definitions(tmp_path: Path) -> None:
	root = tmp_path / "workflows"
	for name in ["b", "a"]:
		path = root / name
		path.mkdir(parents=True)
		(path / "definition.json").write_text("{}", encoding="utf-8")
		(path / "other.json").write_text("{}", encoding="utf-8")

	assert [path.parent.name for path in discover_workflow_defs(root)] == ["a", "b"]


def test_discover_workflow_defs_returns_empty_for_missing_root(tmp_path: Path) -> None:
	assert discover_workflow_defs(tmp_path / "missing") == []


def test_select_jtbd_allows_no_focus() -> None:
	assert _select_jtbd({"jtbds": [{"id": "claim_intake"}]}, None) is None


def test_select_jtbd_skips_non_mapping_items() -> None:
	selected = _select_jtbd({"jtbds": ["bad", {"id": "claim_intake"}]}, "claim_intake")

	assert selected == {"id": "claim_intake"}


def test_select_jtbd_rejects_unknown_job() -> None:
	with pytest.raises(ValueError, match="JTBD id not found: missing"):
		_select_jtbd({"jtbds": [{"id": "claim_intake"}]}, "missing")


def test_ai_assist_writes_prompt_to_file(jtbd_bundle: Path, tmp_path: Path) -> None:
	out = tmp_path / "prompts" / "claim.txt"

	r = runner.invoke(app, ["ai-assist", str(jtbd_bundle), "--job", "claim_intake", "--out", str(out)])

	assert r.exit_code == 0, r.output
	assert f"wrote AI authoring prompt: {out}" in r.output
	assert "Selected JTBD JSON" in out.read_text(encoding="utf-8")


def test_ai_assist_prints_prompt_to_stdout(jtbd_bundle: Path) -> None:
	r = runner.invoke(app, ["ai-assist", str(jtbd_bundle)])

	assert r.exit_code == 0, r.output
	assert "Selected JTBD JSON" in r.output


def test_ai_assist_reports_selection_error(jtbd_bundle: Path) -> None:
	r = runner.invoke(app, ["ai-assist", str(jtbd_bundle), "--job", "missing"])

	assert r.exit_code == 2
	assert "error: JTBD id not found: missing" in r.output
