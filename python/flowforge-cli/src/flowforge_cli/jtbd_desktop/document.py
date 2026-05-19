"""Document model for the optional PyQt JTBD desktop editor."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flowforge_jtbd.dsl.spec import JtbdBundle, SENSITIVE_FIELD_KINDS

from .._io import load_structured, write_json
from ..commands.jtbd_lint import _adapt_to_lint_bundle
from flowforge_jtbd.lint.linter import Linter


_ID_RE = re.compile(r"[^a-z0-9_]+")


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
			"department": None,
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
				_append_lint_issue(issue.severity, f"bundle: {issue.rule}: {issue.message}", warnings, infos)
			for result in report.results:
				for issue in result.issues:
					_append_lint_issue(
						issue.severity,
						f"{result.jtbd_id}: {issue.rule}: {issue.message}",
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
		src.pop("spec_hash", None)
		self.bundle.setdefault("jtbds", []).append(src)
		self.dirty = True
		return len(self.bundle["jtbds"]) - 1

	def remove_jtbd(self, index: int) -> None:
		jtbds = self.bundle.get("jtbds", [])
		if len(jtbds) <= 1:
			raise ValueError("a JTBD bundle must contain at least one job")
		del jtbds[index]
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
	message: str,
	warnings: list[str],
	infos: list[str],
) -> None:
	if severity == "info":
		infos.append(message)
	else:
		warnings.append(f"semantic {severity}: {message}")
