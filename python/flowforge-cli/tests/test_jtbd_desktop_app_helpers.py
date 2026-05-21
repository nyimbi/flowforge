"""GUI-free tests for the optional JTBD desktop app helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd_desktop import app as app_module


class FakeItem:
	def __init__(self, text: object) -> None:
		self._text = str(text)

	def text(self) -> str:
		return self._text


class FakeTable:
	def __init__(self, columns: int) -> None:
		self._columns = columns
		self._rows: list[list[FakeItem | None]] = []
		self._current = -1
		self.blocked: list[bool] = []

	def rowCount(self) -> int:
		return len(self._rows)

	def columnCount(self) -> int:
		return self._columns

	def setRowCount(self, count: int) -> None:
		self._rows = [[None for _ in range(self._columns)] for _ in range(count)]

	def insertRow(self, row: int) -> None:
		self._rows.insert(row, [None for _ in range(self._columns)])

	def setItem(self, row: int, column: int, item: FakeItem) -> None:
		self._rows[row][column] = item

	def item(self, row: int, column: int) -> FakeItem | None:
		return self._rows[row][column]

	def blockSignals(self, value: bool) -> None:
		self.blocked.append(value)

	def currentRow(self) -> int:
		return self._current

	def removeRow(self, row: int) -> None:
		del self._rows[row]


class FakeCombo:
	def __init__(self, values: list[Any]) -> None:
		self.values = values
		self.current_index: int | None = None

	def count(self) -> int:
		return len(self.values)

	def itemData(self, index: int) -> Any:
		return self.values[index]

	def setCurrentIndex(self, index: int) -> None:
		self.current_index = index


def test_theme_helpers_and_missing_pyqt_launch_message(tmp_path: Path) -> None:
	theme_path = tmp_path / "theme.json"
	theme_path.write_text(json.dumps({"primary": "#111827"}), encoding="utf-8")
	assert app_module._read_theme(theme_path) == {"primary": "#111827"}

	bad_theme = tmp_path / "bad-theme.json"
	bad_theme.write_text("[]", encoding="utf-8")
	with pytest.raises(ValueError, match="theme file must contain a JSON object"):
		app_module._read_theme(bad_theme)

	theme = app_module._load_theme({"primary": 123, "unknown": "ignored"})
	assert theme["primary"] == "123"
	assert "unknown" not in theme
	assert app_module._load_theme(None)["primary"] == "#2563eb"
	assert "#f6f8fb" in app_module._stylesheet(theme)

	with pytest.raises(RuntimeError, match="PyQt6 is required"):
		app_module.run_desktop_editor()


def test_scalar_helpers_and_combo_restore() -> None:
	assert app_module._csv(" en, fr ,, sw ") == ["en", "fr", "sw"]
	assert app_module._csv_enum("gdpr, custom", app_module.COMPLIANCE_REGIMES) == [
		"GDPR",
		"custom",
	]
	assert app_module._bool("") is False
	assert app_module._bool("", default=True) is True
	assert app_module._bool("YES") is True
	assert app_module._bool("no") is False
	assert app_module._int("42", 7) == 42
	assert app_module._int("not-a-number", 7) == 7
	assert app_module._unique_template_id("Review Template", {"review_template"}) == (
		"review_template_2"
	)

	combo = FakeCombo(["a", "b"])
	app_module._restore_combo_data(combo, "b", 0)
	assert combo.current_index == 1

	app_module._restore_combo_data(combo, "missing", 99)
	assert combo.current_index == 1

	empty = FakeCombo([])
	app_module._restore_combo_data(empty, "missing", 0)
	assert empty.current_index is None


def test_table_mutation_and_row_serializers(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(app_module, "QTableWidgetItem", FakeItem, raising=False)

	strings = FakeTable(1)
	app_module._set_string_rows(strings, ["first", ""])
	assert strings.blocked == [True, False]
	assert app_module._string_rows(strings) == ["first"]

	calls: list[str] = []
	app_module._mutate_table(strings, app_module._add_empty_row, lambda: calls.append("changed"))
	assert strings.rowCount() == 3
	assert calls == ["changed"]
	app_module._mutate_table(strings, lambda _table: None, None)
	strings._current = 1
	app_module._remove_selected_row(strings)
	assert strings.rowCount() == 2
	strings._current = -1
	app_module._remove_selected_row(strings)
	assert strings.rowCount() == 2

	fields = FakeTable(6)
	app_module._set_rows(
		fields,
		[
			["requester_email", "email", "", "true", "", "PII"],
			["", "text", "Skipped", "false", "false", ""],
		],
	)
	assert app_module._field_rows(fields) == [
		{
			"id": "requester_email",
			"kind": "email",
			"label": "Requester Email",
			"required": True,
			"pii": True,
			"validation": {},
			"sensitivity": ["PII"],
		}
	]
	rendered_fields = FakeTable(6)
	app_module._set_field_rows(
		rendered_fields,
		[
			{
				"id": "amount",
				"kind": "money",
				"label": "Amount",
				"required": False,
				"pii": False,
				"sensitivity": [],
			}
		],
	)
	assert app_module._rows(rendered_fields) == [
		["amount", "money", "Amount", "false", "false", ""]
	]

	edges = FakeTable(4)
	app_module._set_rows(edges, [["large_loss", "amount > 100", "branch", "review"]])
	assert app_module._edge_rows(edges) == [
		{
			"id": "large_loss",
			"condition": "amount > 100",
			"handle": "branch",
			"branch_to": "review",
		}
	]
	rendered_edges = FakeTable(4)
	app_module._set_edge_rows(
		rendered_edges,
		[{"id": "lapsed", "condition": "policy expired", "handle": "reject"}],
	)
	assert app_module._edge_rows(rendered_edges) == [
		{"id": "lapsed", "condition": "policy expired", "handle": "reject"}
	]

	docs = FakeTable(5)
	app_module._set_rows(docs, [["identity", "2", "5", "30", "yes"]])
	assert app_module._doc_rows(docs) == [
		{
			"kind": "identity",
			"min": 2,
			"av_required": True,
			"max": 5,
			"freshness_days": 30,
		}
	]
	rendered_docs = FakeTable(5)
	app_module._set_doc_rows(
		rendered_docs,
		[{"kind": "receipt", "min": 1, "av_required": False}],
	)
	assert app_module._doc_rows(rendered_docs) == [
		{"kind": "receipt", "min": 1, "av_required": False}
	]

	approvals = FakeTable(4)
	app_module._set_rows(
		approvals,
		[
			["reviewer", "n_of_m", "2", ""],
			["manager", "authority_tier", "", "3"],
		],
	)
	assert app_module._approval_rows(approvals) == [
		{"role": "reviewer", "policy": "n_of_m", "n": 2},
		{"role": "manager", "policy": "authority_tier", "tier": 3},
	]
	rendered_approvals = FakeTable(4)
	app_module._set_approval_rows(rendered_approvals, [{"role": "reviewer"}])
	assert app_module._approval_rows(rendered_approvals) == [
		{"role": "reviewer", "policy": "1_of_1"}
	]

	notifications = FakeTable(3)
	app_module._set_rows(
		notifications,
		[
			["", "", "ops"],
			["state_enter", "email", ""],
		],
	)
	assert app_module._notification_rows(notifications) == [
		{"trigger": "state_enter", "channel": "in_app", "audience": "ops"}
	]
	rendered_notifications = FakeTable(3)
	app_module._set_notification_rows(rendered_notifications, [{"audience": "ops"}])
	assert app_module._notification_rows(rendered_notifications) == [
		{"trigger": "state_enter", "channel": "in_app", "audience": "ops"}
	]

	entities = FakeTable(2)
	app_module._set_rows(entities, [["claim", ""], ["", "ignored"]])
	assert app_module._entity_rows(entities) == [{"name": "claim", "id_field": "claim_id"}]
	rendered_entities = FakeTable(2)
	app_module._set_entity_rows(rendered_entities, [{"name": "case", "id_field": "case_id"}])
	assert app_module._entity_rows(rendered_entities) == [
		{"name": "case", "id_field": "case_id"}
	]
