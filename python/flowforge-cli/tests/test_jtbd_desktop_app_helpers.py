"""GUI-free tests for the optional JTBD desktop app helpers."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

from flowforge_cli.jtbd_desktop import app as app_module
from flowforge_cli.jtbd_desktop.document import (
    JtbdDocument,
    ValidationResult,
    create_default_bundle,
)


class FakeItem:
    def __init__(self, text: object) -> None:
        self._text = str(text)
        self.data: dict[object, object] = {}

    def text(self) -> str:
        return self._text

    def setText(self, text: object) -> None:
        self._text = str(text)

    def setData(self, role: object, value: object) -> None:
        self.data[role] = value


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
    def __init__(self, values: list[Any] | None = None) -> None:
        self.values = values or []
        self.current_index: int | None = None
        self.blocked: list[bool] = []
        self.currentTextChanged = FakeSignal()

    def count(self) -> int:
        return len(self.values)

    def itemData(self, index: int) -> Any:
        return self.values[index]

    def setCurrentIndex(self, index: int) -> None:
        self.current_index = index

    def currentData(self) -> Any:
        if self.current_index is None:
            return None
        return self.values[self.current_index]

    def currentText(self) -> str:
        if self.current_index is None:
            return ""
        return str(self.values[self.current_index])

    def setCurrentText(self, value: object) -> None:
        text = str(value)
        for index, item in enumerate(self.values):
            if str(item) == text:
                self.current_index = index
                return
        self.values.append(text)
        self.current_index = len(self.values) - 1

    def clear(self) -> None:
        self.values = []
        self.current_index = None

    def addItem(self, _label: str, data: Any = None) -> None:
        self.values.append(data)

    def addItems(self, values: list[str]) -> None:
        self.values.extend(values)
        if self.current_index is None and self.values:
            self.current_index = 0

    def blockSignals(self, value: bool) -> None:
        self.blocked.append(value)


class FakeSignal:
    def __init__(self) -> None:
        self.slots: list[Any] = []

    def connect(self, slot: Any) -> None:
        self.slots.append(slot)

    def emit(self) -> None:
        for slot in self.slots:
            slot()


class FakeConnectLineEdit:
    def __init__(self) -> None:
        self.textChanged = FakeSignal()


class FakeConnectPlainTextEdit:
    def __init__(self) -> None:
        self.textChanged = FakeSignal()


class FakeConnectComboBox:
    def __init__(self) -> None:
        self.currentTextChanged = FakeSignal()

    def addItems(self, values: list[str]) -> None:
        self.values = values


class FakeConnectCheckBox:
    def __init__(self) -> None:
        self.stateChanged = FakeSignal()


class FakeHeader:
    def __init__(self) -> None:
        self.visible: bool | None = None
        self.resize_modes: list[Any] = []
        self.stretch_last = False

    def setVisible(self, value: bool) -> None:
        self.visible = value

    def setSectionResizeMode(self, mode: Any) -> None:
        self.resize_modes.append(mode)

    def setStretchLastSection(self, value: bool) -> None:
        self.stretch_last = value


class FakeQTableWidget(FakeTable):
    def __init__(self, rows: int = 0, columns: int = 1) -> None:
        super().__init__(columns)
        self.setRowCount(rows)
        self.headers: list[str] = []
        self.alternating = False
        self.selection_behavior: Any = None
        self.selection_mode: Any = None
        self.itemChanged = FakeSignal()
        self._vertical = FakeHeader()
        self._horizontal = FakeHeader()

    def setHorizontalHeaderLabels(self, headers: list[str]) -> None:
        self.headers = headers

    def setAlternatingRowColors(self, value: bool) -> None:
        self.alternating = value

    def setSelectionBehavior(self, value: Any) -> None:
        self.selection_behavior = value

    def setSelectionMode(self, value: Any) -> None:
        self.selection_mode = value

    def verticalHeader(self) -> FakeHeader:
        return self._vertical

    def horizontalHeader(self) -> FakeHeader:
        return self._horizontal


class FakeWidget:
    def __init__(self, *_args: Any) -> None:
        self.layout: Any = None


class FakeLayout:
    def __init__(self, host: Any | None = None) -> None:
        self.host = host
        self.items: list[Any] = []
        self.margins: tuple[int, int, int, int] | None = None
        self.spacing: int | None = None
        if host is not None:
            host.layout = self

    def setContentsMargins(self, *values: int) -> None:
        self.margins = values  # type: ignore[assignment]

    def setSpacing(self, value: int) -> None:
        self.spacing = value

    def addWidget(self, widget: Any, *_args: Any) -> None:
        self.items.append(("widget", widget))

    def addLayout(self, layout: Any) -> None:
        self.items.append(("layout", layout))

    def addRow(self, label: Any, widget: Any) -> None:
        self.items.append(("row", label, widget))

    def addStretch(self, value: int) -> None:
        self.items.append(("stretch", value))


class FakeButton:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.clicked = FakeSignal()


class FakePen:
    def __init__(self, color: Any) -> None:
        self.color = color
        self.width: int | None = None
        self.style: Any = None

    def setWidth(self, width: int) -> None:
        self.width = width

    def setStyle(self, style: Any) -> None:
        self.style = style


class FakeBrush:
    def __init__(self, color: Any) -> None:
        self.color = color


class FakeRect:
    def __init__(self) -> None:
        self.tooltip = ""
        self.pen: Any = None

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def setPen(self, pen: Any) -> None:
        self.pen = pen


class FakeTextItem:
    def __init__(self, text: str) -> None:
        self.text = text
        self.color: Any = None
        self.position: tuple[float, float] | None = None

    def setDefaultTextColor(self, color: Any) -> None:
        self.color = color

    def setPos(self, x: float, y: float) -> None:
        self.position = (x, y)


class FakeBounds:
    def adjusted(self, *values: int) -> tuple[int, ...]:
        return values


class FakeScene:
    def __init__(self, *_args: Any) -> None:
        self.calls: list[tuple[str, Any]] = []

    def clear(self) -> None:
        self.calls.append(("clear", None))

    def addText(self, text: str) -> FakeTextItem:
        self.calls.append(("text", text))
        return FakeTextItem(text)

    def addLine(self, *args: Any) -> None:
        self.calls.append(("line", args))

    def addRect(self, *args: Any) -> FakeRect:
        self.calls.append(("rect", args))
        return FakeRect()

    def itemsBoundingRect(self) -> FakeBounds:
        return FakeBounds()

    def setSceneRect(self, rect: Any) -> None:
        self.calls.append(("scene_rect", rect))


class FakeText:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.textChanged = FakeSignal()
        self.currentTextChanged = FakeSignal()
        self.clicked = FakeSignal()
        self.children_collapsible: bool | None = None
        self.movable: bool | None = None
        self.object_name = ""
        self.read_only: bool | None = None
        self.resizable: bool | None = None
        self.sizes: list[int] | None = None
        self.tooltip = ""
        self.widgets: list[Any] = []
        self.tabs: list[tuple[Any, str]] = []

    def text(self) -> str:
        return self.value

    def setText(self, value: object) -> None:
        self.value = str(value)

    def toPlainText(self) -> str:
        return self.value

    def setPlainText(self, value: object) -> None:
        self.value = str(value)

    def setPlaceholderText(self, value: object) -> None:
        self.placeholder = str(value)

    def setMinimumHeight(self, value: int) -> None:
        self.minimum_height = value

    def setReadOnly(self, value: bool) -> None:
        self.read_only = value

    def setLineWrapMode(self, value: object) -> None:
        self.line_wrap_mode = value

    def setObjectName(self, value: str) -> None:
        self.object_name = value

    def setToolTip(self, value: str) -> None:
        self.tooltip = value

    def setChildrenCollapsible(self, value: bool) -> None:
        self.children_collapsible = value

    def setWidgetResizable(self, value: bool) -> None:
        self.resizable = value

    def setWidget(self, widget: Any) -> None:
        self.widget = widget

    def addWidget(self, widget: Any, *_args: Any) -> None:
        self.widgets.append(widget)

    def setSizes(self, sizes: list[int]) -> None:
        self.sizes = sizes

    def addTab(self, widget: Any, title: str) -> None:
        self.tabs.append((widget, title))

    def addAction(self, action: Any) -> None:
        self.widgets.append(action)

    def setMovable(self, value: bool) -> None:
        self.movable = value


class FakePlainTextEdit(FakeText):
    class LineWrapMode:
        NoWrap = "nowrap"


class FakeChoice(FakeText):
    def currentText(self) -> str:
        return self.value

    def setCurrentText(self, value: object) -> None:
        self.value = str(value)


class FakeCheck:
    def __init__(self, checked: bool | str = False) -> None:
        self.checked = checked if isinstance(checked, bool) else False
        self.stateChanged = FakeSignal()

    def isChecked(self) -> bool:
        return self.checked

    def setChecked(self, checked: bool) -> None:
        self.checked = checked


class FakeList:
    def __init__(self) -> None:
        self.items: list[FakeItem | str] = []
        self.current = -1
        self.currentRowChanged = FakeSignal()

    def clear(self) -> None:
        self.items.clear()

    def addItem(self, item: FakeItem | str) -> None:
        self.items.append(item)

    def count(self) -> int:
        return len(self.items)

    def setCurrentRow(self, row: int) -> None:
        self.current = row

    def item(self, index: int) -> FakeItem | None:
        item = self.items[index] if 0 <= index < len(self.items) else None
        return item if isinstance(item, FakeItem) else None

    def currentRow(self) -> int:
        return self.current


class FakeStatusBar:
    def __init__(self, *_args: Any) -> None:
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.messages.append((message, timeout))


class FakeDataChoice:
    def __init__(self, data: object) -> None:
        self.data = data

    def currentData(self) -> object:
        return self.data


class FakeMessageBox:
    class StandardButton:
        Yes = 1
        No = 2

    def __init__(self) -> None:
        self.next_question: object = self.StandardButton.Yes
        self.calls: list[tuple[str, str, str]] = []

    def critical(self, _parent: object, title: str, message: str) -> None:
        self.calls.append(("critical", title, message))

    def warning(self, _parent: object, title: str, message: str) -> None:
        self.calls.append(("warning", title, message))

    def information(self, _parent: object, title: str, message: str) -> None:
        self.calls.append(("information", title, message))

    def question(
        self, _parent: object, title: str, message: str, *_args: object
    ) -> object:
        self.calls.append(("question", title, message))
        return self.next_question


class FakeClipboard:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class FakeApplication:
    clipboard_obj = FakeClipboard()
    instance_obj: object | None = None

    @classmethod
    def clipboard(cls) -> FakeClipboard:
        return cls.clipboard_obj

    @classmethod
    def instance(cls) -> object | None:
        return cls.instance_obj


class FakePalette:
    class ColorRole:
        Window = "window"
        WindowText = "window_text"
        Base = "base"
        Text = "text"
        Button = "button"
        ButtonText = "button_text"

    def __init__(self) -> None:
        self.colors: list[tuple[object, object]] = []

    def setColor(self, role: object, color: object) -> None:
        self.colors.append((role, color))


class FakeQtApp:
    def __init__(self) -> None:
        self.palette: object | None = None

    def setPalette(self, palette: object) -> None:
        self.palette = palette


class FakeFileDialog:
    open_files: list[str] = []
    save_files: list[str] = []
    directories: list[str] = []

    @classmethod
    def getOpenFileName(cls, *_args: object) -> tuple[str, str]:
        return (cls.open_files.pop(0) if cls.open_files else "", "")

    @classmethod
    def getSaveFileName(cls, *_args: object) -> tuple[str, str]:
        return (cls.save_files.pop(0) if cls.save_files else "", "")

    @classmethod
    def getExistingDirectory(cls, *_args: object) -> str:
        return cls.directories.pop(0) if cls.directories else ""


class FakeInputDialog:
    next_text = ""
    next_ok = False

    @classmethod
    def getText(cls, *_args: object) -> tuple[str, bool]:
        return cls.next_text, cls.next_ok


class FakeDialogCodes:
    class DialogCode:
        Accepted = 1


class FakeDialogBase:
    def __init__(self, *_args: Any) -> None:
        self.accepted = False
        self.rejected = False
        self.window_title = ""

    def accept(self) -> None:
        self.accepted = True

    def reject(self) -> None:
        self.rejected = True

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title


class FakeAction:
    def __init__(self, text: str, _parent: object | None = None) -> None:
        self.text = text
        self.shortcut = ""
        self.triggered = FakeSignal()

    def setShortcut(self, shortcut: str) -> None:
        self.shortcut = shortcut


class FakeDialogButtonBox:
    class StandardButton:
        Ok = 1
        Cancel = 2

    def __init__(self, _buttons: object) -> None:
        self.accepted = FakeSignal()
        self.rejected = FakeSignal()


class FakeMenuBar:
    def __init__(self) -> None:
        self.menus: list[FakeText] = []

    def addMenu(self, title: str) -> FakeText:
        menu = FakeText(title)
        self.menus.append(menu)
        return menu


class FakeNewBundleDialog:
    next_exec = 0

    def __init__(self, _parent: object) -> None:
        pass

    def exec(self) -> int:
        return self.next_exec

    def bundle(self) -> dict[str, Any]:
        return create_default_bundle("Dialog Project", "dialog_project", "dialog")


class FakeLauncherApp:
    instance_obj: "FakeLauncherApp | None" = None

    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.exec_called = False
        FakeLauncherApp.instance_obj = self

    @classmethod
    def instance(cls) -> "FakeLauncherApp | None":
        return cls.instance_obj

    def exec(self) -> int:
        self.exec_called = True
        return 17


class FakeLauncherWindow:
    last: ClassVar["FakeLauncherWindow | None"] = None

    def __init__(
        self, document: JtbdDocument, theme: dict[str, Any] | None = None
    ) -> None:
        self.document = document
        self.theme = theme
        self.shown = False
        FakeLauncherWindow.last = self

    def show(self) -> None:
        self.shown = True


def _make_window(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(app_module, "QTableWidgetItem", FakeItem, raising=False)
    monkeypatch.setattr(app_module, "QListWidgetItem", FakeItem, raising=False)
    monkeypatch.setattr(
        app_module,
        "Qt",
        types.SimpleNamespace(ItemDataRole=types.SimpleNamespace(UserRole="user")),
        raising=False,
    )
    window = app_module.JtbdEditorWindow.__new__(app_module.JtbdEditorWindow)
    window.document = JtbdDocument(create_default_bundle())
    window.current_index = 0
    window._loading = False
    window.template_library = {
        "templates": [
            {
                "id": "approval_intake",
                "name": "Approval intake",
                "description": "Approve one request",
                "jtbd": window.document.bundle["jtbds"][0],
            }
        ]
    }
    window.theme = app_module._load_theme(None)
    window._status = FakeStatusBar()
    window.statusBar = lambda: window._status
    titles: list[str] = []
    window.titles = titles
    window.setWindowTitle = lambda title: window.titles.append(title)
    window.setStyleSheet = lambda _stylesheet: None

    for name in [
        "project_name",
        "project_package",
        "project_domain",
        "project_languages",
        "project_currencies",
        "project_compliance",
        "project_sensitivity",
        "design_primary",
        "design_accent",
        "design_font",
        "design_radius",
        "shared_roles",
        "shared_permissions",
        "job_id",
        "job_title",
        "job_version",
        "actor_role",
        "actor_department",
        "sla_warn",
        "sla_breach",
        "job_compliance",
        "job_sensitivity",
        "project_tags",
        "job_tags",
    ]:
        setattr(window, name, FakeText())
    for name in [
        "project_notes",
        "job_notes",
        "situation",
        "motivation",
        "outcome",
        "json_preview",
        "validation_box",
        "ai_prompt",
        "ai_output",
    ]:
        setattr(window, name, FakeText())
    window.project_tenancy = FakeChoice("multi")
    window.project_renderer = FakeChoice("real")
    window.design_density = FakeChoice("comfortable")
    window.job_status = FakeChoice("draft")
    window.actor_external = FakeCheck(False)

    window.shared_entities = FakeTable(2)
    window.success_table = FakeTable(1)
    window.fields_table = FakeTable(6)
    window.edges_table = FakeTable(4)
    window.docs_table = FakeTable(5)
    window.approvals_table = FakeTable(4)
    window.notifications_table = FakeTable(3)
    window.metrics_table = FakeTable(1)
    window.requires_table = FakeTable(1)
    window.job_list = FakeList()
    window.template_list = FakeList()
    window.visual_dependency_source = FakeDataChoice(0)
    window.visual_dependency_target = FakeDataChoice("intake_case")
    refreshes: list[str] = []
    window.refreshes = refreshes
    window._refresh_visual_map = lambda: window.refreshes.append("visual")
    window._refresh_all = lambda: window.refreshes.append("all")
    return window


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
    app_module._mutate_table(
        strings, app_module._add_empty_row, lambda: calls.append("changed")
    )
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
            ["amount", "number", "", "false", "", ""],
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
        },
        {
            "id": "amount",
            "kind": "number",
            "label": "Amount",
            "required": False,
            "pii": False,
            "validation": {},
            "sensitivity": [],
        },
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
    app_module._set_rows(
        edges,
        [["large_loss", "amount > 100", "branch", "review"], ["", "ignored", "", ""]],
    )
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
    app_module._set_rows(
        docs, [["identity", "2", "5", "30", "yes"], ["", "9", "", "", ""]]
    )
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
            ["", "ignored", "", ""],
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
    assert app_module._entity_rows(entities) == [
        {"name": "claim", "id_field": "claim_id"}
    ]
    rendered_entities = FakeTable(2)
    app_module._set_entity_rows(
        rendered_entities, [{"name": "case", "id_field": "case_id"}]
    )
    assert app_module._entity_rows(rendered_entities) == [
        {"name": "case", "id_field": "case_id"}
    ]


def test_window_refresh_commit_and_validation_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(monkeypatch)
    window.document.bundle["jtbds"].append(
        {
            **window.document.bundle["jtbds"][0],
            "id": "review_case",
            "title": "Review case",
        }
    )
    window.current_index = 1

    app_module.JtbdEditorWindow._refresh_all(window)

    assert window.job_list.count() == 2
    assert window.job_id.text() == "review_case"
    assert "Ready for generation" in window.validation_box.toPlainText()
    assert window.titles[-1] == "Flowforge JTBD Editor - Untitled"

    window.project_name.setText(" Claims Platform ")
    window.project_package.setText(" claims_pkg ")
    window.project_domain.setText(" claims ")
    window.project_languages.setText(" en, fr ")
    window.project_currencies.setText(" USD, KES ")
    window.project_compliance.setText(" gdpr, custom ")
    window.project_sensitivity.setText(" pii, secret-ish ")
    window.project_notes.setPlainText(" Project note ")
    window.project_tags.setText(" ops, beta ")
    window.design_primary.setText("#111827")
    window.design_accent.setText("#22c55e")
    window.design_font.setText("Inter")
    window.design_radius.setText("soft")
    window.shared_roles.setText(" requester, reviewer ")
    window.shared_permissions.setText(" case.submit, case.review ")
    app_module._set_rows(window.shared_entities, [["case", ""]])
    window.job_id.setText("intake_case")
    window.job_title.setText("Duplicate id while typing")
    window.job_version.setText("")
    window.actor_role.setText("requester")
    window.actor_department.setText("Operations")
    window.actor_external.setChecked(True)
    window.sla_warn.setText("not-a-number")
    window.sla_breach.setText("3600")
    window.job_compliance.setText("SOX")
    window.job_sensitivity.setText("PHI")
    window.job_notes.setPlainText(" Job note ")
    window.job_tags.setText(" reviewed ")
    window.situation.setPlainText("Situation")
    window.motivation.setPlainText("Motivation")
    window.outcome.setPlainText("Outcome")
    app_module._set_rows(window.success_table, [["done"]])
    app_module._set_rows(
        window.fields_table, [["email", "email", "", "true", "", "PII"]]
    )
    app_module._set_rows(
        window.edges_table, [["large_loss", "amount > 100", "branch", "review_case"]]
    )
    app_module._set_rows(window.docs_table, [["identity", "2", "", "", "true"]])
    app_module._set_rows(window.approvals_table, [["reviewer", "1_of_1", "", ""]])
    app_module._set_rows(window.notifications_table, [["", "", "ops"]])
    app_module._set_rows(window.metrics_table, [["cycle_time"]])
    app_module._set_rows(window.requires_table, [["intake_case"]])

    app_module.JtbdEditorWindow._commit_forms(window)

    project = window.document.bundle["project"]
    jtbd = window.document.get_jtbd(1)
    assert project["name"] == "Claims Platform"
    assert project["languages"] == ["en", "fr"]
    assert project["compliance"] == ["GDPR", "custom"]
    assert project["data_sensitivity"] == ["PII", "secret-ish"]
    assert project["design"]["radius_scale"] == "soft"
    assert window.document.bundle["shared"]["entities"] == [
        {"name": "case", "id_field": "case_id"}
    ]
    assert jtbd["id"] == "intake_case"
    assert jtbd["actor"]["department"] == "Operations"
    assert jtbd["sla"] == {"warn_pct": 80, "breach_seconds": 3600}
    assert jtbd["data_capture"][0]["pii"] is True
    assert "spec_hash" not in jtbd

    window._loading = True
    window.document.dirty = False
    app_module.JtbdEditorWindow._mark_dirty_from_widgets(window)
    assert window.document.dirty is False
    window._loading = False
    app_module.JtbdEditorWindow._mark_dirty_from_widgets(window)
    assert window.document.dirty is True
    assert " *" in window.titles[-1]

    window.job_list.items = [FakeItem("old"), "not-an-item"]
    window.document.bundle["jtbds"][0]["title"] = "Updated title"
    app_module.JtbdEditorWindow._refresh_job_list_labels(window)
    assert window.job_list.item(0).text() == "Updated title"

    window._loading = False
    app_module.JtbdEditorWindow._on_select_job(window, -1)
    assert window.current_index == 1
    app_module.JtbdEditorWindow._on_select_job(window, 0)
    assert window.current_index == 0


def test_window_actions_with_faked_dialogs_and_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(monkeypatch)
    message_box = FakeMessageBox()
    monkeypatch.setattr(app_module, "QMessageBox", message_box, raising=False)
    monkeypatch.setattr(app_module, "QApplication", FakeApplication, raising=False)

    app_module.JtbdEditorWindow._prepare_copy_polish(window)
    assert "Save the bundle first" in window.ai_output.toPlainText()
    window.document.path = tmp_path / "bundle.json"
    app_module.JtbdEditorWindow._prepare_copy_polish(window)
    assert "flowforge polish-copy --bundle" in window.ai_output.toPlainText()

    window.ai_prompt.setPlainText("")
    app_module.JtbdEditorWindow._draft_jtbd_with_ai(window)
    assert message_box.calls[-1] == (
        "warning",
        "AI Assist",
        "Enter a JTBD prompt first.",
    )
    window.ai_prompt.setPlainText("Collect customer email for approval")
    app_module.JtbdEditorWindow._draft_jtbd_with_ai(window)
    assert window.current_index == 1
    assert "data_capture" in window.ai_output.toPlainText()

    app_module.JtbdEditorWindow._copy_ai_review_prompt(window)
    assert FakeApplication.clipboard_obj.text == window.ai_output.toPlainText()
    assert window._status.messages[-1] == ("AI review prompt copied", 3000)

    window.template_list.current = -1
    app_module.JtbdEditorWindow._add_from_template(window)
    assert message_box.calls[-1] == ("warning", "Templates", "Select a template first.")
    window.template_list.current = 0
    app_module.JtbdEditorWindow._add_from_template(window)
    assert window.current_index == 2

    before = len(window.template_library["templates"])
    app_module.JtbdEditorWindow._capture_template(window)
    assert len(window.template_library["templates"]) == before + 1
    assert window._status.messages[-1] == ("Template captured", 3000)

    window.document.get_jtbd(0)["id"] = "intake_case"
    window.document.get_jtbd(1)["id"] = "draft_case"
    window.job_id.setText(str(window.document.get_jtbd(window.current_index)["id"]))
    window.visual_dependency_source = FakeDataChoice("not-index")
    app_module.JtbdEditorWindow._add_visual_dependency(window)
    assert window.current_index == 2
    window.visual_dependency_source = FakeDataChoice(0)
    window.visual_dependency_target = FakeDataChoice("missing")
    app_module.JtbdEditorWindow._add_visual_dependency(window)
    assert message_box.calls[-1][0:2] == ("warning", "Visual Composition")
    target_id = window.document.get_jtbd(1)["id"]
    window.visual_dependency_target = FakeDataChoice(target_id)
    app_module.JtbdEditorWindow._add_visual_dependency(window)
    assert target_id in window.document.get_jtbd(0)["requires"]
    app_module.JtbdEditorWindow._remove_visual_dependency(window)
    assert target_id not in window.document.get_jtbd(0)["requires"]

    window.document.dirty = False
    assert app_module.JtbdEditorWindow._confirm_discard(window) is True
    window.document.dirty = True
    message_box.next_question = message_box.StandardButton.No
    assert app_module.JtbdEditorWindow._confirm_discard(window) is False

    class FakeEvent:
        def __init__(self) -> None:
            self.accepted = False
            self.ignored = False

        def accept(self) -> None:
            self.accepted = True

        def ignore(self) -> None:
            self.ignored = True

    event = FakeEvent()
    app_module.JtbdEditorWindow.closeEvent(window, event)
    assert event.ignored is True
    message_box.next_question = message_box.StandardButton.Yes
    event = FakeEvent()
    app_module.JtbdEditorWindow.closeEvent(window, event)
    assert event.accepted is True

    result = types.SimpleNamespace(
        errors=["broken"],
        warnings=["risky"],
        infos=["note"],
    )
    app_module.JtbdEditorWindow._append_validation_result(window, "Heading", result)
    assert window.validation_box.toPlainText().splitlines() == [
        "Heading",
        "ERROR: broken",
        "WARN: risky",
        "INFO: note",
    ]


def test_window_file_and_generation_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(monkeypatch)
    window.job_id.setText("intake_case")
    window.job_title.setText("Intake case")
    message_box = FakeMessageBox()
    monkeypatch.setattr(app_module, "QMessageBox", message_box, raising=False)
    monkeypatch.setattr(app_module, "QFileDialog", FakeFileDialog, raising=False)
    monkeypatch.setattr(app_module, "QInputDialog", FakeInputDialog, raising=False)
    monkeypatch.setattr(app_module, "QDialog", FakeDialogCodes, raising=False)

    monkeypatch.setattr(app_module, "NewBundleDialog", FakeNewBundleDialog)
    window.document.dirty = True
    message_box.next_question = message_box.StandardButton.No
    app_module.JtbdEditorWindow._new_bundle(window)
    assert "all" not in window.refreshes
    message_box.next_question = message_box.StandardButton.Yes
    FakeNewBundleDialog.next_exec = 0
    app_module.JtbdEditorWindow._new_bundle(window)
    assert "all" not in window.refreshes
    FakeNewBundleDialog.next_exec = FakeDialogCodes.DialogCode.Accepted
    app_module.JtbdEditorWindow._new_bundle(window)
    assert window.document.bundle["project"]["name"] == "Dialog Project"
    assert "all" in window.refreshes

    FakeFileDialog.open_files = [""]
    app_module.JtbdEditorWindow._open_bundle(window)
    window.document.dirty = True
    message_box.next_question = message_box.StandardButton.No
    FakeFileDialog.open_files = [str(tmp_path / "should-not-open.json")]
    app_module.JtbdEditorWindow._open_bundle(window)
    assert FakeFileDialog.open_files == [str(tmp_path / "should-not-open.json")]
    message_box.next_question = message_box.StandardButton.Yes
    window.document.dirty = False
    error_path = tmp_path / "bad.json"
    error_path.write_text("not-json", encoding="utf-8")
    FakeFileDialog.open_files = [str(error_path)]
    app_module.JtbdEditorWindow._open_bundle(window)
    assert message_box.calls[-1][0:2] == ("critical", "Open failed")
    ok_path = tmp_path / "bundle.json"
    ok_path.write_text(json.dumps(create_default_bundle()), encoding="utf-8")
    FakeFileDialog.open_files = [str(ok_path)]
    app_module.JtbdEditorWindow._open_bundle(window)
    assert window.document.path == ok_path

    FakeInputDialog.next_text = ""
    FakeInputDialog.next_ok = True
    app_module.JtbdEditorWindow._add_job(window)
    current = window.current_index
    FakeInputDialog.next_text = "Review case"
    FakeInputDialog.next_ok = True
    app_module.JtbdEditorWindow._add_job(window)
    assert window.current_index != current

    app_module.JtbdEditorWindow._duplicate_job(window)
    assert window.current_index == len(window.document.bundle["jtbds"]) - 1
    message_box.next_question = message_box.StandardButton.No
    app_module.JtbdEditorWindow._delete_job(window)
    assert message_box.calls[-1][0:2] == ("question", "Delete Job")
    message_box.next_question = message_box.StandardButton.Yes
    app_module.JtbdEditorWindow._delete_job(window)
    assert window.current_index >= 0

    app_module.JtbdEditorWindow._save(window)
    assert window.document.path == ok_path
    original_save = window.document.save

    def fail_save(path: Path | None = None) -> None:
        assert path is None
        raise OSError("disk full")

    monkeypatch.setattr(window.document, "save", fail_save)
    app_module.JtbdEditorWindow._save(window)
    assert message_box.calls[-1] == ("critical", "Save failed", "disk full")
    monkeypatch.setattr(window.document, "save", original_save)
    app_module.JtbdEditorWindow._save(window)
    assert window._status.messages[-1] == ("Saved", 3000)

    FakeFileDialog.save_files = [""]
    app_module.JtbdEditorWindow._save_as(window)
    FakeFileDialog.save_files = [str(tmp_path / "save-as.json")]
    app_module.JtbdEditorWindow._save_as(window)
    assert window.document.path == tmp_path / "save-as.json"

    monkeypatch.setattr(
        window.document, "validate", lambda: ValidationResult(True, [], [], [])
    )
    app_module.JtbdEditorWindow._validate_now(window)
    assert message_box.calls[-1] == ("information", "Validation", "Bundle is valid.")
    monkeypatch.setattr(
        window.document, "validate", lambda: ValidationResult(False, ["bad"], [], [])
    )
    app_module.JtbdEditorWindow._validate_now(window)
    assert message_box.calls[-1][0:2] == ("warning", "Validation")

    monkeypatch.setattr(
        app_module,
        "verify_generation",
        lambda _bundle: types.SimpleNamespace(
            ok=True, errors=[], warnings=[], infos=["generation emits 1 files"]
        ),
    )
    app_module.JtbdEditorWindow._verify_generation(window)
    assert message_box.calls[-1][0:2] == ("information", "Verify Generation")
    monkeypatch.setattr(
        app_module,
        "verify_generation",
        lambda _bundle: types.SimpleNamespace(
            ok=False, errors=["bad"], warnings=[], infos=[]
        ),
    )
    app_module.JtbdEditorWindow._verify_generation(window)
    assert message_box.calls[-1][0:2] == ("warning", "Verify Generation")

    monkeypatch.setattr(
        window.document, "validate", lambda: ValidationResult(False, ["bad"], [], [])
    )
    app_module.JtbdEditorWindow._generate_app(window)
    assert message_box.calls[-1][0:2] == ("warning", "Generate App")
    monkeypatch.setattr(
        window.document, "validate", lambda: ValidationResult(True, [], [], [])
    )
    FakeFileDialog.directories = [""]
    app_module.JtbdEditorWindow._generate_app(window)
    out_dir = tmp_path / "generated"
    out_dir.mkdir()
    (out_dir / "existing.txt").write_text("existing", encoding="utf-8")
    FakeFileDialog.directories = [str(out_dir)]
    message_box.next_question = message_box.StandardButton.No
    app_module.JtbdEditorWindow._generate_app(window)
    assert message_box.calls[-1][0:2] == ("question", "Generate App")
    FakeFileDialog.directories = [str(out_dir)]
    message_box.next_question = message_box.StandardButton.Yes

    class FakeGeneratedFile:
        path = "nested/file.txt"
        content = "generated"

    monkeypatch.setattr(app_module, "generate", lambda _bundle: [FakeGeneratedFile()])
    app_module.JtbdEditorWindow._generate_app(window)
    assert (out_dir / "nested" / "file.txt").read_text(encoding="utf-8") == "generated"
    assert message_box.calls[-1][0:2] == ("information", "Generate App")

    FakeFileDialog.open_files = [""]
    app_module.JtbdEditorWindow._load_templates(window)
    template_file = tmp_path / "templates.json"
    template_file.write_text(json.dumps({"templates": "bad"}), encoding="utf-8")
    FakeFileDialog.open_files = [str(template_file)]
    app_module.JtbdEditorWindow._load_templates(window)
    assert message_box.calls[-1][0:2] == ("critical", "Load templates failed")

    FakeFileDialog.save_files = [""]
    app_module.JtbdEditorWindow._save_templates(window)
    FakeFileDialog.save_files = [str(tmp_path / "templates-out.json")]
    app_module.JtbdEditorWindow._save_templates(window)
    assert window._status.messages[-1] == ("Templates saved", 3000)


def test_window_remaining_action_error_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(monkeypatch)
    message_box = FakeMessageBox()
    monkeypatch.setattr(app_module, "QMessageBox", message_box, raising=False)
    monkeypatch.setattr(app_module, "QFileDialog", FakeFileDialog, raising=False)

    window._loading = True
    window.project_name.setText("Should not commit")
    app_module.JtbdEditorWindow._commit_forms(window)
    assert window.document.bundle["project"]["name"] == "New Flowforge Project"
    window._loading = False

    window.document.bundle["jtbds"] = []
    app_module.JtbdEditorWindow._load_job_form(window, 0)
    window.document = JtbdDocument(create_default_bundle())

    window.document.path = None
    called: list[str] = []
    window._save_as = lambda: called.append("save_as")
    app_module.JtbdEditorWindow._save(window)
    assert called == ["save_as"]

    window._save_as = types.MethodType(app_module.JtbdEditorWindow._save_as, window)

    def fail_save_as(path: Path | None = None) -> None:
        assert path is not None
        raise OSError("cannot write")

    monkeypatch.setattr(window.document, "save", fail_save_as)
    FakeFileDialog.save_files = [str(tmp_path / "bad-save.json")]
    app_module.JtbdEditorWindow._save_as(window)
    assert message_box.calls[-1] == ("critical", "Save failed", "cannot write")

    def fail_prompt(prompt: str) -> int:
        assert prompt == "Draft this job"
        raise ValueError("bad prompt")

    monkeypatch.setattr(window.document, "add_jtbd_from_prompt", fail_prompt)
    window.ai_prompt.setPlainText("Draft this job")
    app_module.JtbdEditorWindow._draft_jtbd_with_ai(window)
    assert message_box.calls[-1] == ("warning", "AI Assist", "bad prompt")

    monkeypatch.setattr(
        window.document, "validate", lambda: ValidationResult(True, [], [], [])
    )
    FakeFileDialog.directories = [str(tmp_path / "out")]
    monkeypatch.setattr(
        app_module,
        "generate",
        lambda _bundle: (_ for _ in ()).throw(ValueError("generator failed")),
    )
    app_module.JtbdEditorWindow._generate_app(window)
    assert message_box.calls[-1] == (
        "critical",
        "Generate App failed",
        "generator failed",
    )

    good_templates = tmp_path / "good-templates.json"
    good_templates.write_text(
        json.dumps({"templates": window.template_library["templates"]}),
        encoding="utf-8",
    )
    FakeFileDialog.open_files = [str(good_templates)]
    app_module.JtbdEditorWindow._load_templates(window)
    assert window.template_list.count() == 1

    monkeypatch.setattr(
        app_module,
        "save_template_library",
        lambda _path, _data: (_ for _ in ()).throw(OSError("template disk full")),
    )
    FakeFileDialog.save_files = [str(tmp_path / "bad-templates.json")]
    app_module.JtbdEditorWindow._save_templates(window)
    assert message_box.calls[-1] == (
        "critical",
        "Save templates failed",
        "template disk full",
    )

    window.document = JtbdDocument(create_default_bundle())
    message_box.next_question = message_box.StandardButton.Yes
    app_module.JtbdEditorWindow._delete_job(window)
    assert message_box.calls[-1] == (
        "warning",
        "Cannot delete",
        "a JTBD bundle must contain at least one job",
    )

    window.visual_dependency_source = FakeDataChoice(0)
    window.visual_dependency_target = FakeDataChoice(123)
    app_module.JtbdEditorWindow._remove_visual_dependency(window)
    assert window.current_index == 0


def test_window_apply_theme_with_fake_qapplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(monkeypatch)
    fake_app = FakeQtApp()
    FakeApplication.instance_obj = fake_app
    monkeypatch.setattr(app_module, "QApplication", FakeApplication, raising=False)
    monkeypatch.setattr(app_module, "QPalette", FakePalette, raising=False)
    monkeypatch.setattr(app_module, "QColor", lambda value: value, raising=False)

    app_module.JtbdEditorWindow._apply_theme(window)

    assert isinstance(fake_app.palette, FakePalette)
    assert len(fake_app.palette.colors) == 6

    FakeApplication.instance_obj = None
    app_module.JtbdEditorWindow._apply_theme(window)


def test_visual_map_and_dependency_control_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(monkeypatch)
    window.document.bundle["jtbds"] = []
    window.visual_scene = FakeScene()
    window.visual_dependency_source = FakeCombo([])
    window.visual_dependency_target = FakeCombo([])
    app_module.JtbdEditorWindow._refresh_visual_map(window)
    assert window.visual_scene.calls == [("clear", None)]

    window.document.bundle["jtbds"] = [
        {
            "id": "intake_case",
            "title": "Intake",
            "requires": [],
        },
        {
            "id": "review_case",
            "title": "Review",
            "requires": ["intake_case", "missing_case"],
        },
        {
            "title": "No id",
            "requires": [],
        },
    ]
    window.current_index = 1
    window.visual_dependency_source = FakeCombo([1])
    window.visual_dependency_source.current_index = 0
    window.visual_dependency_target = FakeCombo(["review_case"])
    window.visual_dependency_target.current_index = 0
    window.visual_scene = FakeScene()
    monkeypatch.setattr(app_module, "QPen", FakePen, raising=False)
    monkeypatch.setattr(app_module, "QBrush", FakeBrush, raising=False)
    monkeypatch.setattr(app_module, "QColor", lambda value: value, raising=False)
    monkeypatch.setattr(
        app_module,
        "Qt",
        types.SimpleNamespace(
            ItemDataRole=types.SimpleNamespace(UserRole="user"),
            PenStyle=types.SimpleNamespace(DashLine="dash"),
        ),
        raising=False,
    )

    app_module.JtbdEditorWindow._refresh_visual_map(window)

    assert (
        "text",
        "Missing dependency: missing_case -> review_case",
    ) in window.visual_scene.calls
    assert any(call[0] == "line" for call in window.visual_scene.calls)
    assert sum(1 for call in window.visual_scene.calls if call[0] == "rect") == 3
    assert window.visual_dependency_source.values == [0, 1, 2]
    assert window.visual_dependency_source.current_index == 1
    assert window.visual_dependency_target.values == ["intake_case", "review_case", ""]
    assert window.visual_dependency_target.current_index == 1
    assert window.visual_dependency_source.blocked == [True, False]
    assert window.visual_dependency_target.blocked == [True, False]


def test_widget_factory_helpers_with_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "QComboBox", FakeConnectComboBox, raising=False)
    combo = app_module._combo(["draft", "published"])
    assert combo.values == ["draft", "published"]

    calls: list[str] = []

    def slot() -> None:
        calls.append("changed")

    line = FakeConnectLineEdit()
    plain = FakeConnectPlainTextEdit()
    box = FakeConnectComboBox()
    check = FakeConnectCheckBox()
    unknown = object()
    monkeypatch.setattr(app_module, "QLineEdit", FakeConnectLineEdit, raising=False)
    monkeypatch.setattr(
        app_module, "QPlainTextEdit", FakeConnectPlainTextEdit, raising=False
    )
    monkeypatch.setattr(app_module, "QComboBox", FakeConnectComboBox, raising=False)
    monkeypatch.setattr(app_module, "QCheckBox", FakeConnectCheckBox, raising=False)

    for widget in [line, plain, box, check, unknown]:
        app_module._connect_change(widget, slot)
    for signal in [
        line.textChanged,
        plain.textChanged,
        box.currentTextChanged,
        check.stateChanged,
    ]:
        signal.emit()
    assert calls == ["changed", "changed", "changed", "changed"]

    monkeypatch.setattr(app_module, "QTableWidget", FakeQTableWidget, raising=False)
    monkeypatch.setattr(
        app_module,
        "QAbstractItemView",
        types.SimpleNamespace(
            SelectionBehavior=types.SimpleNamespace(SelectRows="rows"),
            SelectionMode=types.SimpleNamespace(SingleSelection="single"),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        app_module,
        "QHeaderView",
        types.SimpleNamespace(
            ResizeMode=types.SimpleNamespace(ResizeToContents="resize")
        ),
        raising=False,
    )
    table = app_module._table(["A", "B"], stretch_last=True)
    assert table.headers == ["A", "B"]
    assert table.horizontalHeader().stretch_last is True
    table = app_module._table(["A"], stretch_last=False)
    assert table.horizontalHeader().stretch_last is False

    monkeypatch.setattr(app_module, "QWidget", FakeWidget, raising=False)
    monkeypatch.setattr(app_module, "QVBoxLayout", FakeLayout, raising=False)
    monkeypatch.setattr(app_module, "QHBoxLayout", FakeLayout, raising=False)
    monkeypatch.setattr(app_module, "QPushButton", FakeButton, raising=False)
    monkeypatch.setattr(app_module, "QTableWidgetItem", FakeItem, raising=False)
    mutations: list[str] = []
    panel = app_module._table_panel(table, lambda: mutations.append("changed"))
    button_layout = panel.layout.items[0][1]
    add_button = button_layout.items[0][1]
    remove_button = button_layout.items[1][1]
    add_button.clicked.emit()
    table._current = 0
    remove_button.clicked.emit()
    assert mutations == ["changed", "changed"]


def test_editor_window_constructor_builds_with_gui_fakes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "QAction", FakeAction, raising=False)
    monkeypatch.setattr(app_module, "QApplication", FakeApplication, raising=False)
    monkeypatch.setattr(app_module, "QBrush", FakeBrush, raising=False)
    monkeypatch.setattr(app_module, "QColor", lambda value: value, raising=False)
    monkeypatch.setattr(app_module, "QPalette", FakePalette, raising=False)
    monkeypatch.setattr(app_module, "QPen", FakePen, raising=False)
    monkeypatch.setattr(app_module, "QCheckBox", FakeCheck, raising=False)
    monkeypatch.setattr(app_module, "QComboBox", FakeCombo, raising=False)
    monkeypatch.setattr(
        app_module, "QDialogButtonBox", FakeDialogButtonBox, raising=False
    )
    monkeypatch.setattr(app_module, "QFormLayout", FakeLayout, raising=False)
    monkeypatch.setattr(app_module, "QFrame", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QGraphicsScene", FakeScene, raising=False)
    monkeypatch.setattr(app_module, "QGraphicsView", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QGridLayout", FakeLayout, raising=False)
    monkeypatch.setattr(app_module, "QGroupBox", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QHBoxLayout", FakeLayout, raising=False)
    monkeypatch.setattr(app_module, "QLabel", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QLineEdit", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QListWidget", FakeList, raising=False)
    monkeypatch.setattr(app_module, "QListWidgetItem", FakeItem, raising=False)
    monkeypatch.setattr(app_module, "QPlainTextEdit", FakePlainTextEdit, raising=False)
    monkeypatch.setattr(app_module, "QPushButton", FakeButton, raising=False)
    monkeypatch.setattr(app_module, "QScrollArea", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QSplitter", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QStatusBar", FakeStatusBar, raising=False)
    monkeypatch.setattr(app_module, "QTabWidget", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QTableWidget", FakeQTableWidget, raising=False)
    monkeypatch.setattr(app_module, "QTableWidgetItem", FakeItem, raising=False)
    monkeypatch.setattr(app_module, "QTextEdit", FakeText, raising=False)
    monkeypatch.setattr(app_module, "QVBoxLayout", FakeLayout, raising=False)
    monkeypatch.setattr(app_module, "QWidget", FakeText, raising=False)
    monkeypatch.setattr(
        app_module,
        "QAbstractItemView",
        types.SimpleNamespace(
            SelectionBehavior=types.SimpleNamespace(SelectRows="rows"),
            SelectionMode=types.SimpleNamespace(SingleSelection="single"),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        app_module,
        "QHeaderView",
        types.SimpleNamespace(
            ResizeMode=types.SimpleNamespace(
                ResizeToContents="resize", Stretch="stretch"
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        app_module,
        "Qt",
        types.SimpleNamespace(
            Orientation=types.SimpleNamespace(Horizontal="horizontal"),
            ItemDataRole=types.SimpleNamespace(UserRole="user"),
            PenStyle=types.SimpleNamespace(DashLine="dash"),
        ),
        raising=False,
    )

    titles: list[str] = []
    central_widgets: list[Any] = []
    status_bars: list[Any] = []
    styles: list[str] = []
    menu_bar = FakeMenuBar()
    toolbars: list[FakeText] = []

    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "setWindowTitle",
        lambda _self, title: titles.append(title),
        raising=False,
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow, "resize", lambda *_args: None, raising=False
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "setMinimumSize",
        lambda *_args: None,
        raising=False,
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow, "menuBar", lambda _self: menu_bar, raising=False
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "addToolBar",
        lambda _self, title: toolbars.append(FakeText(title)) or toolbars[-1],
        raising=False,
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "setStatusBar",
        lambda _self, status: status_bars.append(status),
        raising=False,
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "statusBar",
        lambda _self: status_bars[-1],
        raising=False,
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "setCentralWidget",
        lambda _self, widget: central_widgets.append(widget),
        raising=False,
    )
    monkeypatch.setattr(
        app_module.JtbdEditorWindow,
        "setStyleSheet",
        lambda _self, style: styles.append(style),
        raising=False,
    )
    FakeApplication.instance_obj = None

    window = app_module.JtbdEditorWindow(
        JtbdDocument(create_default_bundle()), theme={"primary": "#123456"}
    )

    assert window.job_list.count() == 1
    assert window.project_name.text() == "New Flowforge Project"
    assert window.visual_scene.calls[0] == ("clear", None)
    assert titles[-1] == "Flowforge JTBD Editor - Untitled"
    assert len(menu_bar.menus) == 3
    assert len(toolbars) == 1
    assert central_widgets
    assert isinstance(status_bars[-1], FakeStatusBar)
    assert "#123456" in styles[-1]


def test_launcher_success_path_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(create_default_bundle()), encoding="utf-8")
    theme_path = tmp_path / "theme.json"
    theme_path.write_text(json.dumps({"primary": "#123456"}), encoding="utf-8")
    FakeLauncherApp.instance_obj = None
    FakeLauncherWindow.last = None
    monkeypatch.setattr(app_module, "Qt", object(), raising=False)
    monkeypatch.setattr(app_module, "QApplication", FakeLauncherApp, raising=False)
    monkeypatch.setattr(
        app_module, "JtbdEditorWindow", FakeLauncherWindow, raising=False
    )

    assert app_module.run_desktop_editor(bundle=bundle_path, theme=theme_path) == 17

    assert FakeLauncherWindow.last is not None
    assert FakeLauncherWindow.last.shown is True
    assert FakeLauncherWindow.last.document.path == bundle_path
    assert FakeLauncherWindow.last.theme == {"primary": "#123456"}

    FakeLauncherWindow.last = None
    existing = FakeLauncherApp(["existing"])
    monkeypatch.setattr(
        FakeLauncherApp,
        "instance",
        classmethod(lambda cls: existing),
    )
    assert app_module.run_desktop_editor() == 17
    assert FakeLauncherWindow.last is not None
    assert FakeLauncherWindow.last.document.path is None


def test_new_bundle_dialog_bundle_uses_field_values() -> None:
    dialog = app_module.NewBundleDialog.__new__(app_module.NewBundleDialog)
    dialog.name = FakeText("")
    dialog.package = FakeText("")
    dialog.domain = FakeText("")
    dialog.job_title = FakeText("Review Claim")

    bundle = app_module.NewBundleDialog.bundle(dialog)

    assert bundle["project"]["name"] == "New Flowforge Project"
    assert bundle["project"]["package"] == "new_flowforge_project"
    assert bundle["project"]["domain"] == "case"
    assert bundle["jtbds"][0]["id"] == "review_claim"
    assert bundle["jtbds"][0]["title"] == "Review Claim"


def test_new_bundle_dialog_constructor_with_fake_pyqt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pyqt = types.ModuleType("PyQt6")
    qt_core = types.ModuleType("PyQt6.QtCore")
    qt_gui = types.ModuleType("PyQt6.QtGui")
    qt_widgets = types.ModuleType("PyQt6.QtWidgets")
    setattr(
        qt_core,
        "Qt",
        types.SimpleNamespace(
            Orientation=types.SimpleNamespace(Horizontal="horizontal"),
            ItemDataRole=types.SimpleNamespace(UserRole="user"),
            PenStyle=types.SimpleNamespace(DashLine="dash"),
        ),
    )
    for name, value in {
        "QAction": FakeAction,
        "QBrush": FakeBrush,
        "QColor": lambda value: value,
        "QPalette": FakePalette,
        "QPen": FakePen,
    }.items():
        setattr(qt_gui, name, value)
    for name, value in {
        "QAbstractItemView": types.SimpleNamespace(
            SelectionBehavior=types.SimpleNamespace(SelectRows="rows"),
            SelectionMode=types.SimpleNamespace(SingleSelection="single"),
        ),
        "QApplication": FakeApplication,
        "QCheckBox": FakeCheck,
        "QComboBox": FakeCombo,
        "QDialog": FakeDialogBase,
        "QDialogButtonBox": FakeDialogButtonBox,
        "QFileDialog": FakeFileDialog,
        "QFormLayout": FakeLayout,
        "QFrame": FakeText,
        "QGraphicsScene": FakeScene,
        "QGraphicsView": FakeText,
        "QGridLayout": FakeLayout,
        "QGroupBox": FakeText,
        "QHBoxLayout": FakeLayout,
        "QHeaderView": types.SimpleNamespace(
            ResizeMode=types.SimpleNamespace(
                ResizeToContents="resize", Stretch="stretch"
            )
        ),
        "QInputDialog": FakeInputDialog,
        "QLabel": FakeText,
        "QLineEdit": FakeText,
        "QListWidget": FakeList,
        "QListWidgetItem": FakeItem,
        "QMainWindow": FakeDialogBase,
        "QMessageBox": FakeMessageBox,
        "QPlainTextEdit": FakePlainTextEdit,
        "QPushButton": FakeButton,
        "QScrollArea": FakeText,
        "QSplitter": FakeText,
        "QStatusBar": FakeStatusBar,
        "QTabWidget": FakeText,
        "QTableWidget": FakeQTableWidget,
        "QTableWidgetItem": FakeItem,
        "QTextEdit": FakeText,
        "QVBoxLayout": FakeLayout,
        "QWidget": FakeText,
    }.items():
        setattr(qt_widgets, name, value)

    with monkeypatch.context() as context:
        context.setitem(sys.modules, "PyQt6", pyqt)
        context.setitem(sys.modules, "PyQt6.QtCore", qt_core)
        context.setitem(sys.modules, "PyQt6.QtGui", qt_gui)
        context.setitem(sys.modules, "PyQt6.QtWidgets", qt_widgets)
        reloaded = importlib.reload(app_module)
        dialog = reloaded.NewBundleDialog()

        assert dialog.window_title == "New JTBD Bundle"
        assert dialog.name.text() == "New Flowforge Project"
        assert dialog.package.text() == "new_flowforge_project"
        assert dialog.domain.text() == "case"
        assert dialog.job_title.text() == "Intake case"

    importlib.reload(app_module)
