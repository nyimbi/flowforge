"""Localisation layer for JTBD specs (E-25).

Per ``framework/docs/flowforge-evolution.md`` §11 and
``framework/docs/jtbd-editor-arch.md`` §9.4 + §23.17.

A locale catalog is a flat ``dict[str, str]`` keyed by
``<jtbd_id>.<jcr_path>`` — the canonical key shape laid out in
arch §23.17:

* ``.title``, ``.situation``, ``.motivation``, ``.outcome``
* ``.fields.<id>.label``, ``.fields.<id>.help``
* ``.edge_cases.<id>.message``
* ``.notifications.<trigger>.subject`` / ``.body``
* ``.success_criteria[<i>]``

Public API:

* :class:`LocaleCatalog` — one language's flat key→string table.
* :class:`LocaleRegistry` — multi-language registry with
  fallback chain (e.g., ``fr`` → ``en``).
* :func:`keys_for_spec` — derives every catalog key from a
  :class:`flowforge_jtbd.dsl.JtbdSpec` (or a plain dict spec).
* :func:`validate_catalog` — surfaces missing-translation warnings
  and unknown-path errors.
* :func:`load_catalog_from_path` — reads ``i18n/<lang>.json`` from
  disk.
"""

from __future__ import annotations

from .catalog import LocaleCatalog, LocaleRegistry
from .keys import keys_for_spec
from .loader import load_catalog_from_dir, load_catalog_from_path
from .validator import I18nIssue, I18nValidationResult, validate_catalog

__all__ = [
	"I18nIssue",
	"I18nValidationResult",
	"LocaleCatalog",
	"LocaleRegistry",
	"keys_for_spec",
	"load_catalog_from_dir",
	"load_catalog_from_path",
	"validate_catalog",
]
