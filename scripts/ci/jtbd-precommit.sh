#!/usr/bin/env bash
# jtbd-precommit.sh — pre-commit hook for JTBD bundle linting (E-9 / v0.4.0 E2).
#
# Runs `flowforge jtbd lint --strict` on every jtbd-bundle.json (or
# jtbd_bundle.json) file that is staged for commit. Blocks the commit if
# any bundle has lint errors or warnings (strict mode).
#
# Install as a git pre-commit hook:
#   cp scripts/ci/jtbd-precommit.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Or via pre-commit framework (.pre-commit-config.yaml):
#   - repo: local
#     hooks:
#       - id: jtbd-lint
#         name: JTBD bundle lint
#         language: system
#         entry: bash scripts/ci/jtbd-precommit.sh
#         pass_filenames: false
#
# Exit codes:
#   0  — all staged bundles are clean
#   1  — one or more bundles have lint errors/warnings

set -euo pipefail

# Collect staged bundle files (added, modified, renamed).
staged_bundles=$(git diff --cached --name-only --diff-filter=ACM \
	| grep -E '(jtbd[-_]bundle\.json|jtbd[-_]bundle\.yaml)$' \
	|| true)

if [ -z "$staged_bundles" ]; then
	# Nothing to lint — fast path.
	exit 0
fi

# Verify the CLI is available.
if ! command -v flowforge &>/dev/null && ! uv run flowforge --version &>/dev/null 2>&1; then
	echo "jtbd-precommit: flowforge CLI not found — skipping JTBD lint." >&2
	exit 0
fi

_run_flowforge() {
	if command -v flowforge &>/dev/null; then
		flowforge "$@"
	else
		uv run flowforge "$@"
	fi
}

failed=0
while IFS= read -r bundle; do
	[ -z "$bundle" ] && continue
	if [ ! -f "$bundle" ]; then
		# File was deleted — skip.
		continue
	fi
	echo "jtbd-precommit: linting $bundle …"
	if _run_flowforge jtbd lint --strict "$bundle"; then
		echo "jtbd-precommit: $bundle ok"
	else
		echo "jtbd-precommit: $bundle FAILED" >&2
		failed=$((failed + 1))
	fi
done <<< "$staged_bundles"

if [ "$failed" -gt 0 ]; then
	echo "" >&2
	echo "jtbd-precommit: $failed bundle(s) failed lint. Fix errors before committing." >&2
	echo "  Run: flowforge jtbd lint --strict <bundle_path> to see details." >&2
	exit 1
fi

exit 0
