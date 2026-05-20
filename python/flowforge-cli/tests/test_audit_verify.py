from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.commands import audit_verify
from flowforge_cli.main import app


runner = CliRunner()


def _audit_body(*, payload: dict[str, Any] | None = None) -> dict[str, Any]:
	return {
		"tenant_id": "t1",
		"actor_user_id": "u1",
		"kind": "workflow.event",
		"subject_kind": "claim",
		"subject_id": "c1",
		"occurred_at": "2026-05-20T00:00:00",
		"payload": payload or {"state": "done"},
	}


def _audit_row(*, event_id: str = "e1", prev_sha256: str | None = None) -> dict[str, Any]:
	from flowforge_audit_pg.hash_chain import compute_row_sha

	body = _audit_body()
	row = {"event_id": event_id, **body, "prev_sha256": prev_sha256}
	row["row_sha256"] = compute_row_sha(prev_sha256, body)
	return row


def test_audit_verify_requires_file_option() -> None:
	r = runner.invoke(app, ["audit", "verify"])

	assert r.exit_code == 2
	assert "audit verify requires --file" in r.output


def test_audit_verify_includes_range_label(tmp_path: Path) -> None:
	export = tmp_path / "audit.jsonl"
	export.write_text(json.dumps(_audit_row()) + "\n", encoding="utf-8")

	r = runner.invoke(app, ["audit", "verify", "--file", str(export), "--range", "last-hour"])

	assert r.exit_code == 0
	assert "audit chain ok (last-hour): checked 1 rows" in r.output


def test_audit_verify_reports_broken_chain(tmp_path: Path) -> None:
	first = _audit_row(event_id="e1")
	second = _audit_row(event_id="e2", prev_sha256=first["row_sha256"])
	second["row_sha256"] = "bad-sha"
	export = tmp_path / "audit.jsonl"
	export.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")

	r = runner.invoke(app, ["audit", "verify", "--file", str(export)])

	assert r.exit_code == 1
	assert "audit chain broken: first bad event e2; checked 2 rows" in r.output


def test_load_rows_ignores_blank_lines_and_rejects_non_objects(tmp_path: Path) -> None:
	export = tmp_path / "audit.jsonl"
	export.write_text("\n[]\n", encoding="utf-8")

	with pytest.raises(ValueError, match="expected object"):
		audit_verify._load_rows(export)


def test_row_accepts_datetime_object() -> None:
	raw = {
		**_audit_row(),
		"occurred_at": datetime(2026, 5, 20, 12, 0, 0),
	}

	row = audit_verify._row(raw, line_no=1)

	assert row.occurred_at == datetime(2026, 5, 20, 12, 0, 0)


def test_row_rejects_non_string_timestamp() -> None:
	raw = {**_audit_row(), "occurred_at": 123}

	with pytest.raises(TypeError, match="occurred_at must be a string"):
		audit_verify._row(raw, line_no=1)


def test_row_rejects_non_object_payload() -> None:
	raw = {**_audit_row(), "payload": ["bad"]}

	with pytest.raises(TypeError, match="payload must be an object"):
		audit_verify._row(raw, line_no=1)


def test_row_reports_missing_required_field() -> None:
	raw = _audit_row()
	del raw["kind"]

	with pytest.raises(ValueError, match="line 7: missing required field 'kind'"):
		audit_verify._row(raw, line_no=7)


def test_audit_verify_wraps_export_parse_errors(tmp_path: Path) -> None:
	export = tmp_path / "audit.jsonl"
	export.write_text(json.dumps({"event_id": "e1"}) + "\n", encoding="utf-8")

	r = runner.invoke(app, ["audit", "verify", "--file", str(export)])

	assert r.exit_code == 2
	assert "error: line 1: missing required field" in r.output
