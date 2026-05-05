#!/usr/bin/env bash
# framework/scripts/run_integration.sh
#
# Runs all flowforge cross-package integration tests and summarises results.
# Called as the final stage from framework/scripts/check_all.sh.
#
# Usage (from repo root):
#   bash framework/scripts/run_integration.sh
#
# Env:
#   FLOWFORGE_ROOT  — path to framework/ dir (default: parent of this script)
#   SKIP_E2E        — set to "1" to skip Playwright e2e (requires docker-compose)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_ROOT="${FLOWFORGE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY_INT="$FRAMEWORK_ROOT/tests/integration/python"
# JS integration tests live inside the js/ workspace so workspace:* deps resolve.
JS_INT="$FRAMEWORK_ROOT/js/flowforge-integration-tests"

GREEN="\033[0;32m"
RED="\033[0;31m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}[OK]${RESET}  $*"; }
fail() { echo -e "${RED}[FAIL]${RESET} $*" >&2; exit 1; }
step() { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }

TOTAL_PASS=0
TOTAL_FAIL=0

# ---------------------------------------------------------------------------
# Stage 1: Python cross-package integration tests
# ---------------------------------------------------------------------------

step "Stage 1/3  Python integration tests (pytest)"

PY_OUT=$(mktemp)
if cd "$PY_INT" && uv run pytest tests/ -q --tb=short 2>&1 | tee "$PY_OUT"; then
    PY_PASS=$(grep -oE '^[0-9]+ passed' "$PY_OUT" | grep -oE '^[0-9]+' || echo 0)
    PY_FAIL=0
    ok "Python integration: $PY_PASS tests passed"
else
    PY_PASS=$(grep -oE '[0-9]+ passed' "$PY_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 0)
    PY_FAIL=$(grep -oE '[0-9]+ failed' "$PY_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 0)
    fail "Python integration: $PY_FAIL tests failed (see output above)"
fi
rm -f "$PY_OUT"
TOTAL_PASS=$(( TOTAL_PASS + PY_PASS ))
TOTAL_FAIL=$(( TOTAL_FAIL + PY_FAIL ))

# ---------------------------------------------------------------------------
# Stage 2: JS cross-package integration tests (vitest)
# ---------------------------------------------------------------------------

step "Stage 2/3  JS integration tests (vitest)"

JS_OUT=$(mktemp)
if cd "$JS_INT" && pnpm test 2>&1 | tee "$JS_OUT"; then
    JS_PASS=$(grep -oE '[0-9]+ (tests? )?(passed)' "$JS_OUT" | grep -oE '^[0-9]+' | awk '{s+=$1}END{print s+0}')
    JS_FAIL=0
    ok "JS integration: ${JS_PASS:-?} tests passed"
else
    JS_PASS=$(grep -oE '[0-9]+ passed' "$JS_OUT" | grep -oE '^[0-9]+' | awk '{s+=$1}END{print s+0}' || echo 0)
    JS_FAIL=$(grep -oE '[0-9]+ failed' "$JS_OUT" | grep -oE '^[0-9]+' | awk '{s+=$1}END{print s+0}' || echo 0)
    fail "JS integration: ${JS_FAIL:-?} tests failed (see output above)"
fi
rm -f "$JS_OUT"
TOTAL_PASS=$(( TOTAL_PASS + ${JS_PASS:-0} ))
TOTAL_FAIL=$(( TOTAL_FAIL + ${JS_FAIL:-0} ))

# ---------------------------------------------------------------------------
# Stage 3: Playwright e2e — skipped unless docker-compose available
# ---------------------------------------------------------------------------

step "Stage 3/3  Playwright e2e"

if [[ "${SKIP_E2E:-0}" == "1" ]]; then
    echo "  [SKIP] SKIP_E2E=1 — deferred (requires docker-compose + running services)"
elif ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    echo "  [SKIP] docker-compose not available — Playwright e2e deferred"
    echo "         See framework/tests/integration/README.md §Deferred items"
else
    echo "  [INFO] docker-compose detected but Playwright e2e not yet implemented."
    echo "         See framework/tests/integration/README.md §Deferred items"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}Integration test summary${RESET}"
echo "  Python passed : $TOTAL_PASS"
echo "  JS passed     : ${JS_PASS:-0}"
echo "  E2e           : DEFERRED"
echo "  Total passed  : $(( TOTAL_PASS ))"
echo "  Total failed  : $TOTAL_FAIL"
echo ""

if [[ "$TOTAL_FAIL" -gt 0 ]]; then
    fail "Integration gate FAILED ($TOTAL_FAIL failures)"
fi
ok "Integration gate PASSED"
