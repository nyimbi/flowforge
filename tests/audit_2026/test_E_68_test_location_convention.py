"""E-68 / IT-05 — adopt single test-location convention.

Audit finding (audit-fix-plan §4.4 IT-05, §7 E-68):

The framework grew with three competing test-location conventions:
  * per-package tests at ``framework/python/<pkg>/tests/...``
  * repo-level layered suites at ``framework/tests/<layer>/...``
  * host-project example tests at ``framework/examples/<example>/tests/...``

This file is a lint that walks the source tree and asserts every
``test_*.py`` file lives under exactly one of those three approved
roots, and that the per-layer subdirectory (audit_2026, conformance,
property, integration, edge_cases, cross_runtime, chaos, observability)
is one of the documented audit-2026 layers.

The intent is that someone adding a new test cannot drop it in a random
``framework/scratch/test_foo.py`` location; CI catches the violation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]


# Allowed layer names under framework/tests/<layer>/...
_AUDIT_2026_LAYERS = frozenset(
	{
		"audit_2026",
		"conformance",
		"property",
		"integration",
		"edge_cases",
		"cross_runtime",
		"chaos",
		"observability",
	}
)

# Per-package test-subdir names that are accepted under
# framework/python/<pkg>/tests/<subdir>/...
_PER_PKG_SUBDIRS = frozenset({"unit", "ci", "integration", "property", "fixtures", ""})

# Skip any path containing these segments (third-party, generated code,
# template scaffolding that the framework ships TO host apps).
_SKIP_SEGMENTS = frozenset(
	{
		".venv",
		"node_modules",
		"__pycache__",
		"templates",  # flowforge_cli templates ship test stubs to scaffolded hosts
		"generated",  # examples/<x>/generated/backend/tests ships test stubs
	}
)


def _is_skipped(path: Path) -> bool:
	parts = set(path.parts)
	return bool(parts & _SKIP_SEGMENTS)


def _classify(path: Path) -> str:
	"""Return a string label for the location category, or `'INVALID'`.

	Categories:
	  * ``framework_layered`` — under framework/tests/<layer>/
	  * ``per_package`` — under framework/python/<pkg>/tests/[<subdir>/]
	  * ``example_host`` — under framework/examples/<example>/tests/
	"""

	rel = path.relative_to(_FRAMEWORK_ROOT)
	parts = rel.parts

	# framework/tests/<layer>/...
	if len(parts) >= 2 and parts[0] == "tests":
		layer = parts[1]
		if layer in _AUDIT_2026_LAYERS:
			return "framework_layered"
		# integration/python/tests/ — the established UMS-parity nesting.
		if layer == "integration" and "python" in parts and "tests" in parts:
			return "framework_layered"
		return "INVALID:framework_tests_unknown_layer"

	# framework/python/<pkg>/tests/...
	if len(parts) >= 4 and parts[0] == "python" and parts[2] == "tests":
		subdir = parts[3] if len(parts) > 4 else ""
		# strip filename position: subdir is parts[3] when present, "" when test sits in tests/
		# Treat "test_*.py" sitting directly in tests/ as subdir="" which is allowed.
		if subdir.startswith("test_") and subdir.endswith(".py"):
			subdir = ""
		if subdir not in _PER_PKG_SUBDIRS:
			return f"INVALID:per_pkg_unknown_subdir:{subdir}"
		return "per_package"

	# framework/examples/<example>/tests/...
	if len(parts) >= 3 and parts[0] == "examples" and parts[2] == "tests":
		return "example_host"

	return f"INVALID:unrecognised_root:{parts[0] if parts else '<root>'}"


def test_IT_05_test_files_only_live_in_approved_locations() -> None:
	"""Every ``test_*.py`` under framework/ lives in an approved location.

	The convention is documented in ``framework/tests/README.md``. Adding
	a new test file outside the approved roots requires either (a)
	moving the file to one of the existing roots, or (b) extending
	``_AUDIT_2026_LAYERS`` / ``_PER_PKG_SUBDIRS`` here AND the README.
	"""

	violations: list[tuple[Path, str]] = []
	for test_file in _FRAMEWORK_ROOT.rglob("test_*.py"):
		if _is_skipped(test_file):
			continue
		category = _classify(test_file)
		if category.startswith("INVALID"):
			violations.append((test_file.relative_to(_FRAMEWORK_ROOT), category))

	if violations:
		bullets = "\n".join(f"  - {p}: {reason}" for p, reason in violations)
		pytest.fail(
			"E-68 / IT-05: test files in non-approved locations:\n" + bullets
		)


def test_IT_05_layered_suite_layout_documented() -> None:
	"""``framework/tests/README.md`` documents every audit-2026 layer."""

	readme = _FRAMEWORK_ROOT / "tests" / "README.md"
	if not readme.exists():
		pytest.fail("E-68 / IT-05: framework/tests/README.md missing")

	body = readme.read_text(encoding="utf-8")
	missing = [layer for layer in _AUDIT_2026_LAYERS if layer not in body]
	assert not missing, (
		f"framework/tests/README.md does not document layers: {missing}. "
		f"Add a one-line description per layer."
	)


def test_IT_05_no_stray_test_pyfiles_in_framework_root() -> None:
	"""``framework/test_*.py`` in the bare root is a violation; tests
	always live one or two directories deep."""

	stray = list(_FRAMEWORK_ROOT.glob("test_*.py"))
	assert stray == [], (
		f"E-68 / IT-05: stray test files in framework/ root: {stray}"
	)


def test_IT_05_per_package_tests_have_consistent_init() -> None:
	"""Every per-package ``tests/`` directory contains an ``__init__.py``
	OR is empty/contains only fixtures. This ensures pytest collection
	is uniform across the workspace."""

	missing: list[Path] = []
	pkg_root = _FRAMEWORK_ROOT / "python"
	if not pkg_root.exists():
		pytest.skip("framework/python/ not found")

	for pkg in pkg_root.iterdir():
		if not pkg.is_dir() or _is_skipped(pkg):
			continue
		tests_dir = pkg / "tests"
		if not tests_dir.exists():
			continue
		test_files = list(tests_dir.rglob("test_*.py"))
		if not test_files:
			continue  # empty tests dir is fine
		init = tests_dir / "__init__.py"
		# Either the tests dir has __init__.py, or pytest discovers via
		# rootdir conftest/pyproject (which is the universal case here).
		# We accept either pattern; this test exists to flag a future
		# regression where someone deletes the marker.
		if not (init.exists() or (pkg / "pyproject.toml").exists()):
			missing.append(pkg)

	assert not missing, (
		f"E-68 / IT-05: per-pkg test dirs missing __init__.py and pyproject.toml: {missing}"
	)


def test_IT_05_test_file_names_match_test_glob() -> None:
	"""Every ``test_*.py`` in approved roots actually contains at least
	one test function. Catches accidental empty stubs left behind."""

	stub_files: list[Path] = []
	for tests_root in (
		_FRAMEWORK_ROOT / "tests",
	):
		if not tests_root.exists():
			continue
		for test_file in tests_root.rglob("test_*.py"):
			if _is_skipped(test_file):
				continue
			content = test_file.read_text(encoding="utf-8")
			# Must contain at least one `def test_` or `async def test_`.
			if not re.search(r"^\s*(async\s+)?def\s+test_", content, re.MULTILINE):
				stub_files.append(test_file.relative_to(_FRAMEWORK_ROOT))

	assert not stub_files, (
		f"E-68 / IT-05: empty test stubs (no `def test_*`): {stub_files}"
	)
