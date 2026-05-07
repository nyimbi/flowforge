"""E-49 / E-50 / E-51 — domain pkg hygiene regression tests.

Audit reference: framework/docs/audit-fix-plan.md §7 E-49, E-50, E-51,
findings D-03, D-04, D-05.

For each of the 30 ``flowforge-jtbd-<X>`` domain packages (excluding
``flowforge-jtbd-hub``):

- **E-50 / D-05** — ``[project] version = "0.0.1"`` (semver clarity:
  scaffolds and starter content are not 1.0.0).
- **E-51 / D-03** — ``__init__.py`` exposes ``load_bundle()`` plus an
  explicit ``__all__``. The bundle loader must read
  ``examples/bundle.yaml`` from package resources via ``importlib.resources``.
- **E-49 / D-04** — ``tests/test_smoke.py`` exists and exercises
  ``load_bundle()``.

Each top-level acceptance test (``test_D_05``, ``test_D_03``,
``test_D_04``) iterates over every domain pkg, so a regression in any
one pkg is a single failure with a clear message.
"""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PYTHON_DIR = _REPO_ROOT / "framework" / "python"


def _domain_pkgs() -> list[str]:
	pkgs = sorted(
		p.name
		for p in _PYTHON_DIR.iterdir()
		if p.is_dir()
		and p.name.startswith("flowforge-jtbd-")
		and p.name != "flowforge-jtbd-hub"
	)
	assert len(pkgs) == 30, f"expected 30 domain pkgs, got {len(pkgs)}"
	return pkgs


def _module_name(pkg_dir: str) -> str:
	# flowforge-jtbd-foo-bar → flowforge_jtbd_foo_bar
	return pkg_dir.replace("-", "_")


# ---------------------------------------------------------------------------
# E-50 / D-05 — version pin
# ---------------------------------------------------------------------------


def test_D_05_semver_pin_0_0_1() -> None:
	"""Every domain pkg pyproject.toml has version = 0.0.1."""
	for pkg in _domain_pkgs():
		pyproj = _PYTHON_DIR / pkg / "pyproject.toml"
		with pyproj.open("rb") as f:
			data = tomllib.load(f)
		got = data["project"]["version"]
		assert got == "0.0.1", (
			f"{pkg}/pyproject.toml: version must be '0.0.1' (scaffold tier), got {got!r}"
		)


# ---------------------------------------------------------------------------
# E-51 / D-03 — __init__.py standard
# ---------------------------------------------------------------------------


def _import_pkg(pkg: str):
	"""Import a domain pkg whose ``[tool.uv] package = false`` keeps it off sys.path.

	Adds the pkg's ``src`` dir to ``sys.path`` for the duration of the test
	process and then performs a normal import. Idempotent.
	"""
	src = str(_PYTHON_DIR / pkg / "src")
	if src not in sys.path:
		sys.path.insert(0, src)
	mod_name = _module_name(pkg)
	if mod_name in sys.modules:
		del sys.modules[mod_name]
	return importlib.import_module(mod_name)


def test_D_03_init_load_bundle_and_all() -> None:
	"""Every domain pkg's __init__.py exposes load_bundle() + __all__."""
	for pkg in _domain_pkgs():
		mod = _import_pkg(pkg)
		mod_name = _module_name(pkg)
		assert hasattr(mod, "__all__"), f"{mod_name}: missing __all__"
		assert "load_bundle" in mod.__all__, (
			f"{mod_name}: __all__ does not export 'load_bundle' (got {mod.__all__})"
		)
		assert callable(getattr(mod, "load_bundle", None)), (
			f"{mod_name}: load_bundle is not callable"
		)
		bundle = mod.load_bundle()
		assert isinstance(bundle, dict), (
			f"{mod_name}: load_bundle() must return a dict (got {type(bundle).__name__})"
		)
		# The bundle yaml has top-level keys ``project``, ``shared``, ``jtbds``.
		for key in ("project", "jtbds"):
			assert key in bundle, (
				f"{mod_name}: bundle missing top-level key {key!r}"
			)


# ---------------------------------------------------------------------------
# E-49 / D-04 — per-domain smoke test exists and passes
# ---------------------------------------------------------------------------


def test_D_04_smoke_test_per_pkg_exists() -> None:
	"""Every domain pkg ships ``tests/test_smoke.py``."""
	for pkg in _domain_pkgs():
		smoke = _PYTHON_DIR / pkg / "tests" / "test_smoke.py"
		assert smoke.is_file(), f"{pkg}/tests/test_smoke.py missing"


def test_D_04_smoke_loads_bundle_for_each_pkg() -> None:
	"""Smoke-equivalent: every pkg's load_bundle() round-trips.

	Mirrors what each per-pkg test_smoke.py does, executed once here so
	a bundle-shape regression in one pkg shows up as a single failure
	in the audit-2026 macro target without iterating every per-pkg pytest.
	"""
	for pkg in _domain_pkgs():
		mod = _import_pkg(pkg)
		bundle = mod.load_bundle()
		jtbds = bundle.get("jtbds") or []
		assert jtbds, f"{pkg}: bundle.jtbds is empty"
		for entry in jtbds:
			assert "id" in entry and "version" in entry, (
				f"{pkg}: bundle.jtbds entry missing id/version: {entry}"
			)
