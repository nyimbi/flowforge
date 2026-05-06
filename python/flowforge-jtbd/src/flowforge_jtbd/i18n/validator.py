"""Catalog ↔ spec validator.

Two failure modes:

* ``unknown_path`` (error) — catalog declares a key the spec cannot
  resolve to any real field. Often a stale translation after a field
  was renamed / dropped.
* ``missing_translation`` (warning) — spec declares a translatable
  field the catalog does not cover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .catalog import LocaleCatalog
from .keys import keys_for_spec


Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class I18nIssue:
	"""One catalog ↔ spec mismatch."""

	severity: Severity
	rule: Literal["unknown_path", "missing_translation"]
	key: str
	jtbd_id: str
	message: str


@dataclass
class I18nValidationResult:
	"""Aggregated validator output for one (spec set × catalog) pair."""

	lang: str
	issues: list[I18nIssue] = field(default_factory=list)

	@property
	def ok(self) -> bool:
		return all(issue.severity != "error" for issue in self.issues)

	def errors(self) -> list[I18nIssue]:
		return [i for i in self.issues if i.severity == "error"]

	def warnings(self) -> list[I18nIssue]:
		return [i for i in self.issues if i.severity == "warning"]


def _spec_jtbd_id(spec: Any) -> str:
	if isinstance(spec, dict):
		return spec.get("id") or spec.get("jtbd_id") or "<unknown>"
	for attr in ("id", "jtbd_id"):
		value = getattr(spec, attr, None)
		if isinstance(value, str) and value:
			return value
	return "<unknown>"


def validate_catalog(
	specs: Iterable[Any],
	catalog: LocaleCatalog,
) -> I18nValidationResult:
	"""Cross-check *catalog* against *specs*.

	Errors when the catalog points at a path no spec can resolve;
	warnings when a spec declares a translatable field the catalog
	does not cover. Both shapes carry the offending key + the
	owning ``jtbd_id`` so the editor can deep-link.
	"""
	specs_list = list(specs)
	# Pre-compute the union of all expected keys + a per-key owner map.
	expected: set[str] = set()
	owner: dict[str, str] = {}
	for spec in specs_list:
		jtbd_id = _spec_jtbd_id(spec)
		for key in keys_for_spec(spec):
			expected.add(key)
			owner[key] = jtbd_id

	result = I18nValidationResult(lang=catalog.lang)

	# Errors: keys present in the catalog but not derivable from any
	# spec.
	for key in sorted(catalog.entries):
		if key in expected:
			continue
		result.issues.append(I18nIssue(
			severity="error",
			rule="unknown_path",
			key=key,
			jtbd_id=key.split(".", 1)[0],
			message=(
				f"catalog key {key!r} does not correspond to any field "
				f"on a JTBD in this bundle"
			),
		))

	# Warnings: keys derivable from specs but absent from the catalog.
	for key in sorted(expected - set(catalog.entries)):
		result.issues.append(I18nIssue(
			severity="warning",
			rule="missing_translation",
			key=key,
			jtbd_id=owner[key],
			message=(
				f"catalog {catalog.lang!r} is missing translation for "
				f"{key!r}"
			),
		))

	return result


__all__ = [
	"I18nIssue",
	"I18nValidationResult",
	"Severity",
	"validate_catalog",
]
