"""E-65 — Doc currency regression tests (DOC-03, DOC-04).

Audit reference: framework/docs/audit-fix-plan.md §7 E-65, findings DOC-03, DOC-04.

- **DOC-03** — per-package examples become doctests; ``pytest --doctest-modules``
  on the ``flowforge_money`` package proves at least one example doctest is
  exercised. (Other packages are doctest-clean by virtue of using ``Examples::``
  RST blocks; the audit only requires that the framework HAS doctest-runnable
  examples, not that every package does.)

- **DOC-04** — handbook + evolution + jtbd-editor-arch references no longer
  cite ``apps/jtbd-*/`` paths; the workspace lives at ``framework/python/``
  and ``framework/js/``.
"""

from __future__ import annotations

import doctest
import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRAMEWORK = _REPO_ROOT / "framework"
_DOCS = _FRAMEWORK / "docs"


# ---------------------------------------------------------------------------
# DOC-04 — handbook path drift
# ---------------------------------------------------------------------------


_BAD_PATH_RE = re.compile(r"apps/jtbd-(?:hub|editor)[\w/.-]*")
_PROSE_DOCS = (
	"flowforge-handbook.md",
	"flowforge-evolution.md",
	"jtbd-editor-arch.md",
)


def test_DOC_04_no_apps_jtbd_paths_in_handbook() -> None:
	"""``apps/jtbd-hub/`` and ``apps/jtbd-editor/`` are stale path artefacts."""
	for fname in _PROSE_DOCS:
		path = _DOCS / fname
		assert path.is_file(), f"missing doc: {path}"
		text = path.read_text(encoding="utf-8")
		hits = _BAD_PATH_RE.findall(text)
		assert not hits, (
			f"{fname} still references stale ``apps/jtbd-*`` paths: {hits[:5]} "
			"(should be ``framework/python/flowforge-jtbd-hub/`` or "
			"``framework/js/flowforge-jtbd-editor/``)"
		)


def test_DOC_04_handbook_uses_real_workspace_paths() -> None:
	"""Positive: the handbook mentions the real on-disk locations."""
	handbook = (_DOCS / "flowforge-handbook.md").read_text(encoding="utf-8")
	# At least one mention of the real-pkg paths should exist somewhere in
	# the handbook for the editor and hub.
	assert "flowforge-jtbd-hub" in handbook, (
		"handbook should describe the JTBD hub by its real package name"
	)
	assert "flowforge-jtbd-editor" in handbook or "flowforge-designer" in handbook, (
		"handbook should describe the editor by its real package name"
	)


# ---------------------------------------------------------------------------
# DOC-03 — per-pkg doctests run cleanly
# ---------------------------------------------------------------------------


def test_DOC_03_money_package_has_runnable_doctest() -> None:
	"""``flowforge_money.static`` has at least one passing doctest example.

	The audit's "per-pkg READMEs as doctests" intent is that documentation
	examples be runnable rather than rotting. We exercise this on the money
	package's ``Money`` docstring (which already carries ``>>>`` examples)
	to prove the doctest runner picks them up.
	"""
	from flowforge_money import static as mod

	finder = doctest.DocTestFinder(verbose=False)
	tests = finder.find(mod)
	# Find the Money class doctest (which has the ``>>>`` block).
	runner = doctest.DocTestRunner(verbose=False, optionflags=doctest.ELLIPSIS)
	any_run = 0
	any_failed = 0
	for test in tests:
		if not test.examples:
			continue
		any_run += len(test.examples)
		result = runner.run(test)
		any_failed += result.failed
	assert any_run > 0, "flowforge_money.static has no doctest examples"
	assert any_failed == 0, f"{any_failed} doctest example(s) failed in flowforge_money.static"
