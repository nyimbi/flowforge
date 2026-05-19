#!/usr/bin/env bash
# scripts/run_integration.sh
#
# Runs all flowforge cross-package integration tests and summarises results.
# Called as the final stage from scripts/check_all.sh.
#
# Usage (from repo root):
#   bash scripts/run_integration.sh
#
# Env:
#   FLOWFORGE_ROOT  — path to flowforge repo root (default: parent of this script)
#   SKIP_E2E        — set to "1" to skip the audit e2e pytest flows
#   RUN_BROWSER_E2E — set to "1" to run the browser Playwright full-stack
#                     lane (requires Chromium-capable environment)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_ROOT="${FLOWFORGE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY_INT="$FRAMEWORK_ROOT/tests/integration/python"
E2E_INT="$FRAMEWORK_ROOT/tests/integration/e2e"
# JS integration tests live inside the js/ workspace so workspace:* deps resolve.
JS_INT="$FRAMEWORK_ROOT/js/flowforge-integration-tests"
BROWSER_E2E_SCRIPT="$FRAMEWORK_ROOT/scripts/run_browser_full_stack.sh"

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
PY_PASS=0
JS_PASS=0
E2E_PASS=0
E2E_FAIL=0
BROWSER_E2E_PASS=0
BROWSER_E2E_FAIL=0
BROWSER_E2E_SKIPPED=0

# ---------------------------------------------------------------------------
# Stage 1: Python cross-package integration tests
# ---------------------------------------------------------------------------

step "Stage 1/4  Python integration tests (pytest)"

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

step "Stage 2/4  JS integration tests (vitest)"

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
# Stage 3: Audit e2e flows
# ---------------------------------------------------------------------------

step "Stage 3/4  Audit e2e flows (pytest)"

if [[ "${SKIP_E2E:-0}" == "1" ]]; then
    echo "  [SKIP] SKIP_E2E=1 — audit e2e flows skipped by explicit operator request"
elif [[ ! -d "$E2E_INT" ]]; then
    fail "Audit e2e directory not found: $E2E_INT"
else
    E2E_OUT=$(mktemp)
    if cd "$FRAMEWORK_ROOT" && uv run pytest tests/integration/e2e -q --tb=short 2>&1 | tee "$E2E_OUT"; then
        E2E_PASS=$(grep -oE '^[0-9]+ passed' "$E2E_OUT" | grep -oE '^[0-9]+' || echo 0)
        E2E_FAIL=0
        ok "Audit e2e: $E2E_PASS tests passed"
    else
        E2E_PASS=$(grep -oE '[0-9]+ passed' "$E2E_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 0)
        E2E_FAIL=$(grep -oE '[0-9]+ failed' "$E2E_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 0)
        fail "Audit e2e: ${E2E_FAIL:-?} tests failed (see output above)"
    fi
    rm -f "$E2E_OUT"
fi
TOTAL_PASS=$(( TOTAL_PASS + E2E_PASS ))
TOTAL_FAIL=$(( TOTAL_FAIL + E2E_FAIL ))

# ---------------------------------------------------------------------------
# Stage 4: Browser Playwright full-stack
# ---------------------------------------------------------------------------

step "Stage 4/4  Browser Playwright full-stack"

if [[ "${RUN_BROWSER_E2E:-0}" == "1" ]]; then
    if [[ ! -x "$BROWSER_E2E_SCRIPT" ]]; then
        fail "Browser e2e script missing or not executable: $BROWSER_E2E_SCRIPT"
    fi
    BROWSER_E2E_OUT=$(mktemp)
    if cd "$FRAMEWORK_ROOT" && bash "$BROWSER_E2E_SCRIPT" 2>&1 | tee "$BROWSER_E2E_OUT"; then
        if grep -q '\[SKIP\] browser-full-stack' "$BROWSER_E2E_OUT"; then
            BROWSER_E2E_PASS=0
            BROWSER_E2E_FAIL=0
            BROWSER_E2E_SKIPPED=1
            ok "Browser e2e: skipped by explicit local bootstrap setting"
        else
            BROWSER_E2E_PASS=$(grep -oE '[0-9]+ passed' "$BROWSER_E2E_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 1)
            BROWSER_E2E_FAIL=0
            ok "Browser e2e: $BROWSER_E2E_PASS tests passed"
        fi
    else
        BROWSER_E2E_PASS=$(grep -oE '[0-9]+ passed' "$BROWSER_E2E_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 0)
        BROWSER_E2E_FAIL=$(grep -oE '[0-9]+ failed' "$BROWSER_E2E_OUT" | grep -oE '^[0-9]+' | tail -1 || echo 1)
        fail "Browser e2e: ${BROWSER_E2E_FAIL:-?} tests failed (see output above)"
    fi
    rm -f "$BROWSER_E2E_OUT"
else
    echo "  [EXTERNAL] RUN_BROWSER_E2E=1 not set — browser full-stack lane is run by audit-2026-browser-e2e in browser-capable CI"
fi
TOTAL_PASS=$(( TOTAL_PASS + BROWSER_E2E_PASS ))
TOTAL_FAIL=$(( TOTAL_FAIL + BROWSER_E2E_FAIL ))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}Integration test summary${RESET}"
echo "  Python passed : $PY_PASS"
echo "  JS passed     : ${JS_PASS:-0}"
if [[ "${SKIP_E2E:-0}" == "1" ]]; then
    echo "  E2e passed    : SKIPPED"
else
    echo "  E2e passed    : $E2E_PASS"
fi
if [[ "${RUN_BROWSER_E2E:-0}" == "1" && "$BROWSER_E2E_SKIPPED" == "0" ]]; then
    echo "  Browser e2e   : $BROWSER_E2E_PASS"
elif [[ "${RUN_BROWSER_E2E:-0}" == "1" ]]; then
    echo "  Browser e2e   : SKIPPED"
else
    echo "  Browser e2e   : EXTERNAL"
fi
echo "  Total passed  : $(( TOTAL_PASS ))"
echo "  Total failed  : $TOTAL_FAIL"
printf 'Integration JSON: {"python_passed":%s,"js_passed":%s,"e2e_passed":%s,"e2e_skipped":%s,"browser_e2e_passed":%s,"browser_e2e_external":%s,"browser_e2e_skipped":%s,"total_passed":%s,"total_failed":%s}\n' \
    "$PY_PASS" \
    "${JS_PASS:-0}" \
    "$E2E_PASS" \
    "$([[ "${SKIP_E2E:-0}" == "1" ]] && echo true || echo false)" \
    "$BROWSER_E2E_PASS" \
    "$([[ "${RUN_BROWSER_E2E:-0}" == "1" ]] && echo false || echo true)" \
    "$([[ "$BROWSER_E2E_SKIPPED" == "1" ]] && echo true || echo false)" \
    "$TOTAL_PASS" \
    "$TOTAL_FAIL"
echo ""

if [[ "$TOTAL_FAIL" -gt 0 ]]; then
    fail "Integration gate FAILED ($TOTAL_FAIL failures)"
fi
ok "Integration gate PASSED"
