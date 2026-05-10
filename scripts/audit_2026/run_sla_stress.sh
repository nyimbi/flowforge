#!/usr/bin/env bash
# scripts/audit_2026/run_sla_stress.sh
#
# Nightly SLA stress harness wrapper (v0.3.0 W4a / item 5).
#
# Walks every ``examples/<example>/generated/backend/tests/load/<jtbd>/``
# directory and invokes the k6 + Locust harness scripts the
# ``sla_loadtest`` generator emits for JTBDs declaring
# ``sla.breach_seconds``.
#
# When ``k6`` and/or ``locust`` are not on PATH (the typical per-PR
# runner setup) the script SKIPS WITH A CLEAR REASON and exits 0. This
# matches the cadence policy from ``docs/v0.3.0-engineering-plan.md``
# §10:
#
#     "SLA stress harness (item 5) runs nightly; not per-PR."
#
# The nightly GitHub Actions job
# (``.github/workflows/audit-2026.yml`` ``schedule:`` cron) installs
# both binaries before invoking the wrapper, so the skip path only
# triggers in environments without them.
#
# Exit status:
#   0 — every harness passed (or the skip path triggered).
#   1 — one or more harnesses failed an SLA threshold.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXAMPLES_DIR="$REPO_ROOT/examples"

TARGET="${TARGET:-http://127.0.0.1:8765}"

skip() {
	echo "[SKIP] audit-2026-sla-stress: $*"
	echo "  see docs/improvements.md item 5 + scripts/audit_2026/run_sla_stress.sh."
	exit 0
}

K6_BIN="$(command -v k6 2>/dev/null || true)"
LOCUST_BIN="$(command -v locust 2>/dev/null || true)"
if [[ -z "$K6_BIN" && -z "$LOCUST_BIN" ]]; then
	skip "neither 'k6' nor 'locust' is on PATH (nightly job installs both)"
fi

shopt -s nullglob
HARNESSES=("$EXAMPLES_DIR"/*/generated/backend/tests/load/*)
if [[ ${#HARNESSES[@]} -eq 0 ]]; then
	skip "no generated SLA stress harnesses found (no JTBD declares sla.breach_seconds in any example?)"
fi

FAILED=()
PASSED=()

for dir in "${HARNESSES[@]}"; do
	[[ -d "$dir" ]] || continue
	jtbd_id="$(basename "$dir")"
	echo ""
	echo "==> sla-stress :: $jtbd_id"
	echo "    dir: ${dir#$REPO_ROOT/}"

	if [[ -n "$K6_BIN" && -f "$dir/k6_test.js" ]]; then
		if env TARGET="$TARGET" "$K6_BIN" run --quiet "$dir/k6_test.js"; then
			PASSED+=("k6:$jtbd_id")
		else
			FAILED+=("k6:$jtbd_id")
		fi
	fi

	if [[ -n "$LOCUST_BIN" && -f "$dir/locust_test.py" ]]; then
		if env TARGET="$TARGET" "$LOCUST_BIN" -f "$dir/locust_test.py" \
			--headless -u 10 -r 2 -t 30s --host "$TARGET"; then
			PASSED+=("locust:$jtbd_id")
		else
			FAILED+=("locust:$jtbd_id")
		fi
	fi
done

echo ""
echo "sla-stress passed: ${#PASSED[@]} ; failed: ${#FAILED[@]}"
if (( ${#FAILED[@]} > 0 )); then
	echo "failed harnesses: ${FAILED[*]}"
	exit 1
fi
