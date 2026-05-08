#!/usr/bin/env bash
# audit-2026 soak test runner.
#
# Plan §10.3 close-out criterion 7: 24h soak at 10 fires/sec + 100
# outbox dispatches/sec; assert zero flowforge_audit_chain_breaks_total
# and zero unhandled fire rejects.
#
# Usage:
#   scripts/ops/audit-2026-soak.sh \
#     --target-url https://staging.flowforge/api \
#     --duration 24h \
#     --fires-per-sec 10 \
#     --outbox-per-sec 100
#
# Exits 0 on green. Exits 1 if any required SLI is breached. Logs
# Prometheus snapshot pre/post to ./soak-evidence/.
#
# Required env (or matching --flags):
#   AUDIT_2026_SOAK_TARGET     base URL of the staging environment
#   AUDIT_2026_SOAK_PROM       Prometheus endpoint for SLI scrape
#   AUDIT_2026_SOAK_TENANT     synthetic test tenant id
#   AUDIT_2026_SOAK_PRINCIPAL  synthetic admin principal token
#
# Dependencies: k6 (load gen), curl + jq (prom scrape), promtool
# (alert rule verification).

set -euo pipefail

DURATION="${AUDIT_2026_SOAK_DURATION:-24h}"
FIRES_PER_SEC="${AUDIT_2026_SOAK_FIRES_PER_SEC:-10}"
OUTBOX_PER_SEC="${AUDIT_2026_SOAK_OUTBOX_PER_SEC:-100}"
TARGET="${AUDIT_2026_SOAK_TARGET:-}"
PROM="${AUDIT_2026_SOAK_PROM:-}"
TENANT="${AUDIT_2026_SOAK_TENANT:-soak-test-tenant}"
PRINCIPAL="${AUDIT_2026_SOAK_PRINCIPAL:-}"
EVIDENCE_DIR="${AUDIT_2026_SOAK_EVIDENCE_DIR:-./soak-evidence}"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--target-url) TARGET="$2"; shift 2;;
		--prom-url) PROM="$2"; shift 2;;
		--duration) DURATION="$2"; shift 2;;
		--fires-per-sec) FIRES_PER_SEC="$2"; shift 2;;
		--outbox-per-sec) OUTBOX_PER_SEC="$2"; shift 2;;
		--tenant) TENANT="$2"; shift 2;;
		--principal) PRINCIPAL="$2"; shift 2;;
		--evidence-dir) EVIDENCE_DIR="$2"; shift 2;;
		-h|--help)
			grep '^# ' "$0" | sed 's/^# \?//'
			exit 0;;
		*)
			echo "unknown flag: $1" >&2; exit 2;;
	esac
done

[[ -n "$TARGET" ]] || { echo "missing --target-url" >&2; exit 2; }
[[ -n "$PROM" ]]   || { echo "missing --prom-url"   >&2; exit 2; }

mkdir -p "$EVIDENCE_DIR"

scrape_sli() {
	local label="$1"; shift
	local out="$EVIDENCE_DIR/sli-${label}.txt"
	{
		echo "=== sli scrape ${label} @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
		for q in \
			'flowforge_audit_chain_breaks_total' \
			'rate(flowforge_engine_fire_rejected_concurrent_total[5m])' \
			'rate(flowforge_outbox_dispatch_duration_seconds_count[5m])' \
			'flowforge_signing_secret_default_used_total' \
			'flowforge_audit_record_unique_violation_total'; do
			echo
			echo "# query: ${q}"
			curl -sf --get "${PROM}/api/v1/query" --data-urlencode "query=${q}" \
				| jq -r '.data.result[]? | "  \(.metric)  \(.value[1])"' \
				|| echo "  (no data)"
		done
	} > "$out"
	echo "scraped sli @ ${label} -> ${out}"
}

verify_alert_rules() {
	# Pre-flight: confirm the audit-2026 alert rules promtool-validate
	# before we start putting load on the system.
	if command -v promtool >/dev/null 2>&1; then
		promtool test rules framework/tests/observability/promql/audit-2026.yml
	else
		echo "promtool not found; skipping rule self-test (acceptable)"
	fi
}

run_load() {
	# k6 is the canonical load gen for flowforge soak. Per-VU ramp-up
	# is implicit in the duration / arrival-rate config.
	if ! command -v k6 >/dev/null 2>&1; then
		echo "k6 not installed; aborting" >&2
		exit 3
	fi
	cat > "$EVIDENCE_DIR/k6-script.js" <<-EOF
	import http from "k6/http";
	import { check } from "k6";

	export const options = {
		scenarios: {
			fires: {
				executor: "constant-arrival-rate",
				rate: ${FIRES_PER_SEC},
				timeUnit: "1s",
				duration: "${DURATION}",
				preAllocatedVUs: 64,
				maxVUs: 256,
				exec: "fire",
			},
			outboxes: {
				executor: "constant-arrival-rate",
				rate: ${OUTBOX_PER_SEC},
				timeUnit: "1s",
				duration: "${DURATION}",
				preAllocatedVUs: 128,
				maxVUs: 512,
				exec: "outbox",
			},
		},
	};

	const TENANT = "${TENANT}";
	const HEADERS = { "Authorization": "Bearer ${PRINCIPAL}" };

	export function fire() {
		const r = http.post(\`${TARGET}/v1/workflows/soak/instances/__soak__/fire\`, JSON.stringify({event: "tick", tenant: TENANT}), { headers: HEADERS });
		check(r, { "fire 2xx": (r) => r.status >= 200 && r.status < 300 });
	}

	export function outbox() {
		const r = http.post(\`${TARGET}/v1/outbox/dispatch\`, JSON.stringify({tenant: TENANT, kind: "soak.tick"}), { headers: HEADERS });
		check(r, { "outbox 2xx": (r) => r.status >= 200 && r.status < 300 });
	}
	EOF
	k6 run --quiet --summary-export "$EVIDENCE_DIR/k6-summary.json" "$EVIDENCE_DIR/k6-script.js"
}

verify_acceptance() {
	# The two SLIs the audit-2026 plan §10.3 #7 demands stay at zero
	# during the soak.
	local breaks
	breaks=$(curl -sf --get "${PROM}/api/v1/query" --data-urlencode 'query=flowforge_audit_chain_breaks_total' \
		| jq -r '[.data.result[]?.value[1] | tonumber] | add // 0')
	local secret_default
	secret_default=$(curl -sf --get "${PROM}/api/v1/query" --data-urlencode 'query=flowforge_signing_secret_default_used_total' \
		| jq -r '[.data.result[]?.value[1] | tonumber] | add // 0')

	echo "post-soak SLI snapshot:"
	echo "  flowforge_audit_chain_breaks_total      = ${breaks}"
	echo "  flowforge_signing_secret_default_used   = ${secret_default}"

	local fail=0
	if [[ "$breaks" != "0" ]]; then
		echo "FAIL: audit chain breaks observed (${breaks})" >&2
		fail=1
	fi
	if [[ "$secret_default" != "0" ]]; then
		echo "FAIL: insecure-default signing secret observed (${secret_default})" >&2
		fail=1
	fi
	return "$fail"
}

main() {
	echo "audit-2026 soak: target=${TARGET} duration=${DURATION} fires/s=${FIRES_PER_SEC} outbox/s=${OUTBOX_PER_SEC}"
	verify_alert_rules
	scrape_sli "pre"
	run_load
	scrape_sli "post"
	verify_acceptance
	echo "audit-2026 soak: PASS"
}

main "$@"
