#!/usr/bin/env bash
# scripts/ci/ratchets/check.sh
#
# Runs every audit-2026 grep ratchet (audit-fix-plan §F-6 / R-6).
# Exits 0 when every ratchet is green.
# Exits 1 with a per-ratchet summary on the first failure.
#
# Each individual ratchet script is responsible for its own match/exclude
# logic. This wrapper just sequences them and aggregates the result.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

RATCHETS=(
	no_default_secret.sh
	no_string_interp_sql.sh
	no_eq_compare_hmac.sh
	no_except_pass.sh
	no_unparried_expr_in_step_template.sh
)

FAILED=()
PASSED=()

for r in "${RATCHETS[@]}"; do
	script="$SCRIPT_DIR/$r"
	if [[ ! -x "$script" ]]; then
		echo -e "${YELLOW}[SKIP]${RESET} $r (not executable)"
		continue
	fi
	if "$script"; then
		PASSED+=("$r")
		echo -e "${GREEN}[PASS]${RESET} ratchet $r"
	else
		FAILED+=("$r")
		echo -e "${RED}[FAIL]${RESET} ratchet $r"
	fi
done

echo ""
echo "ratchets passed: ${#PASSED[@]} / ${#RATCHETS[@]}"
if (( ${#FAILED[@]} > 0 )); then
	echo -e "${RED}ratchets failed:${RESET} ${FAILED[*]}"
	echo "see scripts/ci/ratchets/baseline.txt for the legit-exceptions protocol."
	exit 1
fi
