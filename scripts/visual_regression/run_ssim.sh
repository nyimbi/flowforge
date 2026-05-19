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
if [[ "${UPDATE_BASELINES:-}" != "1" ]]; then
	if ! find "$REPO_ROOT/examples" -path "*/screenshots/*/*.png" -type f | grep -q .; then
		skip "pixel baselines are not checked in yet — run with UPDATE_BASELINES=1 after Playwright can launch Chromium."
	fi
fi

HARNESS_PID=""
HARNESS_LOG=""
HARNESS_URL_FILE=""
cleanup() {
	if [[ -n "$HARNESS_PID" ]] && kill -0 "$HARNESS_PID" >/dev/null 2>&1; then
		kill "$HARNESS_PID" >/dev/null 2>&1 || true
		wait "$HARNESS_PID" >/dev/null 2>&1 || true
	fi
	[[ -n "$HARNESS_LOG" ]] && rm -f "$HARNESS_LOG"
	[[ -n "$HARNESS_URL_FILE" ]] && rm -f "$HARNESS_URL_FILE"
}
trap cleanup EXIT

if [[ -z "${VISREG_DEV_SERVER_URL:-}" ]]; then
	if ! (cd "$VISREG_DIR" && node -e "import('vite')" >/dev/null 2>&1); then
		skip "vite is not installed in tests/visual_regression/node_modules — run pnpm install in tests/visual_regression."
	fi
	HARNESS_URL_FILE="$(mktemp)"
	HARNESS_LOG="$(mktemp)"
	(
		cd "$VISREG_DIR"
		node "$VISREG_DIR/harness/start-dev-server.mjs" "$HARNESS_URL_FILE"
	) >"$HARNESS_LOG" 2>&1 &
	HARNESS_PID="$!"
	for _ in {1..100}; do
		if [[ -s "$HARNESS_URL_FILE" ]]; then
			VISREG_DEV_SERVER_URL="$(cat "$HARNESS_URL_FILE")"
			export VISREG_DEV_SERVER_URL
			echo "    harness: $VISREG_DEV_SERVER_URL"
			break
		fi
		if ! kill -0 "$HARNESS_PID" >/dev/null 2>&1; then
			cat "$HARNESS_LOG" >&2
			echo "[FAIL] visual-regression harness failed to start" >&2
			exit 1
		fi
		sleep 0.1
	done
	if [[ -z "${VISREG_DEV_SERVER_URL:-}" ]]; then
		cat "$HARNESS_LOG" >&2
		echo "[FAIL] visual-regression harness did not report a URL" >&2
		exit 1
	fi
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
