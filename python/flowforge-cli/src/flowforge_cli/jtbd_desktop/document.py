"""Document model for the optional PyQt JTBD desktop editor."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flowforge_jtbd.dsl.spec import JtbdBundle, SENSITIVE_FIELD_KINDS

from .._io import load_structured, write_json
from ..commands.jtbd_lint import _adapt_to_lint_bundle
from ..jtbd import generate
from ..jtbd.parse import JTBDParseError, parse_bundle
from flowforge_jtbd.lint.linter import Linter


_ID_RE = re.compile(r"[^a-z0-9_]+")
TEMPLATE_LIBRARY_VERSION = "1.0"


def create_template_library() -> dict[str, Any]:
	"""Return a starter reusable-template sidecar for the editor."""

	return {
		"schema_version": TEMPLATE_LIBRARY_VERSION,
		"templates": [
			{
				"id": "approval_intake",
				"name": "Approval intake",
				"description": "Capture a request and route it to one reviewer.",
				"jtbd": create_default_jtbd("approval_intake", "Approval intake"),
			},
			{
				"id": "document_review",
				"name": "Document review",
				"description": "Collect supporting documents and verify them before approval.",
				"jtbd": _document_review_template(),
			},
		],
	}


def load_template_library(path: Path) -> dict[str, Any]:
	"""Load and validate a desktop template-library sidecar."""

	data = load_structured(path)
	_validate_template_library(data)
	return data


def save_template_library(path: Path, data: dict[str, Any]) -> None:
	"""Persist a desktop template-library sidecar as deterministic JSON."""

	_validate_template_library(data)
	write_json(path, data)


def build_template_from_jtbd(jtbd: dict[str, Any], description: str = "") -> dict[str, Any]:
	"""Return a template-library entry for an existing JTBD."""

	jtbd_copy = copy.deepcopy(jtbd)
	_strip_storage_metadata(jtbd_copy)
	template_id = normalise_id(str(jtbd_copy.get("id") or jtbd_copy.get("title") or "template"))
	return {
		"id": template_id,
		"name": str(jtbd_copy.get("title") or template_id.replace("_", " ").title()),
		"description": description,
		"jtbd": jtbd_copy,
	}


def create_jtbd_from_template(
	template: dict[str, Any],
	existing_ids: set[str],
	title: str | None = None,
) -> dict[str, Any]:
	"""Materialise a template as a bundle-safe JTBD with a unique id."""

	src = copy.deepcopy(template.get("jtbd") or {})
	if not src:
		raise ValueError("template must contain a jtbd object")
	base_title = title or str(src.get("title") or template.get("name") or "New job")
	base = normalise_id(str(src.get("id") or base_title), fallback="job")
	jtbd_id = _unique_id(base, existing_ids)
	src["id"] = jtbd_id
	src["title"] = base_title
	src["status"] = "draft"
	_strip_storage_metadata(src)
	src.setdefault("annotations", {})
	src["annotations"]["source_template"] = str(template.get("id") or "")
	return src


def create_jtbd_from_prompt(prompt: str, existing_ids: set[str]) -> dict[str, Any]:
	"""Create a deterministic AI-assisted draft JTBD from natural language.

	This is intentionally local and reviewable. Real LLM copy polish remains
	an optional sidecar workflow; the editor still gives authors a useful
	first draft without network access or credentials.
	"""

	clean = " ".join(prompt.split())
	if not clean:
		raise ValueError("prompt is required")
	title = _title_from_prompt(clean)
	jtbd_id = _unique_id(normalise_id(title, fallback="ai_generated_job"), existing_ids)
	jtbd = create_default_jtbd(jtbd_id, title)
	jtbd["situation"] = f"A user needs to {clean.rstrip('.')}"
	jtbd["motivation"] = "They want Flowforge to turn the job into a reliable workflow quickly."
	jtbd["outcome"] = "The job is captured, verified, and ready to generate an application."
	jtbd["data_capture"] = _fields_from_prompt(clean)
	jtbd["annotations"] = {
		"ai_assist": {
			"source": "desktop_local_draft",
			"prompt": prompt,
			"review_required": True,
		}
	}
	return jtbd


def build_ai_authoring_prompt(bundle: dict[str, Any], jtbd: dict[str, Any] | None = None) -> str:
	"""Build a copyable prompt for external AI review of a JTBD bundle."""

	project = bundle.get("project", {})
	selection = jtbd or (bundle.get("jtbds") or [{}])[0]
	return (
		"You are helping author a Flowforge JTBD. Improve the selected job while "
		"preserving valid JTBD JSON fields, snake_case ids, explicit pii flags, "
		"and generation compatibility.\n\n"
		f"Project: {project.get('name', '')} ({project.get('package', '')})\n"
		f"Selected JTBD JSON:\n{json.dumps(selection, indent=2, sort_keys=True)}\n"
	)


def verify_generation(bundle: dict[str, Any]) -> ValidationResult:
	"""Run parser and generator verification for a desktop-authored bundle."""

	errors: list[str] = []
	warnings: list[str] = []
	infos: list[str] = []
	try:
		parse_bundle(bundle)
	except JTBDParseError as exc:
		errors.append(str(exc))
	if not errors:
		try:
			files = generate(bundle)
		except (JTBDParseError, ValueError) as exc:
			errors.append(str(exc))
		else:
			infos.append(f"generation emits {len(files)} files")
	return ValidationResult(not errors, errors, warnings, infos)


def normalise_id(value: str, fallback: str = "job") -> str:
	"""Return a JTBD-safe snake_case identifier."""

	base = value.strip().lower()
	base = _ID_RE.sub("_", base)
	base = re.sub(r"_+", "_", base).strip("_")
	if not base or not ("a" <= base[0] <= "z"):
		base = fallback
	return base


def create_default_bundle(
	name: str = "New Flowforge Project",
	package: str = "new_flowforge_project",
	domain: str = "case",
) -> dict[str, Any]:
	"""Return a valid one-job bundle for first-run authoring."""

	pkg = normalise_id(package or name, fallback="flowforge_project")
	return {
		"project": {
			"name": name,
			"package": pkg,
			"domain": domain or "case",
			"tenancy": "multi",
			"languages": ["en"],
			"currencies": ["USD"],
			"frontend_framework": "vite-react",
			"frontend": {"form_renderer": "real"},
			"design": {
				"primary": "#2563eb",
				"accent": "#10b981",
				"font_family": "Inter, system-ui, sans-serif",
				"density": "comfortable",
				"radius_scale": 1.0,
			},
			"compliance": [],
			"data_sensitivity": ["PII"],
			"annotations": {
				"notes": "",
				"tags": ["draft"],
			},
		},
		"shared": {
			"roles": ["requester", "reviewer"],
			"permissions": ["case.submit", "case.review"],
			"entities": [{"name": "case", "id_field": "case_id"}],
		},
		"jtbds": [
			create_default_jtbd(
				"intake_case",
				"Intake case",
				actor_role="requester",
			)
		],
	}


def create_default_jtbd(
	jtbd_id: str,
	title: str,
	actor_role: str = "requester",
) -> dict[str, Any]:
	"""Return a valid starter JTBD with production-friendly defaults."""

	safe_id = normalise_id(jtbd_id or title, fallback="job")
	return {
		"id": safe_id,
		"title": title or safe_id.replace("_", " ").title(),
		"version": "1.0.0",
		"status": "draft",
		"actor": {
			"role": actor_role or "requester",
			"external": False,
		},
		"situation": "A requester needs this work completed with clear ownership.",
		"motivation": "They want a reliable, auditable path from intake to decision.",
		"outcome": "The work is completed, recorded, and ready for downstream action.",
		"success_criteria": [
			"Required information is captured before review.",
			"The reviewer can make a decision without re-keying data.",
		],
		"edge_cases": [
			{
				"id": "missing_information",
				"condition": "Required information is incomplete or inconsistent.",
				"handle": "reject",
			}
		],
		"data_capture": [
			{
				"id": "requester_email",
				"kind": "email",
				"label": "Requester email",
				"required": True,
				"pii": True,
				"validation": {},
				"sensitivity": ["PII"],
			},
			{
				"id": "summary",
				"kind": "textarea",
				"label": "Summary",
				"required": True,
				"pii": False,
				"validation": {"min_length": 20},
				"sensitivity": [],
			},
		],
		"documents_required": [],
		"approvals": [{"role": "reviewer", "policy": "1_of_1"}],
		"sla": {"warn_pct": 80, "breach_seconds": 86400},
		"notifications": [
			{
				"trigger": "state_enter",
				"channel": "in_app",
				"audience": "reviewer",
			}
		],
		"metrics": ["cycle_time_seconds", "first_pass_acceptance_rate"],
		"requires": [],
		"compliance": [],
		"data_sensitivity": ["PII"],
		"annotations": {
			"notes": "",
			"tags": ["draft"],
		},
	}


@dataclass
class ValidationResult:
	"""Validation summary for UI display."""

	ok: bool
	errors: list[str]
	warnings: list[str]
	infos: list[str]


class JtbdDocument:
	"""Mutable bundle document used by the desktop editor."""

	def __init__(self, bundle: dict[str, Any] | None = None, path: Path | None = None) -> None:
		self.bundle: dict[str, Any] = copy.deepcopy(bundle or create_default_bundle())
		self.path = path
		self.dirty = False

	@classmethod
	def load(cls, path: Path) -> "JtbdDocument":
		return cls(load_structured(path), path=path)

	def save(self, path: Path | None = None) -> None:
		target = path or self.path
		if target is None:
			raise ValueError("path is required for first save")
		write_json(target, self.bundle)
		self.path = target
		self.dirty = False

	def validate(self) -> ValidationResult:
		errors: list[str] = []
		warnings: list[str] = []
		infos: list[str] = []
		try:
			JtbdBundle.model_validate(self.bundle)
		except Exception as exc:
			errors.append(str(exc))

		try:
			report = Linter().lint(_adapt_to_lint_bundle(self.bundle))
		except Exception as exc:
			warnings.append(f"linter unavailable: {exc}")
		else:
			for issue in report.bundle_issues:
				_append_lint_issue(
					issue.severity,
					issue.rule,
					f"bundle: {issue.rule}: {issue.message}",
					errors,
					warnings,
					infos,
				)
			for result in report.results:
				for issue in result.issues:
					_append_lint_issue(
						issue.severity,
						issue.rule,
						f"{result.jtbd_id}: {issue.rule}: {issue.message}",
						errors,
						warnings,
						infos,
					)
		return ValidationResult(not errors, errors, warnings, infos)

	def jtbd_ids(self) -> list[str]:
		return [str(j.get("id", "")) for j in self.bundle.get("jtbds", [])]

	def get_jtbd(self, index: int) -> dict[str, Any]:
		return self.bundle["jtbds"][index]

	def add_jtbd(self, title: str) -> int:
		existing = set(self.jtbd_ids())
		base = normalise_id(title, fallback="job")
		jtbd_id = base
		i = 2
		while jtbd_id in existing:
			jtbd_id = f"{base}_{i}"
			i += 1
		self.bundle.setdefault("jtbds", []).append(create_default_jtbd(jtbd_id, title))
		self.dirty = True
		return len(self.bundle["jtbds"]) - 1

	def add_jtbd_from_template(self, template: dict[str, Any], title: str | None = None) -> int:
		jtbd = create_jtbd_from_template(template, set(self.jtbd_ids()), title=title)
		self.bundle.setdefault("jtbds", []).append(jtbd)
		self.dirty = True
		return len(self.bundle["jtbds"]) - 1

	def add_jtbd_from_prompt(self, prompt: str) -> int:
		jtbd = create_jtbd_from_prompt(prompt, set(self.jtbd_ids()))
		self.bundle.setdefault("jtbds", []).append(jtbd)
		self.dirty = True
		return len(self.bundle["jtbds"]) - 1

	def duplicate_jtbd(self, index: int) -> int:
		src = copy.deepcopy(self.get_jtbd(index))
		existing = set(self.jtbd_ids())
		base = normalise_id(f"{src.get('id', 'job')}_copy", fallback="job_copy")
		jtbd_id = base
		i = 2
		while jtbd_id in existing:
			jtbd_id = f"{base}_{i}"
			i += 1
		src["id"] = jtbd_id
		src["title"] = f"{src.get('title') or src['id']} copy"
		src["status"] = "draft"
		_strip_storage_metadata(src)
		self.bundle.setdefault("jtbds", []).append(src)
		self.dirty = True
		return len(self.bundle["jtbds"]) - 1

	def remove_jtbd(self, index: int) -> None:
		jtbds = self.bundle.get("jtbds", [])
		if len(jtbds) <= 1:
			raise ValueError("a JTBD bundle must contain at least one job")
		del jtbds[index]
		self.dirty = True

	def add_dependency(self, index: int, required_id: str) -> None:
		"""Add a composition dependency to a JTBD."""

		required = required_id.strip()
		if not required:
			raise ValueError("dependency id is required")
		jtbd = self.get_jtbd(index)
		jtbd_id = str(jtbd.get("id") or "")
		if required == jtbd_id:
			raise ValueError("a JTBD cannot depend on itself")
		if required not in set(self.jtbd_ids()):
			raise ValueError(f"unknown dependency id: {required}")
		requires = list(jtbd.get("requires") or [])
		if required not in requires:
			requires.append(required)
			jtbd["requires"] = requires
			jtbd.pop("spec_hash", None)
			self.dirty = True

	def remove_dependency(self, index: int, required_id: str) -> None:
		"""Remove a composition dependency from a JTBD if present."""

		required = required_id.strip()
		jtbd = self.get_jtbd(index)
		requires = [r for r in (jtbd.get("requires") or []) if str(r) != required]
		if requires != list(jtbd.get("requires") or []):
			jtbd["requires"] = requires
			jtbd.pop("spec_hash", None)
			self.dirty = True

	def set_project_value(self, key: str, value: Any) -> None:
		self.bundle.setdefault("project", {})[key] = value
		self.dirty = True

	def set_design_value(self, key: str, value: Any) -> None:
		project = self.bundle.setdefault("project", {})
		project.setdefault("design", {})[key] = value
		self.dirty = True

	def set_frontend_renderer(self, value: str) -> None:
		project = self.bundle.setdefault("project", {})
		project.setdefault("frontend", {})["form_renderer"] = value
		self.dirty = True

	def set_jtbd_value(self, index: int, key: str, value: Any) -> None:
		self.get_jtbd(index)[key] = value
		if key in {"id", "title", "version", "status", "actor", "situation", "motivation", "outcome"}:
			self.get_jtbd(index).pop("spec_hash", None)
		self.dirty = True


def requires_pii(kind: str) -> bool:
	return kind in SENSITIVE_FIELD_KINDS


def _append_lint_issue(
	severity: str,
	rule: str,
	message: str,
	errors: list[str],
	warnings: list[str],
	infos: list[str],
) -> None:
	if severity == "info":
		infos.append(message)
	elif severity == "error" and rule not in {"missing_required_stage"}:
		errors.append(f"semantic error: {message}")
	else:
		warnings.append(f"semantic {severity}: {message}")


def _unique_id(base: str, existing_ids: set[str]) -> str:
	candidate = normalise_id(base, fallback="job")
	i = 2
	while candidate in existing_ids:
		candidate = f"{normalise_id(base, fallback='job')}_{i}"
		i += 1
	return candidate


def _strip_storage_metadata(jtbd: dict[str, Any]) -> None:
	"""Remove storage-managed JTBD metadata from desktop-authored copies."""

	for key in (
		"spec_hash",
		"parent_version_id",
		"replaced_by",
		"created_by",
		"published_by",
	):
		jtbd.pop(key, None)


def _title_from_prompt(prompt: str) -> str:
	words = prompt.split()
	if len(words) <= 7:
		return prompt.rstrip(".").capitalize()
	return " ".join(words[:7]).rstrip(".,:;").capitalize()


def _fields_from_prompt(prompt: str) -> list[dict[str, Any]]:
	lower = prompt.lower()
	fields = [
		{
			"id": "summary",
			"kind": "textarea",
			"label": "Summary",
			"required": True,
			"pii": False,
			"validation": {"min_length": 20},
			"sensitivity": [],
		}
	]
	if "email" in lower:
		fields.insert(0, _field("requester_email", "email", "Requester email", pii=True))
	if "phone" in lower:
		fields.append(_field("phone_number", "phone", "Phone number", pii=True))
	if "amount" in lower or "money" in lower or "payment" in lower:
		fields.append(_field("amount", "money", "Amount", pii=False))
	if "date" in lower or "deadline" in lower:
		fields.append(_field("target_date", "date", "Target date", pii=False))
	if "document" in lower or "file" in lower or "attachment" in lower:
		fields.append(_field("supporting_document", "file", "Supporting document", pii=True))
	return fields


def _field(field_id: str, kind: str, label: str, pii: bool) -> dict[str, Any]:
	return {
		"id": field_id,
		"kind": kind,
		"label": label,
		"required": True,
		"pii": pii,
		"validation": {},
		"sensitivity": ["PII"] if pii else [],
	}


def _document_review_template() -> dict[str, Any]:
	jtbd = create_default_jtbd("document_review", "Document review")
	jtbd["data_capture"].append(
		_field("supporting_document", "file", "Supporting document", pii=True)
	)
	jtbd["documents_required"] = [{"kind": "supporting_document", "min": 1, "av_required": True}]
	return jtbd


def _validate_template_library(data: dict[str, Any]) -> None:
	templates = data.get("templates")
	if not isinstance(templates, list):
		raise ValueError("template library must contain a templates list")
	seen: set[str] = set()
	for template in templates:
		if not isinstance(template, dict):
			raise ValueError("template entries must be objects")
		template_id = str(template.get("id") or "")
		if not template_id:
			raise ValueError("template entries must have an id")
		if template_id in seen:
			raise ValueError(f"duplicate template id {template_id!r}")
		seen.add(template_id)
		jtbd = template.get("jtbd")
		if not isinstance(jtbd, dict):
			raise ValueError(f"template {template_id!r} must contain a jtbd object")
		JtbdBundle.model_validate(create_default_bundle() | {"jtbds": [jtbd]})
