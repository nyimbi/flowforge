#!/usr/bin/env bash
# scripts/visual_regression/run_dom_snapshots.sh
#
# CI-gating wrapper for the DOM-snapshot byte-equality test (ADR-001).
# Wraps `tests/visual_regression`'s Playwright runner and applies the
# scope-cuts that the ADR pins:
#
#   * "smoke"  — canonical example only (per-PR cadence). Default when
#                running on a PR branch.
#   * "full"   — every example (nightly cadence).
#
# When prerequisites are missing (Playwright deps not installed because
# pnpm install is blocked, or the dev-server harness has not yet
# landed), the script SKIPS WITH A CLEAR REASON and exits 0. This is
# explicitly authorised by the W3 task brief: the gate must not fail
# CI on a known-deferred prerequisite. Once worker-tokens lands the
# pnpm cleanup PR + the dev-server harness, the skip path stops
# triggering and the gate becomes live with no further changes here.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VISREG_DIR="$REPO_ROOT/tests/visual_regression"

CADENCE="${1:-smoke}"
case "$CADENCE" in
	smoke|full) ;;
	*)
		echo "[ERROR] cadence must be 'smoke' or 'full' (got '$CADENCE')" >&2
		exit 2
		;;
esac

skip() {
	echo "[SKIP] visual-regression-dom: $*"
	echo "  see tests/visual_regression/README.md for status."
	exit 0
}

# 1. Runner directory must exist (sanity check vs accidental deletion).
if [[ ! -d "$VISREG_DIR" ]]; then
	echo "[FAIL] tests/visual_regression/ missing — runner deleted?" >&2
	exit 1
fi

# 2. pnpm install must have populated node_modules. The Playwright
#    package and `pngjs` are the two we need; both come from
#    `tests/visual_regression/package.json`. Detect the dir; if absent,
#    skip with the canonical reason.
if [[ ! -d "$VISREG_DIR/node_modules" ]]; then
	skip "tests/visual_regression/node_modules missing — pnpm install is blocked on the pre-existing pnpm-ignored-builds issue (worker-tokens / W3 closeout owns the unblock)."
fi

# 3. Playwright browsers must be installed. We don't fail-fast here
#    because Playwright will produce its own "browsers not installed"
#    message; we just route that into a clean skip.
if ! "$VISREG_DIR/node_modules/.bin/playwright" --version >/dev/null 2>&1; then
	skip "@playwright/test CLI not on PATH inside tests/visual_regression/node_modules — pnpm install incomplete."
fi

# 4. Dev-server harness wiring. The harness lands in the follow-up PR
#    once pnpm install is unblocked. Until then, VISREG_DEV_SERVER_URL
#    is unset and the test specs themselves skip-with-reason. We
#    surface that here so the operator sees a single skip line rather
#    than N×3-viewport skipped tests.
if [[ -z "${VISREG_DEV_SERVER_URL:-}" ]]; then
	skip "VISREG_DEV_SERVER_URL not set — dev-server harness deferred until pnpm install is unblocked. The runner is structurally complete; only the harness wiring is missing."
fi

# Everything is in place — run the real suite.
echo "==> visual-regression-dom (cadence=$CADENCE)"
cd "$VISREG_DIR"
VISREG_CADENCE="$CADENCE" \
	"$VISREG_DIR/node_modules/.bin/playwright" test --project=dom
