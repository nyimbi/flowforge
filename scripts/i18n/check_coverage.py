#!/usr/bin/env python3
"""i18n coverage gate (v0.3.0 W4b / item 17 of docs/improvements.md).

Walks every example bundle under :file:`examples/`, regenerates the
per-bundle i18n catalogs in memory, and asserts:

* For each JTBD declaring ``compliance: [...]``, every non-English
  catalog has *no empty values* for keys scoped to that JTBD. Empty
  values for compliance-tagged JTBDs are a hard error (exit 1).
* For other JTBDs, empty values are reported as warnings (exit 0).

This gate enforces the W4b acceptance criterion ("no untranslated
strings in ``compliance:`` JTBDs"). The script is invoked from
``make audit-2026-i18n-coverage``; CI calls the Make target.

Usage::

	uv run python scripts/i18n/check_coverage.py [--examples-dir DIR]

Exit codes:

* ``0`` — no errors (warnings may be present)
* ``1`` — at least one compliance-tagged JTBD has untranslated strings
* ``2`` — runtime error (invalid bundle, generator crash, etc.)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make ``flowforge_cli`` importable when this script is run via
# ``uv run python scripts/i18n/check_coverage.py``; ``uv run`` already
# resolves the workspace, but the explicit import path keeps the
# script runnable standalone for debugging.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_generator() -> tuple[Any, Any]:
	"""Lazy-import the i18n generator so this script fails clearly if the
	workspace is not synced (``uv sync`` not run yet)."""

	from flowforge_cli.jtbd.normalize import normalize as _normalize  # noqa: PLC0415
	from flowforge_cli.jtbd.generators import i18n as _i18n  # noqa: PLC0415

	return _normalize, _i18n


def _key_jtbd(key: str) -> str | None:
	"""Return the JTBD id this key is scoped to, or ``None``.

	* ``jtbd.<id>.…`` → ``<id>``
	* ``audit.<id>.…`` → ``<id>`` (audit topics are scoped to a JTBD by
	  dotted prefix; this is the inverse of
	  :func:`flowforge_cli.jtbd.transforms.derive_audit_topics`).
	* anything else → ``None``
	"""

	parts = key.split(".")
	if len(parts) < 2:
		return None
	if parts[0] == "jtbd":
		return parts[1]
	if parts[0] == "audit":
		# audit.<jtbd_id>.<verb>; verb may itself contain underscores.
		return parts[1]
	return None


def _check_bundle(bundle_path: Path) -> tuple[int, int]:
	"""Return ``(error_count, warning_count)`` for *bundle_path*."""

	normalize_fn, i18n_mod = _load_generator()
	raw = json.loads(bundle_path.read_text(encoding="utf-8"))
	norm = normalize_fn(raw)
	files = i18n_mod.generate(norm)
	# Map {lang: catalog} — useT.ts is the TS hook, skipped here.
	catalogs: dict[str, dict[str, str]] = {}
	for f in files:
		if not f.path.endswith(".json"):
			continue
		# .../i18n/<lang>.json
		lang = Path(f.path).stem
		catalogs[lang] = json.loads(f.content)
	compliance_jtbds: set[str] = {j.id for j in norm.jtbds if j.compliance}
	errors = 0
	warnings = 0
	# English is the source of truth; lint targets are every other lang.
	english_lang = (norm.project.languages or ("en",))[0]
	for lang in sorted(catalogs.keys()):
		if lang == english_lang:
			continue
		cat = catalogs[lang]
		for key in sorted(cat.keys()):
			if cat[key] != "":
				continue
			jtbd_id = _key_jtbd(key)
			if jtbd_id is not None and jtbd_id in compliance_jtbds:
				print(
					f"ERROR  {bundle_path.parent.name}/{lang}.json: "
					f"untranslated key '{key}' "
					f"(JTBD '{jtbd_id}' declares compliance:)",
					file=sys.stderr,
				)
				errors += 1
			else:
				print(
					f"WARN   {bundle_path.parent.name}/{lang}.json: "
					f"untranslated key '{key}'"
					+ (f" (JTBD '{jtbd_id}')" if jtbd_id else ""),
					file=sys.stderr,
				)
				warnings += 1
	return errors, warnings


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="i18n coverage gate")
	parser.add_argument(
		"--examples-dir",
		type=Path,
		default=_REPO_ROOT / "examples",
		help="Directory containing example bundles (default: <repo>/examples)",
	)
	args = parser.parse_args(argv)
	examples_dir: Path = args.examples_dir
	if not examples_dir.is_dir():
		print(f"i18n coverage gate: examples dir not found: {examples_dir}", file=sys.stderr)
		return 2
	total_errors = 0
	total_warnings = 0
	checked = 0
	for ex_dir in sorted(examples_dir.iterdir()):
		bundle = ex_dir / "jtbd-bundle.json"
		if not bundle.is_file():
			continue
		try:
			errors, warnings = _check_bundle(bundle)
		except Exception as exc:  # noqa: BLE001
			print(f"i18n coverage gate: failed on {bundle}: {exc!r}", file=sys.stderr)
			return 2
		total_errors += errors
		total_warnings += warnings
		checked += 1
	if total_errors:
		print(
			f"i18n coverage gate FAILED: {total_errors} error(s), "
			f"{total_warnings} warning(s) across {checked} example(s)",
			file=sys.stderr,
		)
		return 1
	print(
		f"i18n coverage gate passed: 0 error(s), {total_warnings} warning(s) "
		f"across {checked} example(s)"
	)
	return 0


if __name__ == "__main__":
	sys.exit(main())
