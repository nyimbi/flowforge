#!/usr/bin/env bash
# scripts/check_all.sh — U24 end-to-end quality gate
#
# Runs the full flowforge framework quality gate + UMS migration parity check.
# Every step is fail-fast (set -e). Exit 0 = all green.
#
# Usage (from repo root):
#   bash scripts/check_all.sh
#
# Env overrides:
#   FLOWFORGE_ROOT  — path to flowforge repo root (default: this script's parent)
#   BACKEND_ROOT    — path to backend/ dir (default: parent/backend; skipped when absent)
#   FLOWFORGE_CHECK_JOBS — package-level pyright/pytest parallelism (default: 4)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_ROOT="${FLOWFORGE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
REPO_ROOT="$(cd "$FRAMEWORK_ROOT/.." && pwd)"
BACKEND_ROOT="${BACKEND_ROOT:-$REPO_ROOT/backend}"

START_TS=$(date +%s)
FLOWFORGE_CHECK_JOBS="${FLOWFORGE_CHECK_JOBS:-4}"
if ! [[ "$FLOWFORGE_CHECK_JOBS" =~ ^[0-9]+$ ]] || [[ "$FLOWFORGE_CHECK_JOBS" -lt 1 ]]; then
    echo "FLOWFORGE_CHECK_JOBS must be a positive integer, got: $FLOWFORGE_CHECK_JOBS" >&2
    exit 1
fi

# ---------- helpers --------------------------------------------------

GREEN="\033[0;32m"
RED="\033[0;31m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}[OK]${RESET}  $*"; }
fail() { echo -e "${RED}[FAIL]${RESET} $*" >&2; exit 1; }
step() { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }

TOTAL_TESTS=0
TOTAL_PKGS=0
TMP_DIRS=()

cleanup_tmp_dirs() {
    for dir in "${TMP_DIRS[@]:-}"; do
        if [[ -n "$dir" ]]; then
            rm -rf "$dir"
        fi
    done
}
trap cleanup_tmp_dirs EXIT

# ---------- Package lists (derived from workspace manifests) ----------

cd "$FRAMEWORK_ROOT"
PY_PKGS=()
while IFS= read -r pkg; do
    PY_PKGS+=("$pkg")
done < <(python scripts/check_workspace.py --list-python)
JS_PKGS=()
while IFS= read -r pkg; do
    JS_PKGS+=("$pkg")
done < <(python scripts/check_workspace.py --list-js)

EXAMPLES=(
    building-permit
    hiring-pipeline
    insurance_claim
)

TOTAL_PKGS=$(( ${#PY_PKGS[@]} + ${#JS_PKGS[@]} ))

# ---------- Step 1: uv sync ------------------------------------------

step "1/14  uv sync (framework workspace)"
cd "$FRAMEWORK_ROOT"
uv sync --quiet
ok "uv sync complete"

# ---------- Step 2: pnpm install -------------------------------------

step "2/14  pnpm install (framework/js + visual regression runner)"
cd "$FRAMEWORK_ROOT/js"
CI="${CI:-true}" pnpm install --frozen-lockfile
cd "$FRAMEWORK_ROOT/tests/visual_regression"
CI="${CI:-true}" pnpm install --frozen-lockfile
ok "pnpm install complete"
cd "$FRAMEWORK_ROOT"

# ---------- Step 3: check_workspace.py -------------------------------

step "3/14  python check_workspace.py"
cd "$FRAMEWORK_ROOT"
python scripts/check_workspace.py
ok "workspace structural check passed"

# ---------- Step 4: pyright on each python/*/src ---------------------

step "4/14  pyright on each Python package"
PYRIGHT_TMP=$(mktemp -d)
TMP_DIRS+=("$PYRIGHT_TMP")
pids=()
pid_pkgs=()
pid_logs=()

flush_pyright_batch() {
    local failed=0
    local idx
    for idx in "${!pids[@]}"; do
        if ! wait "${pids[$idx]}"; then
            failed=1
        fi
    done
    for idx in "${!pids[@]}"; do
        cat "${pid_logs[$idx]}"
    done
    if [[ "$failed" -ne 0 ]]; then
        fail "pyright failed for one or more packages in batch: ${pid_pkgs[*]}"
    fi
    pids=()
    pid_pkgs=()
    pid_logs=()
}

for pkg in "${PY_PKGS[@]}"; do
    src_dir="$FRAMEWORK_ROOT/python/$pkg/src"
    if [[ -d "$src_dir" ]]; then
        log="$PYRIGHT_TMP/$pkg.log"
        (
            echo "    pyright: $pkg"
            uv run pyright "$src_dir" --pythonversion 3.11
        ) > "$log" 2>&1 &
        pids+=("$!")
        pid_pkgs+=("$pkg")
        pid_logs+=("$log")
        if [[ "${#pids[@]}" -ge "$FLOWFORGE_CHECK_JOBS" ]]; then
            flush_pyright_batch
        fi
    else
        fail "src dir missing: $src_dir"
    fi
done
if [[ "${#pids[@]}" -gt 0 ]]; then
    flush_pyright_batch
fi
ok "pyright clean on all ${#PY_PKGS[@]} Python packages"

# ---------- Step 5: pytest on each python/*/tests --------------------

step "5/14  pytest on each Python package"
PY_TEST_COUNT=0
PYTEST_TMP=$(mktemp -d)
TMP_DIRS+=("$PYTEST_TMP")
pids=()
pid_pkgs=()
pid_logs=()

flush_pytest_batch() {
    local failed=0
    local idx
    local passed
    for idx in "${!pids[@]}"; do
        if ! wait "${pids[$idx]}"; then
            failed=1
        fi
    done
    for idx in "${!pids[@]}"; do
        cat "${pid_logs[$idx]}"
        passed=$(grep -E "^[0-9]+ passed" "${pid_logs[$idx]}" | grep -oE "^[0-9]+" || true)
        PY_TEST_COUNT=$(( PY_TEST_COUNT + ${passed:-0} ))
    done
    if [[ "$failed" -ne 0 ]]; then
        fail "pytest failed for one or more packages in batch: ${pid_pkgs[*]}"
    fi
    pids=()
    pid_pkgs=()
    pid_logs=()
}

for pkg in "${PY_PKGS[@]}"; do
    test_dir="$FRAMEWORK_ROOT/python/$pkg/tests"
    if [[ -d "$test_dir" ]]; then
        log="$PYTEST_TMP/$pkg.log"
        src_dir="$FRAMEWORK_ROOT/python/$pkg/src"
        (
            echo "    pytest: $pkg"
            PYTHONPATH="$src_dir:${PYTHONPATH:-}" uv run pytest "$test_dir" -q --tb=short
        ) > "$log" 2>&1 &
        pids+=("$!")
        pid_pkgs+=("$pkg")
        pid_logs+=("$log")
        if [[ "${#pids[@]}" -ge "$FLOWFORGE_CHECK_JOBS" ]]; then
            flush_pytest_batch
        fi
    else
        fail "tests dir missing: $test_dir"
    fi
done
if [[ "${#pids[@]}" -gt 0 ]]; then
    flush_pytest_batch
fi
TOTAL_TESTS=$(( TOTAL_TESTS + PY_TEST_COUNT ))
ok "pytest: $PY_TEST_COUNT tests passed across ${#PY_PKGS[@]} Python packages"

# ---------- Step 6: Python dependency CVE audit ----------------------

step "6/14  pip-audit on Python dependencies"
AUDIT_TMP="${TMPDIR:-/tmp}/flowforge-pip-audit-cache"
UV_AUDIT_CACHE="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/flowforge-uv-cache}"
mkdir -p "$AUDIT_TMP" "$UV_AUDIT_CACHE"
UV_CACHE_DIR="$UV_AUDIT_CACHE" \
	PIP_CACHE_DIR="$AUDIT_TMP" \
	uv run --with pip-audit pip-audit --skip-editable --cache-dir "$AUDIT_TMP"
ok "Python dependency CVE audit clean"

# ---------- Step 7: JS dependency CVE audit --------------------------

step "7/14  pnpm audit (JS production dependencies)"
cd "$FRAMEWORK_ROOT/js"
pnpm audit --prod
ok "JS production dependency audit clean"
cd "$FRAMEWORK_ROOT"

# ---------- Step 8: JS typecheck (pnpm -r build covers all pkgs) -----

step "8/14  pnpm -r typecheck (JS workspace)"
cd "$FRAMEWORK_ROOT/js"
# run typecheck where defined; fall back to build (tsc --noEmit) for others
pnpm -r --if-present typecheck
pnpm -r build
ok "JS typecheck/build clean"
cd "$FRAMEWORK_ROOT"

# ---------- Step 9: pnpm -r test (JS workspace) ----------------------

step "9/14  pnpm -r test (JS workspace)"
cd "$FRAMEWORK_ROOT/js"
JS_TEST_LOG=$(mktemp)
if ! pnpm -r test 2>&1 | tee "$JS_TEST_LOG"; then
    fail "pnpm -r test failed"
fi
# vitest outputs "X tests passed"; sum them
JS_TEST_COUNT=$(grep -oE '[0-9]+ (tests? )?(passed)' "$JS_TEST_LOG" | grep -oE '^[0-9]+' | awk '{s+=$1}END{print s+0}' || true)
rm -f "$JS_TEST_LOG"
TOTAL_TESTS=$(( TOTAL_TESTS + JS_TEST_COUNT ))
ok "JS tests: $JS_TEST_COUNT assertions passed across ${#JS_PKGS[@]} packages"
cd "$FRAMEWORK_ROOT"

# ---------- Step 10: JTBD deterministic regen check ------------------

step "10/14  JTBD deterministic regen check (${#EXAMPLES[@]} examples)"
REGEN_TMP=$(mktemp -d)
TMP_DIRS+=("$REGEN_TMP")

for example in "${EXAMPLES[@]}"; do
    bundle="$FRAMEWORK_ROOT/examples/$example/jtbd-bundle.json"
    expected_dir="$FRAMEWORK_ROOT/examples/$example/generated"

    if [[ ! -f "$bundle" ]]; then
        fail "jtbd-bundle.json missing for example: $example"
    fi

    if [[ ! -d "$expected_dir" ]]; then
        echo "    SKIP regen diff for $example (no generated/ dir checked in)"
        continue
    fi

    echo "    regen: $example"
    actual_dir="$REGEN_TMP/$example"
    mkdir -p "$actual_dir"

    # Run the generator into a temp dir
    uv run flowforge jtbd-generate \
        --jtbd "$bundle" \
        --out "$actual_dir" \
        --force \
        2>&1 | tail -2

    # Byte-identical diff
    if ! diff -rq --exclude="*.pyc" --exclude="__pycache__" \
            "$expected_dir" "$actual_dir" > /dev/null 2>&1; then
        echo "  Diff between expected and regenerated output for $example:"
        diff -ru --exclude="*.pyc" "$expected_dir" "$actual_dir" | head -60
        fail "JTBD regen mismatch for $example — generator output is not byte-identical to checked-in generated/"
    fi

    ok "  $example: regen byte-identical"
done
ok "JTBD deterministic regen: all examples match"

# ---------- Step 11: Visual regression DOM-snapshot gate --------------
#
# Per ADR-001 (`docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md`),
# DOM snapshots are the CI-gating artifact for the visual regression
# suite (item 21). The wrapper script runs the smoke subset (canonical
# example only) per-PR and fails when prerequisites or checked-in DOM
# baselines are missing. Local workstation bootstrap may opt into
# VISREG_ALLOW_SKIP=1, but release gates must not set it.
#
# Pixel SSIM is advisory only; it runs nightly via
# `make audit-2026-visual-regression-ssim`, never per-PR.

step "11/14  Visual regression DOM-snapshot gate (ADR-001)"
bash "$FRAMEWORK_ROOT/scripts/visual_regression/run_dom_snapshots.sh" smoke
ok "visual-regression-dom: gate run"

# ---------- Step 12: UMS parity test ---------------------------------

step "12/14  UMS workflow-def parity (backend)"
if [[ ! -d "$BACKEND_ROOT" ]]; then
    echo "    SKIP UMS parity: BACKEND_ROOT not found at $BACKEND_ROOT"
    echo "    Set BACKEND_ROOT=/path/to/backend when running from a UMS monorepo checkout."
    ok "parity: skipped (standalone flowforge checkout)"
else
cd "$BACKEND_ROOT"
PARITY_OUTPUT=$(uv run pytest tests/test_workflow_def_parity.py -v --tb=short 2>&1)
echo "$PARITY_OUTPUT" | tail -10
PARITY_COUNT=$(echo "$PARITY_OUTPUT" | grep -oE '^[0-9]+ passed' | grep -oE '^[0-9]+' || true)
PARITY_COUNT=${PARITY_COUNT:-0}
# also check for "passed" in summary line
if echo "$PARITY_OUTPUT" | grep -qE 'passed'; then
    PARITY_COUNT=$(echo "$PARITY_OUTPUT" | grep -oE '[0-9]+ passed' | grep -oE '^[0-9]+' | tail -1)
fi
TOTAL_TESTS=$(( TOTAL_TESTS + ${PARITY_COUNT:-0} ))
ok "parity: ${PARITY_COUNT:-0} parity tests passed (22-def target)"
cd "$REPO_ROOT"
fi

# ---------- Step 13: Cross-package integration tests ------------------

step "13/14  Cross-package integration tests"
cd "$FRAMEWORK_ROOT"
INT_OUT=$(mktemp)
bash "$FRAMEWORK_ROOT/scripts/run_integration.sh" 2>&1 | tee "$INT_OUT"
INT_PASS=$(grep -oE 'Total passed  : [0-9]+' "$INT_OUT" | grep -oE '[0-9]+' | tail -1 || echo 0)
rm -f "$INT_OUT"
TOTAL_TESTS=$(( TOTAL_TESTS + ${INT_PASS:-0} ))
ok "integration tests: ${INT_PASS:-0} cross-package tests/assertions passed"
cd "$REPO_ROOT"

# ---------- Step 14: Summary -----------------------------------------

END_TS=$(date +%s)
ELAPSED=$(( END_TS - START_TS ))

step "14/14  Summary"
echo ""
echo -e "${BOLD}flowforge gate — all steps green${RESET}"
echo "  Python packages : ${#PY_PKGS[@]}"
echo "  JS packages     : ${#JS_PKGS[@]}"
echo "  Total packages  : $TOTAL_PKGS"
echo "  Total tests     : $TOTAL_TESTS"
echo "  Elapsed         : ${ELAPSED}s"
echo ""
ok "U24 gate PASSED"
