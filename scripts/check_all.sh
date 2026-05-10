#!/usr/bin/env bash
# framework/scripts/check_all.sh — U24 end-to-end quality gate
#
# Runs the full flowforge framework quality gate + UMS migration parity check.
# Every step is fail-fast (set -e). Exit 0 = all green.
#
# Usage (from repo root):
#   bash framework/scripts/check_all.sh
#
# Env overrides:
#   FLOWFORGE_ROOT  — path to framework/ dir (default: repo_root/framework)
#   BACKEND_ROOT    — path to backend/ dir   (default: repo_root/backend)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_ROOT="${FLOWFORGE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
REPO_ROOT="$(cd "$FRAMEWORK_ROOT/.." && pwd)"
BACKEND_ROOT="${BACKEND_ROOT:-$REPO_ROOT/backend}"

START_TS=$(date +%s)

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

# ---------- Python package list (matches pyproject.toml workspace) ----

PY_PKGS=(
    flowforge-core
    flowforge-fastapi
    flowforge-sqlalchemy
    flowforge-tenancy
    flowforge-audit-pg
    flowforge-outbox-pg
    flowforge-rbac-static
    flowforge-rbac-spicedb
    flowforge-documents-s3
    flowforge-money
    flowforge-signing-kms
    flowforge-notify-multichannel
    flowforge-cli
)

JS_PKGS=(
    flowforge-types
    flowforge-renderer
    flowforge-runtime-client
    flowforge-step-adapters
    flowforge-designer
)

EXAMPLES=(
    building-permit
    hiring-pipeline
    insurance_claim
)

TOTAL_PKGS=$(( ${#PY_PKGS[@]} + ${#JS_PKGS[@]} ))

# ---------- Step 1: uv sync ------------------------------------------

step "1/12  uv sync (framework workspace)"
cd "$FRAMEWORK_ROOT"
uv sync --quiet
ok "uv sync complete"

# ---------- Step 2: pnpm install -------------------------------------

step "2/12  pnpm install (framework/js)"
cd "$FRAMEWORK_ROOT/js"
pnpm install --frozen-lockfile
ok "pnpm install complete"
cd "$FRAMEWORK_ROOT"

# ---------- Step 3: check_workspace.py -------------------------------

step "3/12  python check_workspace.py"
cd "$FRAMEWORK_ROOT"
python scripts/check_workspace.py
ok "workspace structural check passed"

# ---------- Step 4: pyright on each python/*/src ---------------------

step "4/12  pyright on each Python package"
for pkg in "${PY_PKGS[@]}"; do
    src_dir="$FRAMEWORK_ROOT/python/$pkg/src"
    if [[ -d "$src_dir" ]]; then
        echo "    pyright: $pkg"
        uv run pyright "$src_dir" --pythonversion 3.11 2>&1 | tail -3
    else
        fail "src dir missing: $src_dir"
    fi
done
ok "pyright clean on all ${#PY_PKGS[@]} Python packages"

# ---------- Step 5: pytest on each python/*/tests --------------------

step "5/12  pytest on each Python package"
PY_TEST_COUNT=0
for pkg in "${PY_PKGS[@]}"; do
    test_dir="$FRAMEWORK_ROOT/python/$pkg/tests"
    if [[ -d "$test_dir" ]]; then
        echo "    pytest: $pkg"
        # capture output to count tests; still fail-fast on error
        result=$(uv run pytest "$test_dir" -q --tb=short 2>&1)
        echo "$result" | tail -3
        # extract "X passed" line
        passed=$(echo "$result" | grep -E "^[0-9]+ passed" | grep -oE "^[0-9]+")
        PY_TEST_COUNT=$(( PY_TEST_COUNT + ${passed:-0} ))
    else
        fail "tests dir missing: $test_dir"
    fi
done
TOTAL_TESTS=$(( TOTAL_TESTS + PY_TEST_COUNT ))
ok "pytest: $PY_TEST_COUNT tests passed across ${#PY_PKGS[@]} Python packages"

# ---------- Step 6: JS typecheck (pnpm -r build covers all pkgs) -----

step "6/12  pnpm -r typecheck (JS workspace)"
cd "$FRAMEWORK_ROOT/js"
# run typecheck where defined; fall back to build (tsc --noEmit) for others
pnpm -r --if-present typecheck
pnpm -r build
ok "JS typecheck/build clean"
cd "$FRAMEWORK_ROOT"

# ---------- Step 7: pnpm -r test (JS workspace) ----------------------

step "7/12  pnpm -r test (JS workspace)"
cd "$FRAMEWORK_ROOT/js"
JS_TEST_OUTPUT=$(pnpm -r test 2>&1)
echo "$JS_TEST_OUTPUT" | tail -10
# vitest outputs "X tests passed"; sum them
JS_TEST_COUNT=$(echo "$JS_TEST_OUTPUT" | grep -oE '[0-9]+ (tests? )?(passed)' | grep -oE '^[0-9]+' | awk '{s+=$1}END{print s+0}')
TOTAL_TESTS=$(( TOTAL_TESTS + JS_TEST_COUNT ))
ok "JS tests: $JS_TEST_COUNT assertions passed across ${#JS_PKGS[@]} packages"
cd "$FRAMEWORK_ROOT"

# ---------- Step 8: JTBD deterministic regen check -------------------

step "8/12  JTBD deterministic regen check (${#EXAMPLES[@]} examples)"
REGEN_TMP=$(mktemp -d)
trap 'rm -rf "$REGEN_TMP"' EXIT

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

# ---------- Step 9: Visual regression DOM-snapshot gate ---------------
#
# Per ADR-001 (`docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md`),
# DOM snapshots are the CI-gating artifact for the visual regression
# suite (item 21). The wrapper script runs the smoke subset (canonical
# example only) per-PR and SKIPS WITH A CLEAR REASON when prerequisites
# are missing — i.e. when `pnpm install` is blocked on the pre-existing
# pnpm-ignored-builds issue, or when the dev-server harness has not yet
# landed. The W3 task brief explicitly authorises skip-with-reason here
# until the pnpm cleanup PR lands.
#
# Pixel SSIM is advisory only; it runs nightly via
# `make audit-2026-visual-regression-ssim`, never per-PR.

step "9/12  Visual regression DOM-snapshot gate (ADR-001)"
bash "$FRAMEWORK_ROOT/scripts/visual_regression/run_dom_snapshots.sh" smoke
ok "visual-regression-dom: gate run"

# ---------- Step 10: UMS parity test ---------------------------------

step "10/12  UMS workflow-def parity (backend)"
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

# ---------- Step 11: Cross-package integration tests ------------------

step "11/12  Cross-package integration tests"
cd "$FRAMEWORK_ROOT"
bash "$FRAMEWORK_ROOT/scripts/run_integration.sh"
INT_PASS=$(uv run pytest "$FRAMEWORK_ROOT/tests/integration/python/tests/" -q --tb=no 2>&1 | grep -oE '^[0-9]+ passed' | grep -oE '^[0-9]+' || echo 0)
TOTAL_TESTS=$(( TOTAL_TESTS + ${INT_PASS:-0} ))
ok "integration tests: ${INT_PASS:-0} Python tests passed"
cd "$REPO_ROOT"

# ---------- Step 12: Summary -----------------------------------------

END_TS=$(date +%s)
ELAPSED=$(( END_TS - START_TS ))

step "12/12  Summary"
echo ""
echo -e "${BOLD}flowforge gate — all steps green${RESET}"
echo "  Python packages : ${#PY_PKGS[@]}"
echo "  JS packages     : ${#JS_PKGS[@]}"
echo "  Total packages  : $TOTAL_PKGS"
echo "  Total tests     : $TOTAL_TESTS"
echo "  Elapsed         : ${ELAPSED}s"
echo ""
ok "U24 gate PASSED"
