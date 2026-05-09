#!/usr/bin/env bash
# scripts/ci/ratchets/no_idempotency_bypass.sh
#
# Ratchet for v0.3.0 W2b (item 6, invariant 11 of
# docs/v0.3.0-engineering-plan.md §8).
#
# Background. The W2b idempotency-key gate enforces an
# ``Idempotency-Key`` header on every generated ``POST /<jtbd>/events``
# route. The router template (`domain_router.py.j2`) imports the
# per-JTBD ``check_idempotency_key`` / ``record_idempotency_response``
# helpers and rejects missing headers with 400. If a future change to
# the template silently drops the import or the gate, invariant 11 is
# bypassed and duplicate fires can race the engine.
#
# Heuristic. The ratchet greps the router template for the gate
# tokens; absent any of them, the template is bypassed. It also greps
# the *generated* router output committed under examples/*/generated/
# so a regen that drops the wiring trips CI before merge.
#
# Tokens grepped (intentionally narrow — false positives go in the
# baseline file with security/architecture review):
#
#   POST /events handler                — `@router.post("/events")`
#   header parameter                    — `Idempotency-Key`
#   helper import                       — `check_idempotency_key`
#   record-on-success                   — `record_idempotency_response`
#   missing-key 400                     — `HTTP_400_BAD_REQUEST`
#   in-flight 409                       — `HTTP_409_CONFLICT`
#
# Add a legitimate exception by appending the matching path:line:text to
# `no_idempotency_bypass_baseline.txt`; landing such a line requires a
# v0.3.0-engineering security/architecture review.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/no_idempotency_bypass_baseline.txt"

TEMPLATE_REL="python/flowforge-cli/src/flowforge_cli/jtbd/templates/domain_router.py.j2"
TEMPLATE_PATH="$REPO_ROOT/$TEMPLATE_REL"
if [[ ! -f "$TEMPLATE_PATH" ]]; then
	# Some checkouts host this tree under a `framework/` parent.
	TEMPLATE_PATH="$REPO_ROOT/framework/$TEMPLATE_REL"
fi

if [[ ! -f "$TEMPLATE_PATH" ]]; then
	echo "no_idempotency_bypass: domain_router.py.j2 not found at $TEMPLATE_REL"
	exit 1
fi

REQUIRED_TOKENS=(
	'Idempotency-Key'
	'check_idempotency_key'
	'record_idempotency_response'
	'HTTP_400_BAD_REQUEST'
	'HTTP_409_CONFLICT'
)

violations=0
for tok in "${REQUIRED_TOKENS[@]}"; do
	if ! grep -qF "$tok" "$TEMPLATE_PATH"; then
		echo "no_idempotency_bypass: domain_router.py.j2 missing required token: $tok"
		violations=$((violations + 1))
	fi
done

# Generated routers under examples/*/generated/**/routers/*_router.py must
# also carry the gate. A regen that drops the wiring should fail before
# merge. We accept the tokens being present in the rendered file (POST
# /events implies the gate ran).
#
# Portable across macOS bash 3.2: no `mapfile`. Iterate via while-read.
GENERATED_ROUTERS=()
while IFS= read -r router; do
	[[ -z "$router" ]] && continue
	GENERATED_ROUTERS+=("$router")
done < <(
	find "$REPO_ROOT/examples" \
		-path "*/generated/*/routers/*_router.py" \
		-type f 2>/dev/null
)

for router in ${GENERATED_ROUTERS[@]+"${GENERATED_ROUTERS[@]}"}; do
	rel="${router#${REPO_ROOT}/}"
	# Only enforce on routers that expose POST /events — generators may
	# emit non-event routers later; those should be skipped by this
	# heuristic.
	if ! grep -q '@router.post("/events")' "$router"; then
		continue
	fi
	for tok in "${REQUIRED_TOKENS[@]}"; do
		if ! grep -qF "$tok" "$router"; then
			line=$(grep -nF '@router.post("/events")' "$router" | head -1 | cut -d: -f1)
			formatted="${rel}:${line:-1}:${tok}"
			if grep -Fq "$formatted" "$BASELINE" 2>/dev/null; then
				continue
			fi
			echo "no_idempotency_bypass: $formatted (POST /events handler missing $tok)"
			violations=$((violations + 1))
		fi
	done
done

if (( violations > 0 )); then
	echo "no_idempotency_bypass: $violations violation(s); see scripts/ci/ratchets/README.md"
	exit 1
fi

exit 0
