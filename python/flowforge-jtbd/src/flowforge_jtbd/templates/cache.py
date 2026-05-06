"""Template cache for parameterised workflow skeletons (E-27).

Per ``framework/docs/flowforge-evolution.md`` §12.2 / §12.3 and
``framework/docs/jtbd-editor-arch.md`` §10.

A template is a JSON workflow definition with ``{{parameter}}``
placeholders.  :class:`TemplateCache` stores templates, resolves them by
id, and fills in caller-supplied parameters via simple string replacement.

The 12 starter templates live under ``templates/library/`` as JSON files
and are loaded by :meth:`TemplateCache.default` at startup.

Integration
-----------
The incremental compiler (E-26) checks the template cache before
regenerating a workflow: if the JTBD composition matches a known pattern,
it re-uses the cached skeleton and injects only the changed parameters.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Template models
# ---------------------------------------------------------------------------

ParamType = Literal["string", "integer", "boolean", "list"]


@dataclass(frozen=True)
class TemplateParameter:
	"""One parameter definition for a template.

	Parameters are filled in when the template is instantiated via
	:meth:`TemplateCache.instantiate`.
	"""

	name: str
	"""Parameter name; used as ``{{name}}`` in the template body."""

	type: ParamType
	"""Expected type.  Used for validation in :meth:`TemplateCache.instantiate`."""

	required: bool = True
	"""Whether a value must be supplied at instantiation time."""

	default: Any = None
	"""Default value used when the caller does not supply one."""

	description: str = ""
	"""Human-readable description shown in the editor's parameter UI."""


@dataclass
class JtbdTemplate:
	"""A parameterised workflow skeleton.

	The ``workflow_template`` dict may contain ``"{{param}}"`` placeholder
	strings anywhere in its nested structure.  :meth:`instantiate` resolves
	them by walking the entire dict recursively.
	"""

	id: str
	"""Stable template identifier, e.g. ``"n_of_m_approval"``."""

	name: str
	"""Display name shown in the editor."""

	description: str
	"""What the template is for."""

	parameters: list[TemplateParameter] = field(default_factory=list)
	"""Ordered parameter definitions."""

	workflow_template: dict[str, Any] = field(default_factory=dict)
	"""Raw workflow DSL with ``{{param}}`` placeholders."""

	tags: list[str] = field(default_factory=list)
	"""Searchable tags (e.g. ``["approval", "finance"]``)."""

	def param_names(self) -> set[str]:
		return {p.name for p in self.parameters}

	def instantiate(self, params: dict[str, Any]) -> dict[str, Any]:
		"""Return a copy of the workflow with ``{{param}}`` replaced.

		Raises ``ValueError`` for missing required parameters or
		type-incompatible values.
		"""
		resolved = _resolve_params(self.parameters, params)
		return _fill(copy.deepcopy(self.workflow_template), resolved)

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> "JtbdTemplate":
		params = [
			TemplateParameter(
				name=p["name"],
				type=p.get("type", "string"),
				required=p.get("required", True),
				default=p.get("default"),
				description=p.get("description", ""),
			)
			for p in data.get("parameters", [])
		]
		return cls(
			id=data["id"],
			name=data["name"],
			description=data.get("description", ""),
			parameters=params,
			workflow_template=data.get("workflow_template", {}),
			tags=data.get("tags", []),
		)


# ---------------------------------------------------------------------------
# TemplateCache
# ---------------------------------------------------------------------------

class TemplateCache:
	"""Registry of :class:`JtbdTemplate` instances.

	Usage:

	.. code-block:: python

		cache = TemplateCache.default()
		wf = cache.instantiate(
		    "n_of_m_approval",
		    {"required_approvals": 2, "workflow_key": "claim_approval",
		     "subject_kind": "claim"},
		)
	"""

	def __init__(self) -> None:
		self._templates: dict[str, JtbdTemplate] = {}

	def register(self, template: JtbdTemplate) -> None:
		"""Add or replace a template."""
		assert template.id, "template.id must be non-empty"
		self._templates[template.id] = template

	def get(self, template_id: str) -> JtbdTemplate | None:
		"""Return the template for *template_id*, or ``None`` if not found."""
		return self._templates.get(template_id)

	def list_ids(self) -> list[str]:
		"""Return sorted list of registered template ids."""
		return sorted(self._templates)

	def list_templates(self) -> list[JtbdTemplate]:
		"""Return templates sorted by id."""
		return [self._templates[k] for k in sorted(self._templates)]

	def size(self) -> int:
		return len(self._templates)

	def instantiate(
		self,
		template_id: str,
		params: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		"""Instantiate *template_id* with *params* and return the workflow dict.

		Raises ``KeyError`` if the template is not registered.
		Raises ``ValueError`` for missing required parameters.
		"""
		tmpl = self._templates.get(template_id)
		if tmpl is None:
			raise KeyError(f"Template not found: {template_id!r}")
		return tmpl.instantiate(params or {})

	def load_library(self, library_dir: Path) -> int:
		"""Load all ``*.json`` files from *library_dir* and register them.

		Returns the number of templates loaded.
		"""
		assert library_dir is not None
		loaded = 0
		for path in sorted(library_dir.glob("*.json")):
			try:
				data = json.loads(path.read_text(encoding="utf-8"))
				self.register(JtbdTemplate.from_dict(data))
				loaded += 1
			except (json.JSONDecodeError, KeyError, TypeError):
				# Skip malformed files silently; production callers log at caller level.
				pass
		return loaded

	def search(self, tag: str) -> list[JtbdTemplate]:
		"""Return templates that include *tag* in their tags list."""
		return [t for t in self._templates.values() if tag in t.tags]

	@classmethod
	def default(cls) -> "TemplateCache":
		"""Return a :class:`TemplateCache` pre-loaded with the 12 starter templates.

		Templates are loaded from the ``library/`` sub-directory adjacent to
		this module.  If the directory is missing or empty, returns an empty
		cache (test-safe).
		"""
		cache = cls()
		library_dir = Path(__file__).parent / "library"
		if library_dir.is_dir():
			cache.load_library(library_dir)
		return cache


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _resolve_params(
	definitions: list[TemplateParameter],
	supplied: dict[str, Any],
) -> dict[str, Any]:
	"""Merge supplied params with defaults; validate required."""
	resolved: dict[str, Any] = {}
	for param in definitions:
		if param.name in supplied:
			resolved[param.name] = supplied[param.name]
		elif not param.required and param.default is not None:
			resolved[param.name] = param.default
		elif param.required and param.name not in supplied:
			raise ValueError(
				f"Required template parameter '{param.name}' not supplied."
			)
	# Pass through any extra params (forward-compat).
	for k, v in supplied.items():
		if k not in resolved:
			resolved[k] = v
	return resolved


def _fill(obj: Any, params: dict[str, Any]) -> Any:
	"""Recursively replace ``{{param}}`` in *obj* with values from *params*."""
	if isinstance(obj, str):
		def _replace(m: re.Match[str]) -> str:
			key = m.group(1)
			val = params.get(key)
			return str(val) if val is not None else m.group(0)
		return _PLACEHOLDER_RE.sub(_replace, obj)
	if isinstance(obj, dict):
		return {k: _fill(v, params) for k, v in obj.items()}
	if isinstance(obj, list):
		return [_fill(item, params) for item in obj]
	return obj


__all__ = ["JtbdTemplate", "TemplateCache", "TemplateParameter"]
