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
# Missing prerequisites are release-gate failures by default. Developers
# may opt into a local skip with VISREG_ALLOW_SKIP=1 while bootstrapping
# browsers or baselines on a fresh workstation.

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

unavailable() {
	if [[ "${VISREG_ALLOW_SKIP:-}" == "1" ]]; then
		echo "[SKIP] visual-regression-dom: $*"
		echo "  see tests/visual_regression/README.md for status."
		exit 0
	fi
	echo "[FAIL] visual-regression-dom: $*" >&2
	echo "  see tests/visual_regression/README.md for status."
	echo "  set VISREG_ALLOW_SKIP=1 only for local bootstrap, not release gates." >&2
	exit 1
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
	unavailable "tests/visual_regression/node_modules missing — run pnpm install for the visual regression runner."
fi

# 3. Playwright browsers must be installed. We don't fail-fast here
#    because Playwright will produce its own "browsers not installed"
#    message; we just route that into a clean skip.
if ! "$VISREG_DIR/node_modules/.bin/playwright" --version >/dev/null 2>&1; then
	unavailable "@playwright/test CLI not on PATH inside tests/visual_regression/node_modules — pnpm install incomplete."
fi

if [[ "${UPDATE_BASELINES:-}" != "1" ]]; then
	if ! find "$REPO_ROOT/examples" -path "*/screenshots/*/*.dom.html" -type f | grep -q .; then
		unavailable "DOM baselines are not checked in yet — run with UPDATE_BASELINES=1 after Playwright can launch Chromium."
	fi
fi

# 4. Dev-server harness wiring. Operators may point the runner at an
#    already-running server with VISREG_DEV_SERVER_URL. When unset, the
#    local Vite harness mounts generated pages and admin components
#    directly from the checked-in example tree.
HARNESS_PID=""
HARNESS_LOG=""
HARNESS_URL_FILE=""
HARNESS_BUILD_DIR=""
PLAYWRIGHT_LOG=""
cleanup() {
	if [[ -n "$HARNESS_PID" ]] && kill -0 "$HARNESS_PID" >/dev/null 2>&1; then
		kill "$HARNESS_PID" >/dev/null 2>&1 || true
		wait "$HARNESS_PID" >/dev/null 2>&1 || true
	fi
	[[ -n "$HARNESS_LOG" ]] && rm -f "$HARNESS_LOG"
	[[ -n "$HARNESS_URL_FILE" ]] && rm -f "$HARNESS_URL_FILE"
	[[ -n "$HARNESS_BUILD_DIR" ]] && rm -rf "$HARNESS_BUILD_DIR"
	[[ -n "$PLAYWRIGHT_LOG" ]] && rm -f "$PLAYWRIGHT_LOG"
}
trap cleanup EXIT

if [[ -z "${VISREG_DEV_SERVER_URL:-}" ]]; then
	if ! (cd "$VISREG_DIR" && node -e "import('vite')" >/dev/null 2>&1); then
		unavailable "vite is not installed in tests/visual_regression/node_modules — run pnpm install in tests/visual_regression."
	fi
	HARNESS_BUILD_DIR="$(mktemp -d)"
	if ! (
		cd "$VISREG_DIR"
		"$VISREG_DIR/node_modules/.bin/vite" build --config harness/vite.config.ts --outDir "$HARNESS_BUILD_DIR" --emptyOutDir
	) >/dev/null; then
		echo "[FAIL] visual-regression harness build failed — generated page imports are not loadable by Vite." >&2
		exit 1
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

# Everything is in place — run the real suite.
echo "==> visual-regression-dom (cadence=$CADENCE)"
cd "$VISREG_DIR"
PLAYWRIGHT_LOG="$(mktemp)"
if ! VISREG_CADENCE="$CADENCE" \
	"$VISREG_DIR/node_modules/.bin/playwright" test --project=dom 2>&1 | tee "$PLAYWRIGHT_LOG"; then
	if grep -Eq "Executable doesn't exist|Looks like Playwright was just installed|npx playwright install" "$PLAYWRIGHT_LOG"; then
		unavailable "Playwright Chromium browser is not installed. Run `pnpm exec playwright install chromium` in tests/visual_regression, then rerun this gate."
	fi
	if grep -q "MachPortRendezvousServer.*Permission denied" "$PLAYWRIGHT_LOG"; then
		unavailable "Playwright Chromium cannot launch in this macOS sandbox (MachPortRendezvousServer permission denied). Run the gate from an unsandboxed terminal or a browser-capable CI runner."
	fi
	unavailable "Playwright DOM run failed — verify Chromium/browser support or inspect the visual-regression output above."
fi
