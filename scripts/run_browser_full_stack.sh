#!/usr/bin/env bash
# scripts/run_browser_full_stack.sh
#
# Browser-backed e2e gate for the generated workflow path:
# Playwright Chromium -> generated React page -> real HTTP origin ->
# generated insurance-claim FastAPI router -> generated domain service.
#
# This target requires an environment where Playwright can launch Chromium.
# Local bootstrap may opt into BROWSER_E2E_ALLOW_SKIP=1, but release gates
# must not set it.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VISREG_DIR="$REPO_ROOT/tests/visual_regression"
BACKEND_SCRIPT="$REPO_ROOT/tests/integration/browser/generated_backend_server.py"

: "${UV_CACHE_DIR:=/private/tmp/flowforge-uv-cache}"
export UV_CACHE_DIR

unavailable() {
	if [[ "${BROWSER_E2E_ALLOW_SKIP:-}" == "1" ]]; then
		echo "[SKIP] browser-full-stack: $*"
		echo "  run without BROWSER_E2E_ALLOW_SKIP in browser-capable release CI."
		exit 0
	fi
	echo "[FAIL] browser-full-stack: $*" >&2
	echo "  set BROWSER_E2E_ALLOW_SKIP=1 only for local bootstrap, not release gates." >&2
	exit 1
}

if [[ ! -d "$VISREG_DIR" ]]; then
	echo "[FAIL] tests/visual_regression/ missing — Playwright runner deleted?" >&2
	exit 1
fi

if [[ ! -d "$VISREG_DIR/node_modules" ]]; then
	unavailable "tests/visual_regression/node_modules missing — run pnpm install for the visual regression runner."
fi

if ! "$VISREG_DIR/node_modules/.bin/playwright" --version >/dev/null 2>&1; then
	unavailable "@playwright/test CLI not on PATH inside tests/visual_regression/node_modules — pnpm install incomplete."
fi

if [[ ! -f "$BACKEND_SCRIPT" ]]; then
	echo "[FAIL] generated backend bridge missing: $BACKEND_SCRIPT" >&2
	exit 1
fi

BACKEND_PID=""
BACKEND_LOG=""
BACKEND_URL_FILE=""
HARNESS_PID=""
HARNESS_LOG=""
HARNESS_URL_FILE=""
PLAYWRIGHT_LOG=""

cleanup() {
	if [[ -n "$HARNESS_PID" ]] && kill -0 "$HARNESS_PID" >/dev/null 2>&1; then
		kill "$HARNESS_PID" >/dev/null 2>&1 || true
		wait "$HARNESS_PID" >/dev/null 2>&1 || true
	fi
	if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
		kill "$BACKEND_PID" >/dev/null 2>&1 || true
		wait "$BACKEND_PID" >/dev/null 2>&1 || true
	fi
	[[ -n "$BACKEND_LOG" ]] && rm -f "$BACKEND_LOG"
	[[ -n "$BACKEND_URL_FILE" ]] && rm -f "$BACKEND_URL_FILE"
	[[ -n "$HARNESS_LOG" ]] && rm -f "$HARNESS_LOG"
	[[ -n "$HARNESS_URL_FILE" ]] && rm -f "$HARNESS_URL_FILE"
	[[ -n "$PLAYWRIGHT_LOG" ]] && rm -f "$PLAYWRIGHT_LOG"
}
trap cleanup EXIT

BACKEND_URL_FILE="$(mktemp)"
BACKEND_LOG="$(mktemp)"
(
	cd "$REPO_ROOT"
	uv run python "$BACKEND_SCRIPT" --url-file "$BACKEND_URL_FILE"
) >"$BACKEND_LOG" 2>&1 &
BACKEND_PID="$!"
for _ in {1..100}; do
	if [[ -s "$BACKEND_URL_FILE" ]]; then
		FLOWFORGE_BROWSER_E2E_API_URL="$(cat "$BACKEND_URL_FILE")"
		export FLOWFORGE_BROWSER_E2E_API_URL
		echo "    generated backend: $FLOWFORGE_BROWSER_E2E_API_URL"
		break
	fi
	if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
		cat "$BACKEND_LOG" >&2
		echo "[FAIL] browser-full-stack backend failed to start" >&2
		exit 1
	fi
	sleep 0.1
done
if [[ -z "${FLOWFORGE_BROWSER_E2E_API_URL:-}" ]]; then
	cat "$BACKEND_LOG" >&2
	echo "[FAIL] browser-full-stack backend did not report a URL" >&2
	exit 1
fi

HARNESS_URL_FILE="$(mktemp)"
HARNESS_LOG="$(mktemp)"
(
	cd "$VISREG_DIR"
	NEXT_PUBLIC_FLOWFORGE_API_BASE_URL="$FLOWFORGE_BROWSER_E2E_API_URL" \
	NEXT_PUBLIC_FLOWFORGE_DEMO_MODE="0" \
	NEXT_PUBLIC_FLOWFORGE_TENANT_ID="${FLOWFORGE_BROWSER_E2E_TENANT_ID:-tenant-browser-e2e}" \
		node "$VISREG_DIR/harness/start-dev-server.mjs" "$HARNESS_URL_FILE"
) >"$HARNESS_LOG" 2>&1 &
HARNESS_PID="$!"
for _ in {1..100}; do
	if [[ -s "$HARNESS_URL_FILE" ]]; then
		VISREG_DEV_SERVER_URL="$(cat "$HARNESS_URL_FILE")"
		export VISREG_DEV_SERVER_URL
		echo "    frontend harness: $VISREG_DEV_SERVER_URL"
		break
	fi
	if ! kill -0 "$HARNESS_PID" >/dev/null 2>&1; then
		cat "$HARNESS_LOG" >&2
		echo "[FAIL] browser-full-stack frontend harness failed to start" >&2
		exit 1
	fi
	sleep 0.1
done
if [[ -z "${VISREG_DEV_SERVER_URL:-}" ]]; then
	cat "$HARNESS_LOG" >&2
	echo "[FAIL] browser-full-stack frontend harness did not report a URL" >&2
	exit 1
fi

echo "==> browser-full-stack Playwright e2e"
cd "$VISREG_DIR"
PLAYWRIGHT_LOG="$(mktemp)"
if ! FLOWFORGE_BROWSER_E2E_REQUIRE=1 \
	"$VISREG_DIR/node_modules/.bin/playwright" test --project=browser-full-stack 2>&1 | tee "$PLAYWRIGHT_LOG"; then
	if grep -Eq "Executable doesn't exist|Looks like Playwright was just installed|npx playwright install" "$PLAYWRIGHT_LOG"; then
		unavailable "Playwright Chromium browser is not installed. Run `pnpm exec playwright install chromium` in tests/visual_regression, then rerun this gate."
	fi
	if grep -q "MachPortRendezvousServer.*Permission denied" "$PLAYWRIGHT_LOG"; then
		unavailable "Playwright Chromium cannot launch in this macOS sandbox (MachPortRendezvousServer permission denied). Run the gate from an unsandboxed terminal or a browser-capable CI runner."
	fi
	unavailable "Playwright browser execution failed — verify Chromium/browser support or inspect the browser-full-stack output above."
fi
