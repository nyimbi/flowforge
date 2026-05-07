"""E-46 — Workspace + docs alignment regression tests (DOC-01, DOC-02).

Audit findings (audit-fix-plan §4.x DOC-01/DOC-02, §7 E-46, §2 F-5):

- **DOC-01 (P1)** — every Python package under ``framework/python/`` is
  registered in the root ``[tool.uv.workspace]``. F-5 mitigation: register
  in two steps — first as ``package=false`` build-only members, then flip
  to ``package=true`` per pkg as it's reviewed.
- **DOC-02 (P2)** — ``framework/README.md`` package count matches the
  filesystem (no drift like "12 PyPI packages" while there are 45).
- **DOC-02 (P2)** — ``framework/docs/flowforge-evolution.md`` paths match
  the actual layout (no ``apps/jtbd-hub/`` artefacts; the package lives
  at ``framework/python/flowforge-jtbd-hub/``).

Plan reference: framework/docs/audit-fix-plan.md §7 E-46, §2 F-5.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRAMEWORK = _REPO_ROOT / "framework"
_PYTHON_DIR = _FRAMEWORK / "python"
_ROOT_PYPROJECT = _FRAMEWORK / "pyproject.toml"
_README = _FRAMEWORK / "README.md"
_EVOLUTION = _FRAMEWORK / "docs" / "flowforge-evolution.md"


def _list_python_packages() -> list[str]:
	return sorted(p.name for p in _PYTHON_DIR.iterdir() if p.is_dir())


def _load_root_pyproject() -> dict:
	with _ROOT_PYPROJECT.open("rb") as f:
		return tomllib.load(f)


# ---------------------------------------------------------------------------
# DOC-01 — workspace registration
# ---------------------------------------------------------------------------


def test_DOC_01_workspace_complete() -> None:
	"""Every package directory under framework/python is in the workspace members."""
	cfg = _load_root_pyproject()
	members = cfg.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
	registered = {m.removeprefix("python/") for m in members if m.startswith("python/")}

	on_disk = set(_list_python_packages())
	missing = on_disk - registered
	extras = registered - on_disk
	assert not missing, f"workspace missing packages: {sorted(missing)}"
	assert not extras, f"workspace lists nonexistent packages: {sorted(extras)}"


def test_DOC_01_unreviewed_pkgs_marked_package_false() -> None:
	"""F-5 mitigation: jtbd-* domain pkgs (except hub) start as ``package=false``.

	The two-step rollout is: (a) add to workspace members with package=false,
	(b) flip to package=true per pkg as it's reviewed (E-48a / E-48b owners).
	"""
	jtbd_starters = sorted(
		p.name
		for p in _PYTHON_DIR.iterdir()
		if p.is_dir() and p.name.startswith("flowforge-jtbd-") and p.name != "flowforge-jtbd-hub"
	)
	# 30 domain packages live under framework/python — every one of them
	# must be present here (regression-detect a sneaky rename).
	assert len(jtbd_starters) == 30, (
		f"expected 30 jtbd domain pkgs, got {len(jtbd_starters)}"
	)
	for pkg in jtbd_starters:
		pyproj = _PYTHON_DIR / pkg / "pyproject.toml"
		assert pyproj.is_file(), f"{pkg} missing pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		uv_section = data.get("tool", {}).get("uv", {})
		# Two-step: package=false now, flip to True per E-48a review.
		assert uv_section.get("package") is False, (
			f"{pkg} is in the workspace but is not marked [tool.uv] package=false; "
			"either review and flip via E-48a, or set package=false."
		)


def test_DOC_01_strategic_pkgs_remain_package_true() -> None:
	"""The 15 originally-registered pkgs keep their default (package=true).

	If any of these flips to ``package=false`` it means a regression in the
	build pipeline — they ship today and must continue to do so.
	"""
	strategic = {
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
	}
	for pkg in strategic:
		pyproj = _PYTHON_DIR / pkg / "pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		# package may be unset (default True) or explicitly True.
		uv_section = data.get("tool", {}).get("uv", {})
		assert uv_section.get("package", True) is True, (
			f"strategic pkg {pkg} is marked package=false — should ship as a real distribution"
		)


# ---------------------------------------------------------------------------
# DOC-02 — README + handbook accuracy
# ---------------------------------------------------------------------------


def test_DOC_02_readme_pkg_count_matches_filesystem() -> None:
	"""``framework/README.md`` must reference 45 (not the stale 12)."""
	text = _README.read_text(encoding="utf-8")
	on_disk = len(_list_python_packages())
	assert on_disk == 45, f"unexpected package count on disk: {on_disk}"
	# Reject the historical "12" claim outright.
	assert not re.search(r"\b12\s+(PyPI\s+)?packages\b", text, re.IGNORECASE), (
		"README still claims '12 PyPI packages' — update to 45"
	)
	# Positive: the README mentions the real total.
	assert re.search(r"\b45\b", text), "README does not reference the real 45-package total"


def test_DOC_02_handbook_path_drift_fixed() -> None:
	"""``docs/flowforge-evolution.md`` no longer references ``apps/jtbd-hub/``."""
	text = _EVOLUTION.read_text(encoding="utf-8")
	# The pkg lives at framework/python/flowforge-jtbd-hub/; ``apps/jtbd-hub/``
	# was a pre-rebrand path that no longer exists.
	bad_paths = re.findall(r"apps/jtbd[\w/.-]*", text)
	assert not bad_paths, (
		f"docs/flowforge-evolution.md still references stale ``apps/jtbd-*`` paths: {bad_paths}"
	)
