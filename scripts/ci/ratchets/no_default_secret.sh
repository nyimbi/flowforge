#!/usr/bin/env bash
# scripts/ci/ratchets/no_default_secret.sh
#
# Ratchet for audit finding SK-01 (audit-fix-plan §4.1, ticket E-34).
#
# Forbids any module-level default value for `FLOWFORGE_SIGNING_SECRET` or
# any obviously-hard-coded HMAC dev secret string. Matches must either
# (a) live in scripts/ci/ratchets/baseline.txt or (b) be removed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/baseline.txt"

cd "$REPO_ROOT"

# Patterns:
#  - default = "anything-with-a-secret-shape" assigned to the env-var
#  - hmac dev secret literal "flowforge-dev-secret" or similar marker strings
#  - `os.environ.setdefault("FLOWFORGE_SIGNING_SECRET", ...)`
PATTERNS=(
	'FLOWFORGE_SIGNING_SECRET[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']{8,}["'"'"']'
	'os\.environ\.setdefault\([[:space:]]*["'"'"']FLOWFORGE_SIGNING_SECRET'
	'flowforge-dev-secret'
	'change-?me-?in-?prod'
)

# Search only inside framework/python (runtime + tests) and scripts/.
# Tests under tests/audit_2026/ are explicitly *allowed* to reference these
# strings as the regression-test bank (test_SK_01_*).
SEARCH_ROOTS=(
	"framework/python"
	"backend/app"
	"scripts"
)

EXCLUDES=(
	":(exclude)framework/tests/audit_2026"
	":(exclude)scripts/ci/ratchets"
	":(exclude)**/__pycache__/**"
	":(exclude)**/.venv/**"
	":(exclude)**/node_modules/**"
)

violations=0

for pat in "${PATTERNS[@]}"; do
	# git grep is faster + respects .gitignore + supports pathspecs
	matches=$(git grep -n -E "$pat" -- "${SEARCH_ROOTS[@]}" "${EXCLUDES[@]}" 2>/dev/null || true)
	if [[ -z "$matches" ]]; then
		continue
	fi
	# Filter against baseline
	while IFS= read -r line; do
		[[ -z "$line" ]] && continue
		if grep -Fq "$line" "$BASELINE" 2>/dev/null; then
			continue
		fi
		echo "no_default_secret: $line"
		violations=$((violations + 1))
	done <<< "$matches"
done

if (( violations > 0 )); then
	echo "no_default_secret: $violations new violation(s); land via E-34 or update baseline.txt with security-team review."
	exit 1
fi
exit 0
