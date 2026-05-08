#!/usr/bin/env bash
# scripts/ci/ratchets/no_string_interp_sql.sh
#
# Ratchet for audit findings T-01, J-01, OB-01 (audit-fix-plan §4.1/4.2).
# Forbids f-string / .format() / `%` interpolation directly inside SQL strings
# in runtime code. Bound parameters (`:k`, `%s`, sqlalchemy text(":x")) are the
# only acceptable injection-safe path.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/baseline.txt"

cd "$REPO_ROOT"

# Heuristic patterns. Intentionally conservative — false positives are
# expected to land in baseline.txt with a justification.
PATTERNS=(
	# f-string with SQL keyword inline
	'f["'"'"'].*\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|SET[[:space:]]+(LOCAL|SESSION))\b'
	# .format() called on an SQL-shaped string
	'["'"'"'].*\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b.*["'"'"']\.format\('
	# % interpolation against an SQL keyword
	'["'"'"'].*\b(SELECT|INSERT|UPDATE|DELETE)\b.*["'"'"'][[:space:]]*%[[:space:]]*[\(\{a-zA-Z_]'
)

SEARCH_ROOTS=(
	"framework/python"
	"backend/app"
)

EXCLUDES=(
	":(exclude)framework/tests/audit_2026"
	":(exclude)framework/tests/property"
	":(exclude)scripts/ci/ratchets"
	":(exclude)**/__pycache__/**"
	":(exclude)**/.venv/**"
	":(exclude)**/migrations/**"
	":(exclude)**/alembic/**"
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
		echo "no_string_interp_sql: $line"
		violations=$((violations + 1))
	done <<< "$matches"
done

if (( violations > 0 )); then
	echo "no_string_interp_sql: $violations new violation(s); use bound params (:k / sqlalchemy text+bindparams) or update baseline.txt with security-team review."
	exit 1
fi
exit 0
