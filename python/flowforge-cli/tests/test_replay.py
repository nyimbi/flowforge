from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowforge_cli.commands.replay import _load_events
from flowforge_cli.main import app


runner = CliRunner()


def test_replay_requires_workflow_definition() -> None:
	r = runner.invoke(app, ["replay", "--event", "submit"])

	assert r.exit_code == 2
	assert "replay requires --def" in r.output


def test_replay_accepts_context_events_file_and_instance_id(
	workflow_ok: Path,
	tmp_path: Path,
) -> None:
	events_file = tmp_path / "events.json"
	events_file.write_text(
		json.dumps(
			{
				"events": [
					{"event": "submit", "payload": {"source": "file"}},
					{"name": "approve", "payload": {"source": "file"}},
				]
			}
		),
		encoding="utf-8",
	)
	context = tmp_path / "context.json"
	context.write_text(json.dumps({"claim_id": "c1"}), encoding="utf-8")

	r = runner.invoke(
		app,
		[
			"replay",
			"--def",
			str(workflow_ok),
			"--context",
			str(context),
			"--events-file",
			str(events_file),
			"--instance-id",
			"deterministic-instance",
		],
	)

	assert r.exit_code == 0, r.output
	assert "replay events: 2" in r.output
	assert "final state: done" in r.output
	assert "history: intake-(submit:submit)->review, review-(approve:approve)->done" in r.output


def test_replay_without_events_reports_empty_history(workflow_ok: Path) -> None:
	r = runner.invoke(app, ["replay", "--def", str(workflow_ok)])

	assert r.exit_code == 0, r.output
	assert "replay events: 0" in r.output
	assert "final state: intake" in r.output
	assert "history: (empty)" in r.output


def test_replay_wraps_event_file_errors(workflow_ok: Path, tmp_path: Path) -> None:
	events_file = tmp_path / "events.json"
	events_file.write_text(json.dumps({"events": "submit"}), encoding="utf-8")

	r = runner.invoke(app, ["replay", "--def", str(workflow_ok), "--events-file", str(events_file)])

	assert r.exit_code == 2
	assert "error: --events-file must contain an events list" in r.output


def test_load_events_splits_repeatable_and_comma_separated_events() -> None:
	assert _load_events(["submit, approve", " ,close"], None) == [
		("submit", {}),
		("approve", {}),
		("close", {}),
	]


def test_load_events_reads_string_and_object_events(tmp_path: Path) -> None:
	events_file = tmp_path / "events.json"
	events_file.write_text(
		json.dumps({"events": ["submit", {"name": "approve", "payload": {"ok": True}}]}),
		encoding="utf-8",
	)

	assert _load_events(["draft"], events_file) == [
		("draft", {}),
		("submit", {}),
		("approve", {"ok": True}),
	]


def test_load_events_rejects_missing_event_name(tmp_path: Path) -> None:
	events_file = tmp_path / "events.json"
	events_file.write_text(json.dumps({"events": [{"payload": {}}]}), encoding="utf-8")

	with pytest.raises(ValueError, match=r"events\[0\] must include event/name"):
		_load_events([], events_file)


def test_load_events_rejects_non_object_payload(tmp_path: Path) -> None:
	events_file = tmp_path / "events.json"
	events_file.write_text(json.dumps({"events": [{"event": "submit", "payload": ["bad"]}]}), encoding="utf-8")

	with pytest.raises(ValueError, match=r"events\[0\]\.payload must be an object"):
		_load_events([], events_file)


def test_load_events_rejects_unknown_event_item_shape(tmp_path: Path) -> None:
	events_file = tmp_path / "events.json"
	events_file.write_text(json.dumps({"events": [123]}), encoding="utf-8")

	with pytest.raises(ValueError, match=r"events\[0\] must be a string or object"):
		_load_events([], events_file)
