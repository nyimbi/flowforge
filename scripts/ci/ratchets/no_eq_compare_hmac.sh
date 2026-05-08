#!/usr/bin/env bash
# scripts/ci/ratchets/no_eq_compare_hmac.sh
#
# Ratchet for audit finding NM-01 (audit-fix-plan §4.2, ticket E-54).
# Forbids `==` / `!=` comparisons against the output of hmac.new(...).digest()
# or .hexdigest(). HMAC comparisons must use hmac.compare_digest to avoid
# timing side-channels.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/baseline.txt"

cd "$REPO_ROOT"

PATTERNS=(
	# `hmac.new(...).digest() == something` or its hex variant
	'hmac\.new\([^)]*\)\.(hex)?digest\(\)[[:space:]]*[!=]='
	'[!=]=[[:space:]]*hmac\.new\([^)]*\)\.(hex)?digest\(\)'
	# generic signature-shaped variable named `*signature*` or `*mac*` compared with ==
	'\b(expected|computed)_(sig|mac|hmac|signature)\b[[:space:]]*[!=]='
)

SEARCH_ROOTS=(
	"framework/python"
	"backend/app"
)

EXCLUDES=(
	":(exclude)framework/tests/audit_2026"
	":(exclude)scripts/ci/ratchets"
	":(exclude)**/__pycache__/**"
	":(exclude)**/.venv/**"
)

violations=0

for pat in "${PATTERNS[@]}"; do
	matches=$(git grep -n -E "$pat" -- "${SEARCH_ROOTS[@]}" "${EXCLUDES[@]}" 2>/dev/null || true)
	[[ -z "$matches" ]] && continue
	while IFS= read -r line; do
		[[ -z "$line" ]] && continue
		if grep -Fq "$line" "$BASELINE" 2>/dev/null; then
			continue
		fi
		echo "no_eq_compare_hmac: $line"
		violations=$((violations + 1))
	done <<< "$matches"
done

if (( violations > 0 )); then
	echo "no_eq_compare_hmac: $violations new violation(s); switch to hmac.compare_digest or update baseline.txt with security-team review."
	exit 1
fi
exit 0
