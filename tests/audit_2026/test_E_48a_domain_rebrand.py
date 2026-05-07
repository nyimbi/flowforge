"""E-48a — Domain rebrand regression tests (D-01, 25/30 pkgs).

Audit reference: framework/docs/audit-fix-plan.md §7 E-48a, §4.x D-01.

The 25 non-strategic JTBD domain packages must be renamed to
``flowforge-jtbd-<X>-starter`` with:

- ``[project] name = "flowforge-jtbd-<X>-starter"``
- ``Development Status :: 1 - Planning`` and a ``scaffold-only`` keyword
  in classifiers / keywords (the "lint badge")
- README disclaimer at the top: "Starter scaffold. ..."

Strategic 5 (insurance, healthcare, banking, gov, hr) are excluded —
those carry real content via E-48b.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PYTHON_DIR = _REPO_ROOT / "framework" / "python"

# Strategic verticals carry real JTBD content; they keep their original name.
_STRATEGIC = frozenset({
	"flowforge-jtbd-insurance",
	"flowforge-jtbd-healthcare",
	"flowforge-jtbd-banking",
	"flowforge-jtbd-gov",
	"flowforge-jtbd-hr",
})


def _starter_pkgs() -> list[str]:
	pkgs = sorted(
		p.name
		for p in _PYTHON_DIR.iterdir()
		if p.is_dir()
		and p.name.startswith("flowforge-jtbd-")
		and p.name != "flowforge-jtbd-hub"
		and p.name not in _STRATEGIC
	)
	# Sanity: 30 total - 5 strategic - 0 hub = 25 starters.
	assert len(pkgs) == 25, f"expected 25 starter pkgs, got {len(pkgs)}: {pkgs}"
	return pkgs


def test_D_01_starter_pkgs_renamed() -> None:
	"""Every non-strategic domain pkg has ``name = flowforge-jtbd-<X>-starter``."""
	for pkg_dir_name in _starter_pkgs():
		pyproj = _PYTHON_DIR / pkg_dir_name / "pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		got = data["project"]["name"]
		expected = f"{pkg_dir_name}-starter"
		assert got == expected, (
			f"{pkg_dir_name}/pyproject.toml: expected name={expected!r}, got {got!r}"
		)


def test_D_01_starter_pkgs_have_scaffold_classifier() -> None:
	"""Each starter pkg carries a ``scaffold-only`` lint badge."""
	for pkg_dir_name in _starter_pkgs():
		pyproj = _PYTHON_DIR / pkg_dir_name / "pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		project = data["project"]
		classifiers = project.get("classifiers", [])
		keywords = project.get("keywords", [])
		# Either keyword or classifier hits.
		has_badge = (
			any("scaffold-only" in str(c).lower() for c in classifiers)
			or "scaffold-only" in keywords
		)
		assert has_badge, (
			f"{pkg_dir_name}/pyproject.toml: missing 'scaffold-only' lint badge "
			"in classifiers or keywords"
		)
		# Status classifier — Planning (1) for scaffolds.
		has_planning = any(
			"Development Status :: 1 - Planning" == str(c) for c in classifiers
		)
		assert has_planning, (
			f"{pkg_dir_name}/pyproject.toml: missing 'Development Status :: 1 - Planning' classifier"
		)


def test_D_01_starter_readme_carries_disclaimer() -> None:
	"""Each starter pkg's README starts with the audit-mandated disclaimer."""
	expected_phrase = "Starter scaffold"
	for pkg_dir_name in _starter_pkgs():
		readme = _PYTHON_DIR / pkg_dir_name / "README.md"
		assert readme.is_file(), f"{pkg_dir_name}/README.md missing"
		text = readme.read_text(encoding="utf-8")
		# Disclaimer must appear in the top 2 KiB so it's the first thing readers see.
		head = text[:2048]
		assert expected_phrase in head, (
			f"{pkg_dir_name}/README.md: missing 'Starter scaffold' disclaimer in first 2KB"
		)


def test_D_01_strategic_pkgs_keep_original_name() -> None:
	"""The 5 strategic verticals must NOT be renamed to ``-starter``."""
	for pkg in _STRATEGIC:
		pyproj = _PYTHON_DIR / pkg / "pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		got = data["project"]["name"]
		assert got == pkg, (
			f"strategic pkg {pkg} was incorrectly rebranded to {got!r}"
		)
		assert not got.endswith("-starter"), (
			f"strategic pkg {pkg} must not be a starter"
		)
