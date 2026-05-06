"""Disk loaders for ``i18n/<lang>.json`` catalogs.

Library packs ship their localisation as flat JSON files under
``i18n/<lang>.json`` (per arch §9.4). The loaders here return
:class:`LocaleCatalog` instances ready to drop into a
:class:`LocaleRegistry`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .catalog import LocaleCatalog


_LANG_FILE_RE = re.compile(r"^([a-zA-Z]{2,3}(?:[-_][A-Za-z0-9]+)?)\.json$")


class CatalogLoadError(RuntimeError):
	"""Raised when a catalog file cannot be read or parsed."""


def load_catalog_from_path(path: Path | str, *, lang: str | None = None) -> LocaleCatalog:
	"""Load one catalog from a JSON file.

	The language code defaults to the file stem (``en.json`` → ``en``).
	Pass *lang* explicitly to override.
	"""
	p = Path(path)
	if not p.exists() or not p.is_file():
		raise CatalogLoadError(f"catalog not found: {p}")
	if lang is None:
		match = _LANG_FILE_RE.match(p.name)
		if match is None:
			raise CatalogLoadError(
				f"could not derive language from {p.name!r}; pass lang=…",
			)
		lang = match.group(1)
	try:
		raw = json.loads(p.read_text(encoding="utf-8"))
	except json.JSONDecodeError as exc:
		raise CatalogLoadError(f"{p}: {exc}") from exc
	if not isinstance(raw, dict):
		raise CatalogLoadError(
			f"{p}: top-level must be an object, got {type(raw).__name__}",
		)
	for key, value in raw.items():
		if not isinstance(key, str):
			raise CatalogLoadError(f"{p}: non-string key {key!r}")
		if not isinstance(value, str):
			raise CatalogLoadError(
				f"{p}: value for {key!r} must be a string, got "
				f"{type(value).__name__}",
			)
	return LocaleCatalog(lang=lang, entries=raw)


def load_catalog_from_dir(directory: Path | str) -> dict[str, LocaleCatalog]:
	"""Scan *directory* for ``<lang>.json`` files and load each.

	Files whose name does not match the ``<lang>(.json)`` shape are
	skipped silently — sibling fixtures and notes are common in
	library packs.
	"""
	root = Path(directory)
	if not root.exists() or not root.is_dir():
		raise CatalogLoadError(f"catalog directory not found: {root}")
	out: dict[str, LocaleCatalog] = {}
	for entry in sorted(root.iterdir()):
		if not entry.is_file():
			continue
		match = _LANG_FILE_RE.match(entry.name)
		if match is None:
			continue
		out[match.group(1)] = load_catalog_from_path(entry)
	return out


__all__ = [
	"CatalogLoadError",
	"load_catalog_from_dir",
	"load_catalog_from_path",
]
