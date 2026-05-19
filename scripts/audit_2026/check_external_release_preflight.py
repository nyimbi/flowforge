"""Preflight checks for the external release gate."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from check_polish_copy_sidecar import check_sidecar


_DOM_BASELINE_GLOB = "*/screenshots/**/*.dom.html"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _backend_root() -> Path:
	raw = os.environ.get("BACKEND_ROOT")
	if raw:
		return Path(raw)
	return (_REPO_ROOT.parent / "backend").resolve()


def _requires_ums_parity() -> bool:
	return os.environ.get("FLOWFORGE_REQUIRE_UMS_PARITY") == "1"


def collect_issues() -> list[str]:
	issues: list[str] = []
	if os.environ.get("VISREG_ALLOW_SKIP") == "1":
		issues.append("VISREG_ALLOW_SKIP=1 is forbidden for release qualification")
	if os.environ.get("BROWSER_E2E_ALLOW_SKIP") == "1":
		issues.append("BROWSER_E2E_ALLOW_SKIP=1 is forbidden for release qualification")
	if not any((_REPO_ROOT / "examples").glob(_DOM_BASELINE_GLOB)):
		issues.append(
			"DOM baselines are not checked in; run "
			"`UPDATE_BASELINES=1 bash scripts/visual_regression/run_dom_snapshots.sh smoke` "
			"in a Chromium-capable environment"
		)
	sidecar_issue = check_sidecar()
	if sidecar_issue is not None:
		issues.append(sidecar_issue)
	backend_root = _backend_root()
	if _requires_ums_parity() and not backend_root.is_dir():
		issues.append(
			f"BACKEND_ROOT not found at {backend_root}; set BACKEND_ROOT=/path/to/backend "
			"or unset FLOWFORGE_REQUIRE_UMS_PARITY for independent FlowForge release qualification"
		)
	if not (
		os.environ.get("FLOWFORGE_TEST_PG_URL")
		or os.environ.get("FLOWFORGE_LIVE_PG_URL")
	):
		issues.append(
			"set FLOWFORGE_TEST_PG_URL to a disposable Postgres database"
		)
	return issues


def main() -> int:
	issues = collect_issues()
	if issues:
		print("audit-2026-release-external-preflight: blocked", file=sys.stderr)
		for issue in issues:
			print(f"- {issue}", file=sys.stderr)
		return 1
	print(
		"audit-2026-release-external-preflight: ok "
		"(browser execution is verified by make audit-2026-release-external)"
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
