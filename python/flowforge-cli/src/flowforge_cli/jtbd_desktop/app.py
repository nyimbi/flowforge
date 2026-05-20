"""PyQt desktop editor for JTBD bundle authoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from .document import (
	JtbdDocument,
	build_ai_authoring_prompt,
	build_template_from_jtbd,
	create_default_bundle,
	create_default_jtbd,
	create_template_library,
	load_template_library,
	normalise_id,
	requires_pii,
	save_template_library,
	verify_generation,
)
from .._io import safe_output_path
from ..jtbd import generate
from ..jtbd.parse import JTBDParseError

try:  # pragma: no cover - exercised manually / in GUI smoke environments.
	from PyQt6.QtCore import Qt  # type: ignore[import-not-found]
	from PyQt6.QtGui import QAction, QBrush, QColor, QPalette, QPen  # type: ignore[import-not-found]
	from PyQt6.QtWidgets import (  # type: ignore[import-not-found]
		QAbstractItemView,
		QApplication,
		QCheckBox,
		QComboBox,
		QDialog,
		QDialogButtonBox,
		QFileDialog,
		QFormLayout,
		QFrame,
		QGraphicsScene,
		QGraphicsView,
		QGridLayout,
		QGroupBox,
		QHBoxLayout,
		QHeaderView,
		QInputDialog,
		QLabel,
		QLineEdit,
		QListWidget,
		QListWidgetItem,
		QMainWindow,
		QMessageBox,
		QPlainTextEdit,
		QPushButton,
		QScrollArea,
		QSplitter,
		QStatusBar,
		QTabWidget,
		QTableWidget,
		QTableWidgetItem,
		QTextEdit,
		QVBoxLayout,
		QWidget,
	)
except ModuleNotFoundError:  # pragma: no cover - command reports actionable message.
	Qt = cast(Any, None)
	QDialog = cast(Any, object)
	QMainWindow = cast(Any, object)


FIELD_KINDS = [
	"text",
	"number",
	"money",
	"date",
	"datetime",
	"enum",
	"boolean",
	"party_ref",
	"document_ref",
	"email",
	"phone",
	"address",
	"textarea",
	"signature",
	"file",
]
STATUSES = ["draft", "in_review", "published", "deprecated", "archived"]
TENANCY = ["none", "single", "multi"]
RENDERERS = ["real", "skeleton"]
EDGE_HANDLES = ["branch", "reject", "escalate", "compensate", "loop"]
APPROVAL_POLICIES = ["1_of_1", "2_of_2", "n_of_m", "authority_tier"]
NOTIFICATION_TRIGGERS = [
	"state_enter",
	"state_exit",
	"sla_warn",
	"sla_breach",
	"approved",
	"rejected",
	"escalated",
]
NOTIFICATION_CHANNELS = ["email", "sms", "slack", "webhook", "in_app"]
COMPLIANCE_REGIMES = [
	"GDPR",
	"SOX",
	"HIPAA",
	"PCI-DSS",
	"ISO27001",
	"SOC2",
	"NIST-800-53",
	"CCPA",
]
DATA_SENSITIVITY = ["PII", "PHI", "PCI", "secrets", "regulated"]


class NewBundleDialog(QDialog):  # type: ignore[misc]
	"""Small first-run dialog for creating a new bundle."""

	def __init__(self, parent: QWidget | None = None) -> None:
		super().__init__(parent)
		self.setWindowTitle("New JTBD Bundle")
		self.name = QLineEdit("New Flowforge Project")
		self.package = QLineEdit("new_flowforge_project")
		self.domain = QLineEdit("case")
		self.job_title = QLineEdit("Intake case")

		form = QFormLayout()
		form.addRow("Project name", self.name)
		form.addRow("Package", self.package)
		form.addRow("Domain", self.domain)
		form.addRow("First job", self.job_title)

		buttons = QDialogButtonBox(
			QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
		)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)

		layout = QVBoxLayout(self)
		layout.addLayout(form)
		layout.addWidget(buttons)

	def bundle(self) -> dict[str, Any]:
		bundle = create_default_bundle(
			self.name.text().strip() or "New Flowforge Project",
			self.package.text().strip() or "new_flowforge_project",
			self.domain.text().strip() or "case",
		)
		title = self.job_title.text().strip() or "Intake case"
		bundle["jtbds"][0] = create_default_jtbd(
			normalise_id(title, fallback="job"),
			title,
		)
		return bundle


class JtbdEditorWindow(QMainWindow):  # type: ignore[misc]
	"""Main JTBD editor window."""

	def __init__(
		self,
		document: JtbdDocument,
		theme: dict[str, Any] | None = None,
	) -> None:
		super().__init__()
		self.document = document
		self.current_index = 0
		self._loading = False
		self.template_library = create_template_library()
		self.theme = _load_theme(theme)
		self.setWindowTitle("Flowforge JTBD Editor")
		self.resize(1360, 860)
		self.setMinimumSize(1100, 720)
		self._build_ui()
		self._apply_theme()
		self._refresh_all()

	def _build_ui(self) -> None:
		self._build_actions()
		self.setStatusBar(QStatusBar(self))

		root = QSplitter(Qt.Orientation.Horizontal)
		root.setChildrenCollapsible(False)
		self.setCentralWidget(root)

		left = QFrame()
		left.setObjectName("sidebar")
		left_layout = QVBoxLayout(left)
		left_layout.setContentsMargins(16, 16, 16, 16)
		left_layout.setSpacing(12)
		title = QLabel("JTBD Map")
		title.setObjectName("sidebarTitle")
		self.job_list = QListWidget()
		self.job_list.currentRowChanged.connect(self._on_select_job)
		self.add_job_button = QPushButton("Add Job")
		self.add_job_button.clicked.connect(self._add_job)
		self.duplicate_job_button = QPushButton("Duplicate")
		self.duplicate_job_button.clicked.connect(self._duplicate_job)
		self.delete_job_button = QPushButton("Delete")
		self.delete_job_button.clicked.connect(self._delete_job)
		left_layout.addWidget(title)
		left_layout.addWidget(self.job_list, 1)
		left_layout.addWidget(self.add_job_button)
		left_layout.addWidget(self.duplicate_job_button)
		left_layout.addWidget(self.delete_job_button)
		root.addWidget(left)

		editor_scroll = QScrollArea()
		editor_scroll.setWidgetResizable(True)
		editor_host = QWidget()
		self.editor_layout = QVBoxLayout(editor_host)
		self.editor_layout.setContentsMargins(18, 18, 18, 18)
		self.editor_layout.setSpacing(14)
		editor_scroll.setWidget(editor_host)
		root.addWidget(editor_scroll)

		right = QFrame()
		right.setObjectName("rightPanel")
		right_layout = QVBoxLayout(right)
		right_layout.setContentsMargins(14, 14, 14, 14)
		right_layout.setSpacing(12)
		self.validation_box = QTextEdit()
		self.validation_box.setReadOnly(True)
		self.validation_box.setMinimumHeight(170)
		self.json_preview = QPlainTextEdit()
		self.json_preview.setReadOnly(True)
		self.json_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
		right_layout.addWidget(QLabel("Validation"))
		right_layout.addWidget(self.validation_box)
		right_layout.addWidget(QLabel("Bundle JSON"))
		right_layout.addWidget(self.json_preview, 1)
		root.addWidget(right)
		root.setSizes([250, 730, 380])

		self._build_project_panel()
		self._build_shared_panel()
		self._build_job_panel()
		self._build_tabs()

	def _build_actions(self) -> None:
		toolbar = self.addToolBar("Main")
		toolbar.setMovable(False)
		file_menu = self.menuBar().addMenu("File")
		job_menu = self.menuBar().addMenu("Job")
		tools_menu = self.menuBar().addMenu("Tools")

		for text, slot, shortcut in [
			("New", self._new_bundle, "Ctrl+N"),
			("Open", self._open_bundle, "Ctrl+O"),
			("Save", self._save, "Ctrl+S"),
			("Save As", self._save_as, "Ctrl+Shift+S"),
		]:
			action = QAction(text, self)
			action.triggered.connect(slot)
			action.setShortcut(shortcut)
			file_menu.addAction(action)
			toolbar.addAction(action)

		for text, slot in [
			("Add Job", self._add_job),
			("Duplicate Job", self._duplicate_job),
			("Delete Job", self._delete_job),
		]:
			action = QAction(text, self)
			action.triggered.connect(slot)
			job_menu.addAction(action)

		validate = QAction("Validate", self)
		validate.triggered.connect(self._validate_now)
		validate.setShortcut("Ctrl+R")
		tools_menu.addAction(validate)
		toolbar.addAction(validate)

		verify = QAction("Verify Generation", self)
		verify.triggered.connect(self._verify_generation)
		tools_menu.addAction(verify)
		toolbar.addAction(verify)

		generate_action = QAction("Generate App", self)
		generate_action.triggered.connect(self._generate_app)
		generate_action.setShortcut("Ctrl+G")
		tools_menu.addAction(generate_action)
		toolbar.addAction(generate_action)

	def _build_project_panel(self) -> None:
		box = QGroupBox("Project")
		grid = QGridLayout(box)
		self.project_name = QLineEdit()
		self.project_package = QLineEdit()
		self.project_domain = QLineEdit()
		self.project_tenancy = _combo(TENANCY)
		self.project_renderer = _combo(RENDERERS)
		self.project_languages = QLineEdit()
		self.project_currencies = QLineEdit()
		self.project_compliance = QLineEdit()
		self.project_sensitivity = QLineEdit()
		self.project_compliance.setPlaceholderText(", ".join(COMPLIANCE_REGIMES))
		self.project_sensitivity.setPlaceholderText(", ".join(DATA_SENSITIVITY))
		self.design_primary = QLineEdit()
		self.design_accent = QLineEdit()
		self.design_font = QLineEdit()
		self.design_density = _combo(["comfortable", "compact"])
		self.design_radius = QLineEdit()
		for widget in [
			self.project_name,
			self.project_package,
			self.project_domain,
			self.project_tenancy,
			self.project_renderer,
			self.project_languages,
			self.project_currencies,
			self.project_compliance,
			self.project_sensitivity,
			self.design_primary,
			self.design_accent,
			self.design_font,
			self.design_density,
			self.design_radius,
		]:
			_connect_change(widget, self._mark_dirty_from_widgets)
		rows = [
			("Name", self.project_name),
			("Package", self.project_package),
			("Domain", self.project_domain),
			("Tenancy", self.project_tenancy),
			("Form renderer", self.project_renderer),
			("Languages", self.project_languages),
			("Currencies", self.project_currencies),
			("Compliance", self.project_compliance),
			("Sensitivity", self.project_sensitivity),
			("Primary", self.design_primary),
			("Accent", self.design_accent),
			("Font", self.design_font),
			("Density", self.design_density),
			("Radius", self.design_radius),
		]
		for i, (label, widget) in enumerate(rows):
			grid.addWidget(QLabel(label), i // 2, (i % 2) * 2)
			grid.addWidget(widget, i // 2, (i % 2) * 2 + 1)
		self.editor_layout.addWidget(box)

	def _build_shared_panel(self) -> None:
		box = QGroupBox("Shared")
		form = QFormLayout(box)
		self.shared_roles = QLineEdit()
		self.shared_permissions = QLineEdit()
		self.shared_entities = QTableWidget(0, 2)
		self.shared_entities.setHorizontalHeaderLabels(["Name", "ID field"])
		self.shared_entities.setAlternatingRowColors(True)
		self.shared_entities.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
		self.shared_entities.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
		self.shared_entities.verticalHeader().setVisible(False)
		self.shared_entities.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
		for widget in [self.shared_roles, self.shared_permissions]:
			_connect_change(widget, self._mark_dirty_from_widgets)
		self.shared_entities.itemChanged.connect(self._mark_dirty_from_widgets)
		form.addRow("Roles", self.shared_roles)
		form.addRow("Permissions", self.shared_permissions)
		form.addRow("Entities", _table_panel(self.shared_entities, self._mark_dirty_from_widgets))
		self.editor_layout.addWidget(box)

	def _build_job_panel(self) -> None:
		box = QGroupBox("Job")
		form = QFormLayout(box)
		self.job_id = QLineEdit()
		self.job_title = QLineEdit()
		self.job_version = QLineEdit()
		self.job_status = _combo(STATUSES)
		self.actor_role = QLineEdit()
		self.actor_department = QLineEdit()
		self.actor_external = QCheckBox("External actor")
		self.sla_warn = QLineEdit()
		self.sla_breach = QLineEdit()
		self.job_compliance = QLineEdit()
		self.job_sensitivity = QLineEdit()
		self.job_compliance.setPlaceholderText(", ".join(COMPLIANCE_REGIMES))
		self.job_sensitivity.setPlaceholderText(", ".join(DATA_SENSITIVITY))
		self.situation = QPlainTextEdit()
		self.motivation = QPlainTextEdit()
		self.outcome = QPlainTextEdit()
		for edit in [self.situation, self.motivation, self.outcome]:
			edit.setMinimumHeight(72)
		for widget in [
			self.job_id,
			self.job_title,
			self.job_version,
			self.job_status,
			self.actor_role,
			self.actor_department,
			self.actor_external,
			self.sla_warn,
			self.sla_breach,
			self.job_compliance,
			self.job_sensitivity,
			self.situation,
			self.motivation,
			self.outcome,
		]:
			_connect_change(widget, self._mark_dirty_from_widgets)
		form.addRow("ID", self.job_id)
		form.addRow("Title", self.job_title)
		form.addRow("Version", self.job_version)
		form.addRow("Status", self.job_status)
		form.addRow("Actor role", self.actor_role)
		form.addRow("Actor department", self.actor_department)
		form.addRow("", self.actor_external)
		form.addRow("SLA warn %", self.sla_warn)
		form.addRow("SLA breach seconds", self.sla_breach)
		form.addRow("Compliance", self.job_compliance)
		form.addRow("Sensitivity", self.job_sensitivity)
		form.addRow("Situation", self.situation)
		form.addRow("Motivation", self.motivation)
		form.addRow("Outcome", self.outcome)
		self.editor_layout.addWidget(box)

	def _build_tabs(self) -> None:
		self.tabs = QTabWidget()
		self.success_table = _table(["Success criterion"], stretch_last=True)
		self.fields_table = _table(["ID", "Kind", "Label", "Required", "PII", "Sensitivity"], stretch_last=True)
		self.edges_table = _table(["ID", "Condition", "Handle", "Branch to"], stretch_last=True)
		self.docs_table = _table(["Kind", "Min", "Max", "Freshness days", "AV required"], stretch_last=True)
		self.approvals_table = _table(["Role", "Policy", "N", "Tier"], stretch_last=True)
		self.notifications_table = _table(["Trigger", "Channel", "Audience"], stretch_last=True)
		self.metrics_table = _table(["Metric"], stretch_last=True)
		self.requires_table = _table(["Requires JTBD ID"], stretch_last=True)
		for table in [
			self.success_table,
			self.fields_table,
			self.edges_table,
			self.docs_table,
			self.approvals_table,
			self.notifications_table,
			self.metrics_table,
			self.requires_table,
		]:
			table.itemChanged.connect(self._mark_dirty_from_widgets)
		self.tabs.addTab(_table_panel(self.success_table, self._mark_dirty_from_widgets), "Criteria")
		self.tabs.addTab(_table_panel(self.fields_table, self._mark_dirty_from_widgets), "Fields")
		self.tabs.addTab(_table_panel(self.edges_table, self._mark_dirty_from_widgets), "Edge Cases")
		self.tabs.addTab(_table_panel(self.docs_table, self._mark_dirty_from_widgets), "Documents")
		self.tabs.addTab(_table_panel(self.approvals_table, self._mark_dirty_from_widgets), "Approvals")
		self.tabs.addTab(_table_panel(self.notifications_table, self._mark_dirty_from_widgets), "Notifications")
		self.tabs.addTab(_table_panel(self.metrics_table, self._mark_dirty_from_widgets), "Metrics")
		self.tabs.addTab(_table_panel(self.requires_table, self._mark_dirty_from_widgets), "Dependencies")
		self._build_visual_tab()
		self._build_annotations_tab()
		self._build_ai_tab()
		self._build_templates_tab()
		self.editor_layout.addWidget(self.tabs)

	def _build_visual_tab(self) -> None:
		host = QWidget()
		layout = QVBoxLayout(host)
		self.visual_scene = QGraphicsScene(self)
		self.visual_view = QGraphicsView(self.visual_scene)
		self.visual_view.setMinimumHeight(360)
		self.visual_view.setObjectName("visualMap")
		self.visual_view.setToolTip("Select a source and dependency to compose JTBD dependencies.")
		controls = QHBoxLayout()
		self.visual_dependency_source = QComboBox()
		self.visual_dependency_target = QComboBox()
		add_dependency = QPushButton("Add Dependency")
		remove_dependency = QPushButton("Remove Dependency")
		add_dependency.clicked.connect(self._add_visual_dependency)
		remove_dependency.clicked.connect(self._remove_visual_dependency)
		controls.addWidget(QLabel("Job"))
		controls.addWidget(self.visual_dependency_source)
		controls.addWidget(QLabel("requires"))
		controls.addWidget(self.visual_dependency_target)
		controls.addWidget(add_dependency)
		controls.addWidget(remove_dependency)
		controls.addStretch(1)
		layout.addWidget(self.visual_view, 1)
		layout.addLayout(controls)
		self.tabs.addTab(host, "Visual Map")

	def _build_annotations_tab(self) -> None:
		host = QWidget()
		layout = QFormLayout(host)
		self.project_notes = QPlainTextEdit()
		self.project_tags = QLineEdit()
		self.job_notes = QPlainTextEdit()
		self.job_tags = QLineEdit()
		for edit in [self.project_notes, self.job_notes]:
			edit.setMinimumHeight(80)
		for widget in [self.project_notes, self.project_tags, self.job_notes, self.job_tags]:
			_connect_change(widget, self._mark_dirty_from_widgets)
		layout.addRow("Project notes", self.project_notes)
		layout.addRow("Project tags", self.project_tags)
		layout.addRow("JTBD notes", self.job_notes)
		layout.addRow("JTBD tags", self.job_tags)
		self.tabs.addTab(host, "Annotations")

	def _build_ai_tab(self) -> None:
		host = QWidget()
		layout = QVBoxLayout(host)
		self.ai_prompt = QPlainTextEdit()
		self.ai_prompt.setPlaceholderText("Describe the job to be done, constraints, actor, data to collect, and success criteria.")
		self.ai_prompt.setMinimumHeight(110)
		self.ai_output = QPlainTextEdit()
		self.ai_output.setReadOnly(True)
		buttons = QHBoxLayout()
		draft = QPushButton("Draft JTBD")
		draft.clicked.connect(self._draft_jtbd_with_ai)
		copy_prompt = QPushButton("Copy Review Prompt")
		copy_prompt.clicked.connect(self._copy_ai_review_prompt)
		polish_hint = QPushButton("Prepare Copy Polish")
		polish_hint.clicked.connect(self._prepare_copy_polish)
		buttons.addWidget(draft)
		buttons.addWidget(copy_prompt)
		buttons.addWidget(polish_hint)
		buttons.addStretch(1)
		layout.addWidget(self.ai_prompt)
		layout.addLayout(buttons)
		layout.addWidget(self.ai_output, 1)
		self.tabs.addTab(host, "AI Assist")

	def _build_templates_tab(self) -> None:
		host = QWidget()
		layout = QVBoxLayout(host)
		self.template_list = QListWidget()
		buttons = QHBoxLayout()
		add = QPushButton("Add From Template")
		add.clicked.connect(self._add_from_template)
		capture = QPushButton("Save JTBD As Template")
		capture.clicked.connect(self._capture_template)
		load = QPushButton("Load Templates")
		load.clicked.connect(self._load_templates)
		save = QPushButton("Save Templates")
		save.clicked.connect(self._save_templates)
		for button in [add, capture, load, save]:
			buttons.addWidget(button)
		buttons.addStretch(1)
		layout.addWidget(self.template_list)
		layout.addLayout(buttons)
		self.tabs.addTab(host, "Templates")

	def _apply_theme(self) -> None:
		app = QApplication.instance()
		if app is not None:
			palette = QPalette()
			palette.setColor(QPalette.ColorRole.Window, QColor(self.theme["background"]))
			palette.setColor(QPalette.ColorRole.WindowText, QColor(self.theme["text"]))
			palette.setColor(QPalette.ColorRole.Base, QColor(self.theme["surface"]))
			palette.setColor(QPalette.ColorRole.Text, QColor(self.theme["text"]))
			palette.setColor(QPalette.ColorRole.Button, QColor(self.theme["surface"]))
			palette.setColor(QPalette.ColorRole.ButtonText, QColor(self.theme["text"]))
			app.setPalette(palette)
		self.setStyleSheet(_stylesheet(self.theme))

	def _refresh_all(self) -> None:
		self._loading = True
		project = self.document.bundle.get("project", {})
		design = project.get("design") or {}
		frontend = project.get("frontend") or {}
		self.project_name.setText(str(project.get("name", "")))
		self.project_package.setText(str(project.get("package", "")))
		self.project_domain.setText(str(project.get("domain", "")))
		self.project_tenancy.setCurrentText(str(project.get("tenancy", "single")))
		self.project_renderer.setCurrentText(str(frontend.get("form_renderer", "real")))
		self.project_languages.setText(", ".join(project.get("languages", []) or []))
		self.project_currencies.setText(", ".join(project.get("currencies", []) or []))
		self.project_compliance.setText(", ".join(project.get("compliance", []) or []))
		self.project_sensitivity.setText(", ".join(project.get("data_sensitivity", []) or []))
		self.design_primary.setText(str(design.get("primary", "#2563eb")))
		self.design_accent.setText(str(design.get("accent", "#10b981")))
		self.design_font.setText(str(design.get("font_family", "Inter, system-ui, sans-serif")))
		self.design_density.setCurrentText(str(design.get("density", "comfortable")))
		self.design_radius.setText(str(design.get("radius_scale", 1.0)))
		project_annotations = project.get("annotations") or {}
		self.project_notes.setPlainText(str(project_annotations.get("notes") or ""))
		self.project_tags.setText(", ".join(project_annotations.get("tags", []) or []))
		shared = self.document.bundle.get("shared", {})
		self.shared_roles.setText(", ".join(shared.get("roles", []) or []))
		self.shared_permissions.setText(", ".join(shared.get("permissions", []) or []))
		_set_entity_rows(self.shared_entities, shared.get("entities", []) or [])

		self.job_list.clear()
		for i, jtbd in enumerate(self.document.bundle.get("jtbds", [])):
			item = QListWidgetItem(str(jtbd.get("title") or jtbd.get("id") or f"Job {i + 1}"))
			item.setData(Qt.ItemDataRole.UserRole, i)
			self.job_list.addItem(item)
		self.current_index = max(0, min(self.current_index, self.job_list.count() - 1))
		self.job_list.setCurrentRow(self.current_index)
		self._load_job_form(self.current_index)
		self._loading = False
		self._refresh_template_list()
		self._refresh_visual_map()
		self._refresh_preview_and_validation()
		self._refresh_title()

	def _load_job_form(self, index: int) -> None:
		if not self.document.bundle.get("jtbds"):
			return
		jtbd = self.document.get_jtbd(index)
		actor = jtbd.get("actor") or {}
		sla = jtbd.get("sla") or {}
		self.job_id.setText(str(jtbd.get("id", "")))
		self.job_title.setText(str(jtbd.get("title", "")))
		self.job_version.setText(str(jtbd.get("version", "1.0.0")))
		self.job_status.setCurrentText(str(jtbd.get("status", "draft")))
		self.actor_role.setText(str(actor.get("role", "")))
		self.actor_department.setText(str(actor.get("department") or ""))
		self.actor_external.setChecked(bool(actor.get("external", False)))
		self.sla_warn.setText(str(sla.get("warn_pct") or ""))
		self.sla_breach.setText(str(sla.get("breach_seconds") or ""))
		self.job_compliance.setText(", ".join(jtbd.get("compliance", []) or []))
		self.job_sensitivity.setText(", ".join(jtbd.get("data_sensitivity", []) or []))
		job_annotations = jtbd.get("annotations") or {}
		self.job_notes.setPlainText(str(job_annotations.get("notes") or ""))
		self.job_tags.setText(", ".join(job_annotations.get("tags", []) or []))
		self.situation.setPlainText(str(jtbd.get("situation", "")))
		self.motivation.setPlainText(str(jtbd.get("motivation", "")))
		self.outcome.setPlainText(str(jtbd.get("outcome", "")))
		_set_string_rows(self.success_table, jtbd.get("success_criteria", []))
		_set_field_rows(self.fields_table, jtbd.get("data_capture", []))
		_set_edge_rows(self.edges_table, jtbd.get("edge_cases", []))
		_set_doc_rows(self.docs_table, jtbd.get("documents_required", []))
		_set_approval_rows(self.approvals_table, jtbd.get("approvals", []))
		_set_notification_rows(self.notifications_table, jtbd.get("notifications", []))
		_set_string_rows(self.metrics_table, jtbd.get("metrics", []))
		_set_string_rows(self.requires_table, jtbd.get("requires", []))
		self.statusBar().showMessage(
			f"SLA warn {sla.get('warn_pct', '-')}%, breach {sla.get('breach_seconds', '-')}s",
			4000,
		)

	def _commit_forms(self) -> None:
		if self._loading:
			return
		project = self.document.bundle.setdefault("project", {})
		project["name"] = self.project_name.text().strip()
		project["package"] = self.project_package.text().strip()
		project["domain"] = self.project_domain.text().strip()
		project["tenancy"] = self.project_tenancy.currentText()
		project["languages"] = _csv(self.project_languages.text())
		project["currencies"] = _csv(self.project_currencies.text())
		project["compliance"] = _csv_enum(self.project_compliance.text(), COMPLIANCE_REGIMES)
		project["data_sensitivity"] = _csv_enum(self.project_sensitivity.text(), DATA_SENSITIVITY)
		project["annotations"] = {
			"notes": self.project_notes.toPlainText().strip(),
			"tags": _csv(self.project_tags.text()),
		}
		project.setdefault("frontend", {})["form_renderer"] = self.project_renderer.currentText()
		shared = self.document.bundle.setdefault("shared", {})
		shared["roles"] = _csv(self.shared_roles.text())
		shared["permissions"] = _csv(self.shared_permissions.text())
		shared["entities"] = _entity_rows(self.shared_entities)
		design = project.setdefault("design", {})
		design["primary"] = self.design_primary.text().strip()
		design["accent"] = self.design_accent.text().strip()
		design["font_family"] = self.design_font.text().strip()
		design["density"] = self.design_density.currentText()
		try:
			design["radius_scale"] = float(self.design_radius.text().strip())
		except ValueError:
			design["radius_scale"] = self.design_radius.text().strip()

		jtbd = self.document.get_jtbd(self.current_index)
		new_job_id = self.job_id.text().strip()
		if new_job_id != str(jtbd.get("id") or ""):
			try:
				self.document.rename_jtbd(self.current_index, new_job_id)
			except ValueError:
				# Keep typing responsive for temporarily invalid ids; validation
				# surfaces the authoring problem without crashing the GUI.
				jtbd["id"] = new_job_id
				jtbd.pop("spec_hash", None)
				self.document.dirty = True
			jtbd = self.document.get_jtbd(self.current_index)
		jtbd["title"] = self.job_title.text().strip()
		jtbd["version"] = self.job_version.text().strip() or "1.0.0"
		jtbd["status"] = self.job_status.currentText()
		jtbd["actor"] = {
			"role": self.actor_role.text().strip(),
			"external": self.actor_external.isChecked(),
		}
		if self.actor_department.text().strip():
			jtbd["actor"]["department"] = self.actor_department.text().strip()
		jtbd["situation"] = self.situation.toPlainText().strip()
		jtbd["motivation"] = self.motivation.toPlainText().strip()
		jtbd["outcome"] = self.outcome.toPlainText().strip()
		sla: dict[str, int] = {}
		if self.sla_warn.text().strip():
			sla["warn_pct"] = _int(self.sla_warn.text(), 80)
		if self.sla_breach.text().strip():
			sla["breach_seconds"] = _int(self.sla_breach.text(), 86400)
		jtbd["sla"] = sla or None
		jtbd["compliance"] = _csv_enum(self.job_compliance.text(), COMPLIANCE_REGIMES)
		jtbd["data_sensitivity"] = _csv_enum(self.job_sensitivity.text(), DATA_SENSITIVITY)
		annotations = dict(jtbd.get("annotations") or {})
		annotations["notes"] = self.job_notes.toPlainText().strip()
		annotations["tags"] = _csv(self.job_tags.text())
		jtbd["annotations"] = annotations
		jtbd["success_criteria"] = _string_rows(self.success_table)
		jtbd["data_capture"] = _field_rows(self.fields_table)
		jtbd["edge_cases"] = _edge_rows(self.edges_table)
		jtbd["documents_required"] = _doc_rows(self.docs_table)
		jtbd["approvals"] = _approval_rows(self.approvals_table)
		jtbd["notifications"] = _notification_rows(self.notifications_table)
		jtbd["metrics"] = _string_rows(self.metrics_table)
		jtbd["requires"] = _string_rows(self.requires_table)
		jtbd.pop("spec_hash", None)

	def _mark_dirty_from_widgets(self, *_: Any) -> None:
		if self._loading:
			return
		self.document.dirty = True
		self._commit_forms()
		self._refresh_preview_and_validation()
		self._refresh_job_list_labels()
		self._refresh_visual_map()
		self._refresh_title()

	def _refresh_preview_and_validation(self) -> None:
		self.json_preview.setPlainText(
			json.dumps(self.document.bundle, indent=2, sort_keys=True) + "\n"
		)
		result = self.document.validate()
		lines: list[str] = []
		if result.ok:
			if result.warnings:
				lines.append("Ready for generation. Review advisory findings below.")
			else:
				lines.append("Ready for generation.")
		for err in result.errors:
			lines.append(f"ERROR: {err}")
		for warn in result.warnings:
			lines.append(f"WARN: {warn}")
		for info in result.infos:
			lines.append(f"INFO: {info}")
		self.validation_box.setPlainText("\n".join(lines))

	def _refresh_title(self) -> None:
		name = self.document.path.name if self.document.path else "Untitled"
		dirty = " *" if self.document.dirty else ""
		self.setWindowTitle(f"Flowforge JTBD Editor - {name}{dirty}")

	def _refresh_job_list_labels(self) -> None:
		for i, jtbd in enumerate(self.document.bundle.get("jtbds", [])):
			item = self.job_list.item(i)
			if item:
				item.setText(str(jtbd.get("title") or jtbd.get("id") or f"Job {i + 1}"))

	def _on_select_job(self, row: int) -> None:
		if self._loading or row < 0:
			return
		self._commit_forms()
		self.current_index = row
		self._loading = True
		self._load_job_form(row)
		self._loading = False
		self._refresh_visual_map()
		self._refresh_preview_and_validation()

	def _new_bundle(self) -> None:
		if not self._confirm_discard():
			return
		dialog = NewBundleDialog(self)
		if dialog.exec() != QDialog.DialogCode.Accepted:
			return
		self.document = JtbdDocument(dialog.bundle())
		self.current_index = 0
		self._refresh_all()

	def _open_bundle(self) -> None:
		if not self._confirm_discard():
			return
		file_name, _ = QFileDialog.getOpenFileName(
			self,
			"Open JTBD bundle",
			"",
			"JTBD bundles (*.json *.yaml *.yml);;All files (*)",
		)
		if not file_name:
			return
		try:
			self.document = JtbdDocument.load(Path(file_name))
		except Exception as exc:
			QMessageBox.critical(self, "Open failed", str(exc))
			return
		self.current_index = 0
		self._refresh_all()

	def _save(self) -> None:
		self._commit_forms()
		if self.document.path is None:
			self._save_as()
			return
		try:
			self.document.save()
		except Exception as exc:
			QMessageBox.critical(self, "Save failed", str(exc))
			return
		self._refresh_title()
		self.statusBar().showMessage("Saved", 3000)

	def _save_as(self) -> None:
		self._commit_forms()
		file_name, _ = QFileDialog.getSaveFileName(
			self,
			"Save JTBD bundle",
			str(self.document.path or Path("jtbd-bundle.json")),
			"JTBD bundle (*.json)",
		)
		if not file_name:
			return
		try:
			self.document.save(Path(file_name))
		except Exception as exc:
			QMessageBox.critical(self, "Save failed", str(exc))
			return
		self._refresh_title()
		self.statusBar().showMessage("Saved", 3000)

	def _validate_now(self) -> None:
		self._commit_forms()
		result = self.document.validate()
		self._refresh_preview_and_validation()
		if result.ok:
			QMessageBox.information(self, "Validation", "Bundle is valid.")
		else:
			QMessageBox.warning(self, "Validation", "Bundle has errors. See the validation panel.")

	def _verify_generation(self) -> None:
		self._commit_forms()
		result = verify_generation(self.document.bundle)
		self._append_validation_result("Generation verification", result)
		if result.ok:
			QMessageBox.information(self, "Verify Generation", "\n".join(result.infos) or "Generation verified.")
		else:
			QMessageBox.warning(self, "Verify Generation", "Generation verification failed. See the validation panel.")

	def _generate_app(self) -> None:
		self._commit_forms()
		result = self.document.validate()
		if not result.ok:
			QMessageBox.warning(self, "Generate App", "Fix validation errors before generating.")
			return
		target = QFileDialog.getExistingDirectory(self, "Generate Flowforge app into directory")
		if not target:
			return
		out = Path(target)
		if out.exists() and any(out.iterdir()):
			answer = QMessageBox.question(
				self,
				"Generate App",
				f"{out} is not empty. Write generated files into it?",
				QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			)
			if answer != QMessageBox.StandardButton.Yes:
				return
		try:
			files = generate(self.document.bundle)
			for file in files:
				dst = safe_output_path(out, file.path)
				dst.parent.mkdir(parents=True, exist_ok=True)
				dst.write_text(file.content, encoding="utf-8")
		except (JTBDParseError, OSError, ValueError) as exc:
			QMessageBox.critical(self, "Generate App failed", str(exc))
			return
		QMessageBox.information(self, "Generate App", f"Wrote {len(files)} files to {out}.")

	def _add_job(self) -> None:
		title, ok = QInputDialog.getText(self, "Add Job", "Job title")
		if not ok or not title.strip():
			return
		self._commit_forms()
		self.current_index = self.document.add_jtbd(title.strip())
		self._refresh_all()

	def _draft_jtbd_with_ai(self) -> None:
		prompt = self.ai_prompt.toPlainText().strip()
		if not prompt:
			QMessageBox.warning(self, "AI Assist", "Enter a JTBD prompt first.")
			return
		self._commit_forms()
		try:
			self.current_index = self.document.add_jtbd_from_prompt(prompt)
		except ValueError as exc:
			QMessageBox.warning(self, "AI Assist", str(exc))
			return
		self.ai_output.setPlainText(
			json.dumps(self.document.get_jtbd(self.current_index), indent=2, sort_keys=True)
		)
		self._refresh_all()

	def _copy_ai_review_prompt(self) -> None:
		self._commit_forms()
		prompt = build_ai_authoring_prompt(
			self.document.bundle,
			self.document.get_jtbd(self.current_index),
		)
		QApplication.clipboard().setText(prompt)
		self.ai_output.setPlainText(prompt)
		self.statusBar().showMessage("AI review prompt copied", 3000)

	def _prepare_copy_polish(self) -> None:
		if self.document.path is None:
			self.ai_output.setPlainText("Save the bundle first, then run: flowforge polish-copy --bundle <saved-bundle> --dry-run")
			return
		self.ai_output.setPlainText(
			f"flowforge polish-copy --bundle {self.document.path} --dry-run\n"
			f"flowforge polish-copy --bundle {self.document.path} --commit"
		)

	def _add_from_template(self) -> None:
		row = self.template_list.currentRow()
		templates = self.template_library.get("templates", [])
		if row < 0 or row >= len(templates):
			QMessageBox.warning(self, "Templates", "Select a template first.")
			return
		self._commit_forms()
		self.current_index = self.document.add_jtbd_from_template(templates[row])
		self._refresh_all()

	def _capture_template(self) -> None:
		self._commit_forms()
		entry = build_template_from_jtbd(self.document.get_jtbd(self.current_index))
		existing = {str(t.get("id")) for t in self.template_library.get("templates", [])}
		entry["id"] = _unique_template_id(str(entry["id"]), existing)
		self.template_library.setdefault("templates", []).append(entry)
		self._refresh_template_list()
		self.statusBar().showMessage("Template captured", 3000)

	def _load_templates(self) -> None:
		file_name, _ = QFileDialog.getOpenFileName(
			self,
			"Load JTBD templates",
			"",
			"JTBD template library (*.json);;All files (*)",
		)
		if not file_name:
			return
		try:
			self.template_library = load_template_library(Path(file_name))
		except Exception as exc:
			QMessageBox.critical(self, "Load templates failed", str(exc))
			return
		self._refresh_template_list()

	def _save_templates(self) -> None:
		file_name, _ = QFileDialog.getSaveFileName(
			self,
			"Save JTBD templates",
			"jtbd-templates.json",
			"JTBD template library (*.json)",
		)
		if not file_name:
			return
		try:
			save_template_library(Path(file_name), self.template_library)
		except Exception as exc:
			QMessageBox.critical(self, "Save templates failed", str(exc))
			return
		self.statusBar().showMessage("Templates saved", 3000)

	def _duplicate_job(self) -> None:
		self._commit_forms()
		self.current_index = self.document.duplicate_jtbd(self.current_index)
		self._refresh_all()

	def _delete_job(self) -> None:
		if QMessageBox.question(
			self,
			"Delete Job",
			"Delete the selected JTBD?",
		) != QMessageBox.StandardButton.Yes:
			return
		try:
			self.document.remove_jtbd(self.current_index)
		except Exception as exc:
			QMessageBox.warning(self, "Cannot delete", str(exc))
			return
		self.current_index = max(0, self.current_index - 1)
		self._refresh_all()

	def _add_visual_dependency(self) -> None:
		self._commit_forms()
		source = self.visual_dependency_source.currentData()
		target = self.visual_dependency_target.currentData()
		if not isinstance(source, int) or not isinstance(target, str):
			return
		try:
			self.document.add_dependency(source, target)
		except ValueError as exc:
			QMessageBox.warning(self, "Visual Composition", str(exc))
			return
		self.current_index = source
		self._refresh_all()

	def _remove_visual_dependency(self) -> None:
		self._commit_forms()
		source = self.visual_dependency_source.currentData()
		target = self.visual_dependency_target.currentData()
		if not isinstance(source, int) or not isinstance(target, str):
			return
		self.document.remove_dependency(source, target)
		self.current_index = source
		self._refresh_all()

	def _confirm_discard(self) -> bool:
		if not self.document.dirty:
			return True
		answer = QMessageBox.question(
			self,
			"Unsaved changes",
			"Discard unsaved changes?",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
		)
		return answer == QMessageBox.StandardButton.Yes

	def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API.
		if self._confirm_discard():
			event.accept()
		else:
			event.ignore()

	def _append_validation_result(self, heading: str, result: Any) -> None:
		lines = [heading]
		for err in result.errors:
			lines.append(f"ERROR: {err}")
		for warn in result.warnings:
			lines.append(f"WARN: {warn}")
		for info in result.infos:
			lines.append(f"INFO: {info}")
		self.validation_box.setPlainText("\n".join(lines))

	def _refresh_template_list(self) -> None:
		self.template_list.clear()
		for template in self.template_library.get("templates", []):
			self.template_list.addItem(
				f"{template.get('name') or template.get('id')} - {template.get('description') or ''}".strip()
			)

	def _refresh_visual_map(self) -> None:
		self._refresh_visual_dependency_controls()
		self.visual_scene.clear()
		jtbds = list(self.document.bundle.get("jtbds", []) or [])
		if not jtbds:
			return

		positions: dict[str, tuple[int, int]] = {}
		node_w = 210
		node_h = 74
		x_gap = 260
		y_gap = 126
		for idx, jtbd in enumerate(jtbds):
			jtbd_id = str(jtbd.get("id") or f"job_{idx + 1}")
			positions[jtbd_id] = (40 + (idx % 3) * x_gap, 40 + (idx // 3) * y_gap)

		edge_pen = QPen(QColor(self.theme["muted"]))
		edge_pen.setWidth(2)
		missing_pen = QPen(QColor(self.theme["danger"]))
		missing_pen.setWidth(2)
		missing_pen.setStyle(Qt.PenStyle.DashLine)
		for jtbd in jtbds:
			jtbd_id = str(jtbd.get("id") or "")
			to_pos = positions.get(jtbd_id)
			if to_pos is None:
				continue
			to_x, to_y = to_pos
			for required in jtbd.get("requires", []) or []:
				from_pos = positions.get(str(required))
				if from_pos is None:
					self.visual_scene.addText(f"Missing dependency: {required} -> {jtbd_id}")
					continue
				from_x, from_y = from_pos
				self.visual_scene.addLine(
					from_x + node_w,
					from_y + node_h / 2,
					to_x,
					to_y + node_h / 2,
					edge_pen if str(required) in positions else missing_pen,
				)

		border = QPen(QColor(self.theme["primary"]))
		border.setWidth(2)
		fill = QBrush(QColor(self.theme["surface"]))
		for idx, jtbd in enumerate(jtbds):
			jtbd_id = str(jtbd.get("id") or f"job_{idx + 1}")
			x, y = positions[jtbd_id]
			rect = self.visual_scene.addRect(x, y, node_w, node_h, border, fill)
			rect.setToolTip("Double-click the row in the left JTBD Map to edit this job.")
			title = str(jtbd.get("title") or jtbd_id)
			label = self.visual_scene.addText(f"{title}\n{jtbd_id}")
			label.setDefaultTextColor(QColor(self.theme["text"]))
			label.setPos(x + 12, y + 10)
			if idx == self.current_index:
				selected = QPen(QColor(self.theme["accent"]))
				selected.setWidth(4)
				rect.setPen(selected)

		self.visual_scene.setSceneRect(self.visual_scene.itemsBoundingRect().adjusted(-40, -40, 80, 80))

	def _refresh_visual_dependency_controls(self) -> None:
		current_source = self.visual_dependency_source.currentData()
		current_target = self.visual_dependency_target.currentData()
		self.visual_dependency_source.blockSignals(True)
		self.visual_dependency_target.blockSignals(True)
		self.visual_dependency_source.clear()
		self.visual_dependency_target.clear()
		for idx, jtbd in enumerate(self.document.bundle.get("jtbds", []) or []):
			label = f"{jtbd.get('title') or jtbd.get('id')} ({jtbd.get('id')})"
			self.visual_dependency_source.addItem(label, idx)
			self.visual_dependency_target.addItem(label, str(jtbd.get("id") or ""))
		_restore_combo_data(self.visual_dependency_source, current_source, self.current_index)
		_restore_combo_data(self.visual_dependency_target, current_target, 0)
		self.visual_dependency_source.blockSignals(False)
		self.visual_dependency_target.blockSignals(False)


def run_desktop_editor(bundle: Path | None = None, theme: Path | None = None) -> int:
	"""Launch the PyQt JTBD desktop editor."""

	if Qt is None:
		raise RuntimeError(
			"PyQt6 is required for the desktop editor. Install it with "
			"`uv sync --package flowforge-cli --extra desktop`, "
			"`uv pip install 'flowforge-cli[desktop]'`, or "
			"`uv run --with PyQt6 flowforge jtbd desktop`."
		)
	theme_data = _read_theme(theme) if theme else None
	document = JtbdDocument.load(bundle) if bundle else JtbdDocument()
	app = QApplication.instance() or QApplication(sys.argv)
	window = JtbdEditorWindow(document, theme=theme_data)
	window.show()
	return int(app.exec())


def _read_theme(path: Path) -> dict[str, Any]:
	data = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(data, dict):
		raise ValueError("theme file must contain a JSON object")
	return data


def _load_theme(theme: dict[str, Any] | None) -> dict[str, str]:
	defaults = {
		"background": "#f6f8fb",
		"surface": "#ffffff",
		"surface_alt": "#edf2f7",
		"text": "#172033",
		"muted": "#5b677a",
		"border": "#d8e0ec",
		"primary": "#2563eb",
		"accent": "#10b981",
		"danger": "#b42318",
		"radius": "8px",
		"font_family": "Inter, system-ui, sans-serif",
	}
	out = dict(defaults)
	if theme:
		out.update({k: str(v) for k, v in theme.items() if k in out})
	return out


def _stylesheet(theme: dict[str, str]) -> str:
	return f"""
	* {{
		font-family: {theme["font_family"]};
		font-size: 13px;
	}}
	QMainWindow {{
		background: {theme["background"]};
		color: {theme["text"]};
	}}
	QMenuBar, QMenu, QToolBar {{
		background: {theme["surface"]};
		border: 0;
		color: {theme["text"]};
	}}
	QFrame#sidebar, QFrame#rightPanel, QGroupBox {{
		background: {theme["surface"]};
		border: 1px solid {theme["border"]};
		border-radius: {theme["radius"]};
	}}
	QLabel#sidebarTitle {{
		font-size: 18px;
		font-weight: 700;
		color: {theme["text"]};
	}}
	QGroupBox {{
		margin-top: 12px;
		padding: 14px;
		font-weight: 700;
	}}
	QGroupBox::title {{
		subcontrol-origin: margin;
		left: 14px;
		padding: 0 6px;
		color: {theme["muted"]};
	}}
	QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QTableWidget, QListWidget {{
		background: {theme["surface"]};
		border: 1px solid {theme["border"]};
		border-radius: {theme["radius"]};
		color: {theme["text"]};
		padding: 6px;
		selection-background-color: {theme["primary"]};
	}}
	QTableWidget {{
		gridline-color: {theme["border"]};
	}}
	QHeaderView::section {{
		background: {theme["surface_alt"]};
		color: {theme["muted"]};
		padding: 6px;
		border: 0;
		border-right: 1px solid {theme["border"]};
	}}
	QPushButton {{
		background: {theme["primary"]};
		color: white;
		border: 0;
		border-radius: {theme["radius"]};
		padding: 8px 10px;
		font-weight: 600;
	}}
	QPushButton:hover {{
		background: {theme["accent"]};
	}}
	QTabWidget::pane {{
		border: 1px solid {theme["border"]};
		border-radius: {theme["radius"]};
		background: {theme["surface"]};
	}}
	QTabBar::tab {{
		padding: 8px 12px;
		color: {theme["muted"]};
	}}
	QTabBar::tab:selected {{
		color: {theme["primary"]};
		font-weight: 700;
	}}
	"""


def _combo(values: list[str]) -> QComboBox:
	box = QComboBox()
	box.addItems(values)
	return box


def _restore_combo_data(combo: QComboBox, data: Any, fallback_index: int) -> None:
	for idx in range(combo.count()):
		if combo.itemData(idx) == data:
			combo.setCurrentIndex(idx)
			return
	if combo.count():
		combo.setCurrentIndex(max(0, min(fallback_index, combo.count() - 1)))


def _connect_change(widget: Any, slot: Any) -> None:
	if isinstance(widget, QLineEdit):
		widget.textChanged.connect(slot)
	elif isinstance(widget, QPlainTextEdit):
		widget.textChanged.connect(slot)
	elif isinstance(widget, QComboBox):
		widget.currentTextChanged.connect(slot)
	elif isinstance(widget, QCheckBox):
		widget.stateChanged.connect(slot)


def _table(headers: list[str], stretch_last: bool = False) -> QTableWidget:
	table = QTableWidget(0, len(headers))
	table.setHorizontalHeaderLabels(headers)
	table.setAlternatingRowColors(True)
	table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
	table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
	table.verticalHeader().setVisible(False)
	table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
	if stretch_last:
		table.horizontalHeader().setStretchLastSection(True)
	return table


def _table_panel(table: QTableWidget, changed: Any | None = None) -> QWidget:
	host = QWidget()
	layout = QVBoxLayout(host)
	layout.setContentsMargins(8, 8, 8, 8)
	buttons = QHBoxLayout()
	add = QPushButton("Add Row")
	remove = QPushButton("Remove Row")
	add.clicked.connect(lambda: _mutate_table(table, _add_empty_row, changed))
	remove.clicked.connect(lambda: _mutate_table(table, _remove_selected_row, changed))
	buttons.addWidget(add)
	buttons.addWidget(remove)
	buttons.addStretch(1)
	layout.addLayout(buttons)
	layout.addWidget(table)
	return host


def _mutate_table(table: QTableWidget, mutator: Any, changed: Any | None) -> None:
	mutator(table)
	if changed is not None:
		changed()


def _add_empty_row(table: QTableWidget) -> None:
	row = table.rowCount()
	table.insertRow(row)
	for col in range(table.columnCount()):
		table.setItem(row, col, QTableWidgetItem(""))


def _remove_selected_row(table: QTableWidget) -> None:
	row = table.currentRow()
	if row >= 0:
		table.removeRow(row)


def _set_string_rows(table: QTableWidget, values: list[Any]) -> None:
	_set_rows(table, [[str(v)] for v in values])


def _string_rows(table: QTableWidget) -> list[str]:
	return [row[0] for row in _rows(table) if row and row[0]]


def _set_field_rows(table: QTableWidget, fields: list[dict[str, Any]]) -> None:
	rows = []
	for field in fields:
		rows.append([
			field.get("id", ""),
			field.get("kind", "text"),
			field.get("label", ""),
			"true" if field.get("required") else "false",
			"true" if field.get("pii") else "false",
			", ".join(field.get("sensitivity", []) or []),
		])
	_set_rows(table, rows)


def _field_rows(table: QTableWidget) -> list[dict[str, Any]]:
	out = []
	for row in _rows(table):
		if not row or not row[0]:
			continue
		kind = row[1] or "text"
		pii = _bool(row[4])
		if row[4] == "" and requires_pii(kind):
			pii = True
		out.append({
			"id": row[0],
			"kind": kind,
			"label": row[2] or row[0].replace("_", " ").title(),
			"required": _bool(row[3]),
			"pii": pii,
			"validation": {},
			"sensitivity": _csv(row[5]),
		})
	return out


def _set_edge_rows(table: QTableWidget, edges: list[dict[str, Any]]) -> None:
	_set_rows(table, [[e.get("id", ""), e.get("condition", ""), e.get("handle", "reject"), e.get("branch_to", "") or ""] for e in edges])


def _edge_rows(table: QTableWidget) -> list[dict[str, Any]]:
	out = []
	for row in _rows(table):
		if not row or not row[0]:
			continue
		entry = {"id": row[0], "condition": row[1], "handle": row[2] or "reject"}
		if entry["handle"] == "branch":
			entry["branch_to"] = row[3]
		out.append(entry)
	return out


def _set_doc_rows(table: QTableWidget, docs: list[dict[str, Any]]) -> None:
	_set_rows(table, [[d.get("kind", ""), d.get("min", 1), d.get("max", "") or "", d.get("freshness_days", "") or "", "true" if d.get("av_required", True) else "false"] for d in docs])


def _doc_rows(table: QTableWidget) -> list[dict[str, Any]]:
	out = []
	for row in _rows(table):
		if not row or not row[0]:
			continue
		entry: dict[str, Any] = {"kind": row[0], "min": _int(row[1], 1), "av_required": _bool(row[4], True)}
		if row[2]:
			entry["max"] = _int(row[2], 1)
		if row[3]:
			entry["freshness_days"] = _int(row[3], 1)
		out.append(entry)
	return out


def _set_approval_rows(table: QTableWidget, approvals: list[dict[str, Any]]) -> None:
	_set_rows(table, [[a.get("role", ""), a.get("policy", "1_of_1"), a.get("n", "") or "", a.get("tier", "") or ""] for a in approvals])


def _approval_rows(table: QTableWidget) -> list[dict[str, Any]]:
	out = []
	for row in _rows(table):
		if not row or not row[0]:
			continue
		entry: dict[str, Any] = {"role": row[0], "policy": row[1] or "1_of_1"}
		if entry["policy"] == "n_of_m":
			entry["n"] = _int(row[2], 1)
		if entry["policy"] == "authority_tier":
			entry["tier"] = _int(row[3], 1)
		out.append(entry)
	return out


def _set_notification_rows(table: QTableWidget, notifications: list[dict[str, Any]]) -> None:
	_set_rows(table, [[n.get("trigger", "state_enter"), n.get("channel", "in_app"), n.get("audience", "")] for n in notifications])


def _notification_rows(table: QTableWidget) -> list[dict[str, Any]]:
	out = []
	for row in _rows(table):
		if not row or not row[2]:
			continue
		out.append({"trigger": row[0] or "state_enter", "channel": row[1] or "in_app", "audience": row[2]})
	return out


def _set_entity_rows(table: QTableWidget, entities: list[dict[str, Any]]) -> None:
	_set_rows(table, [[e.get("name", ""), e.get("id_field", "")] for e in entities])


def _entity_rows(table: QTableWidget) -> list[dict[str, str]]:
	out = []
	for row in _rows(table):
		if not row or not row[0]:
			continue
		out.append({"name": row[0], "id_field": row[1] or f"{row[0]}_id"})
	return out


def _set_rows(table: QTableWidget, rows: list[list[Any]]) -> None:
	table.blockSignals(True)
	table.setRowCount(0)
	for values in rows:
		row = table.rowCount()
		table.insertRow(row)
		for col in range(table.columnCount()):
			table.setItem(row, col, QTableWidgetItem(str(values[col]) if col < len(values) else ""))
	table.blockSignals(False)


def _rows(table: QTableWidget) -> list[list[str]]:
	out = []
	for row in range(table.rowCount()):
		values = []
		for col in range(table.columnCount()):
			item = table.item(row, col)
			values.append(item.text().strip() if item else "")
		if any(values):
			out.append(values)
	return out


def _csv(value: str) -> list[str]:
	return [v.strip() for v in value.split(",") if v.strip()]


def _csv_enum(value: str, allowed: list[str]) -> list[str]:
	canonical = {item.lower(): item for item in allowed}
	return [canonical.get(item.lower(), item) for item in _csv(value)]


def _unique_template_id(base: str, existing: set[str]) -> str:
	candidate = normalise_id(base, fallback="template")
	i = 2
	while candidate in existing:
		candidate = f"{normalise_id(base, fallback='template')}_{i}"
		i += 1
	return candidate


def _bool(value: str, default: bool = False) -> bool:
	if value == "":
		return default
	return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: str, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default
