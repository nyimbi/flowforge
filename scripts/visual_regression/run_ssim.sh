#!/usr/bin/env bash
# scripts/visual_regression/run_ssim.sh
#
# Advisory wrapper for the pixel-SSIM test (ADR-001 §"Decision" — pixel
# screenshots advisory only, never block PR merge). Always runs the
# *full* suite (every example) because the cadence is nightly per the
# ADR, and there's no PR-time wallclock pressure.
#
# When prerequisites are missing the script SKIPS WITH A CLEAR REASON
# and exits 0 — same skip-path as the DOM gate, plus an additional
# skip when `pngjs` (the SSIM helper's PNG decoder) isn't installed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VISREG_DIR="$REPO_ROOT/tests/visual_regression"

skip() {
	echo "[SKIP] visual-regression-ssim: $*"
	echo "  see tests/visual_regression/README.md for status."
	exit 0
}

if [[ ! -d "$VISREG_DIR" ]]; then
	echo "[FAIL] tests/visual_regression/ missing — runner deleted?" >&2
	exit 1
fi
if [[ ! -d "$VISREG_DIR/node_modules" ]]; then
	skip "tests/visual_regression/node_modules missing — pnpm install is blocked on the pre-existing pnpm-ignored-builds issue."
fi
if ! "$VISREG_DIR/node_modules/.bin/playwright" --version >/dev/null 2>&1; then
	skip "@playwright/test CLI not on PATH — pnpm install incomplete."
fi
if [[ ! -d "$VISREG_DIR/node_modules/pngjs" ]]; then
	skip "pngjs not installed — SSIM helper cannot decode PNGs. The test specs themselves also skip-with-reason in this case (advisory; not a CI gate)."
fi
if [[ -z "${VISREG_DEV_SERVER_URL:-}" ]]; then
	skip "VISREG_DEV_SERVER_URL not set — dev-server harness deferred until pnpm install is unblocked."
fi

echo "==> visual-regression-ssim (advisory; nightly cadence)"
cd "$VISREG_DIR"
# Advisory: never fail the build. Drop the exit code via `|| true` so
# nightly summaries can pick up annotated SSIM-below-threshold cases
# without breaking the larger pipeline. Per ADR-001 §"Decision" the
# pixel gate posts as a PR comment; it never blocks merge.
VISREG_CADENCE="full" \
	"$VISREG_DIR/node_modules/.bin/playwright" test --project=ssim || {
	echo "[ADVISORY] visual-regression-ssim reported one or more SSIM scores below 0.98."
	echo "  per ADR-001 §\"Decision\" this is advisory only and does NOT fail the build."
	exit 0
}
