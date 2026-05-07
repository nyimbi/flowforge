"""E-69 — Evolution-doc + version-cadence reconciliation tests.

Audit reference: framework/docs/audit-fix-plan.md §7 E-69.

- **DOC E-31..E-72 reconciliation** — ``framework/docs/flowforge-evolution.md``
  carries an "audit 2026" section that enumerates the audit-fix tickets
  (E-31 through E-72) so a reader of the evolution doc isn't left with
  a sequence gap between E-30 and E-72.
- **DOC-05 / version cadence** — every Python package in the workspace
  follows a documented two-tier policy:
    * **Tier-1 (engine + adapters)**: ``0.1.x`` until the audit-2026
      hardenings sign off.
    * **Tier-2 (domain JTBD libraries)**: ``0.0.1`` for scaffolds /
      starters until they are reviewed and rebranded.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRAMEWORK = _REPO_ROOT / "framework"
_PYTHON_DIR = _FRAMEWORK / "python"
_EVOLUTION = _FRAMEWORK / "docs" / "flowforge-evolution.md"
_ROOT_PYPROJECT = _FRAMEWORK / "pyproject.toml"


# ---------------------------------------------------------------------------
# E-31..E-72 reconciliation
# ---------------------------------------------------------------------------


def test_DOC_E_31_reconciled_listed_in_evolution() -> None:
	"""``flowforge-evolution.md`` enumerates the audit-fix-plan ticket range."""
	text = _EVOLUTION.read_text(encoding="utf-8")
	# Anchor: the new "audit 2026" section header.
	assert re.search(
		r"^##\s.*[Aa]udit[- ]2026", text, flags=re.MULTILINE
	), "evolution doc missing an Audit 2026 section heading"

	# Every audit ticket id (E-32..E-72, plus E-37b and E-48a/b variants)
	# must appear at least once in the section.
	for ticket in (
		"E-32", "E-33", "E-34", "E-35", "E-36", "E-37", "E-37b",
		"E-38", "E-39", "E-40", "E-41", "E-42", "E-43", "E-44",
		"E-45", "E-46", "E-47", "E-48a", "E-48b", "E-49", "E-50",
		"E-51", "E-52", "E-53", "E-54", "E-55", "E-56", "E-57",
		"E-58", "E-59", "E-60", "E-61", "E-62", "E-63", "E-64",
		"E-65", "E-66", "E-67", "E-68", "E-69", "E-70", "E-72",
	):
		assert ticket in text, f"evolution doc missing ticket {ticket}"


# ---------------------------------------------------------------------------
# DOC-05 — version cadence
# ---------------------------------------------------------------------------


_TIER_1: frozenset[str] = frozenset({
	"flowforge-core",
	"flowforge-fastapi",
	"flowforge-sqlalchemy",
	"flowforge-tenancy",
	"flowforge-audit-pg",
	"flowforge-outbox-pg",
	"flowforge-rbac-static",
	"flowforge-rbac-spicedb",
	"flowforge-documents-s3",
	"flowforge-money",
	"flowforge-signing-kms",
	"flowforge-notify-multichannel",
	"flowforge-cli",
	"flowforge-jtbd",
	"flowforge-jtbd-hub",
})


def _tier_for(pkg_dir_name: str) -> str:
	if pkg_dir_name in _TIER_1:
		return "tier-1"
	if pkg_dir_name.startswith("flowforge-jtbd-"):
		return "tier-2"
	raise AssertionError(f"unknown pkg tier for {pkg_dir_name!r}")


def test_DOC_05_versions_consistent_per_tier() -> None:
	"""Every pkg's version matches the cadence policy for its tier."""
	for pkg_dir in sorted(_PYTHON_DIR.iterdir()):
		if not pkg_dir.is_dir():
			continue
		pyproj = pkg_dir / "pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		version = data["project"]["version"]
		tier = _tier_for(pkg_dir.name)
		if tier == "tier-1":
			assert re.match(r"^0\.1\.\d+$", version), (
				f"tier-1 pkg {pkg_dir.name} should be 0.1.x; got {version!r}"
			)
		else:
			assert version == "0.0.1", (
				f"tier-2 pkg {pkg_dir.name} should be 0.0.1; got {version!r}"
			)


def test_DOC_05_cadence_documented_in_root_pyproject() -> None:
	"""Root ``framework/pyproject.toml`` documents the cadence policy in a comment block."""
	text = _ROOT_PYPROJECT.read_text(encoding="utf-8")
	assert "version cadence" in text.lower(), (
		"root pyproject.toml is missing the version-cadence policy header"
	)
	# Both tiers must be named.
	assert "tier-1" in text.lower() or "tier 1" in text.lower(), (
		"root pyproject.toml does not name tier-1 packages"
	)
	assert "tier-2" in text.lower() or "tier 2" in text.lower(), (
		"root pyproject.toml does not name tier-2 packages"
	)
