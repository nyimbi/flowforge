#!/usr/bin/env bash
# scripts/ci/ratchets/no_unparried_expr_in_step_template.sh
#
# Ratchet for v0.3.0 W1 (item 13, pre-mortem scenario 2 of
# docs/v0.3.0-engineering-plan.md).
#
# Background. The W1 form_renderer="real" Step.tsx emission path may
# inline JSON-DSL expression fragments (`{var: "context.X"}`,
# `{"==": [...]}`, etc.) for show_if-shaped conditional visibility.
# Such fragments evaluate in BOTH the Python engine (server-side gate)
# and the TS @flowforge/renderer (client-side conditional render). If
# the cross-runtime parity fixture (tests/cross_runtime/fixtures/
# expr_parity_v2.json) is not extended in the same PR that adds new
# expression shapes to the template, invariant 5 fails on production.
#
# Heuristic. Count expression-shaped JSON-DSL tokens emitted by the
# template. If any are present, fixture v2 must exist and have at
# least 50 conditional-tagged cases (the W1 floor; raise as the
# template gains complexity).
#
# Tokens grepped (intentionally narrow — false positives go in the
# baseline file with security/architecture review):
#
#   {"var":          – JSON-shape variable read
#   {"==": [         – JSON-shape equality
#   {"!=": [         – JSON-shape inequality
#   {"and": [        – JSON-shape conjunction
#   {"or": [         – JSON-shape disjunction
#   {"not": [        – JSON-shape negation
#   {"if": [         – JSON-shape conditional
#   {"in": [         – JSON-shape membership
#   {"not_null": [   – JSON-shape null-check
#   {"coalesce": [   – JSON-shape coalesce
#   "var:            – DSL-style variable token (`{var: "context.X"}` minified)
#   "op:             – DSL-style op token
#
# Add a legitimate exception by appending the matching path:line:text to
# `no_unparried_expr_in_step_template_baseline.txt`; landing such a line
# requires the fixture-v2 update in the same PR.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/no_unparried_expr_in_step_template_baseline.txt"
TEMPLATE_PATH_REL="framework/python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2"
FIXTURE_V2_REL="framework/tests/cross_runtime/fixtures/expr_parity_v2.json"

# Some checkouts host this tree at the repo root rather than under a
# `framework/` parent; fall back to the bare path if the namespaced one
# is missing.
TEMPLATE_PATH="$REPO_ROOT/$TEMPLATE_PATH_REL"
if [[ ! -f "$TEMPLATE_PATH" ]]; then
	TEMPLATE_PATH="$REPO_ROOT/python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2"
fi
FIXTURE_V2="$REPO_ROOT/$FIXTURE_V2_REL"
if [[ ! -f "$FIXTURE_V2" ]]; then
	FIXTURE_V2="$REPO_ROOT/tests/cross_runtime/fixtures/expr_parity_v2.json"
fi

if [[ ! -f "$TEMPLATE_PATH" ]]; then
	echo "no_unparried_expr_in_step_template: Step.tsx.j2 not found; nothing to check"
	exit 0
fi

PATTERNS=(
	'\{"var":'
	'\{"==": \['
	'\{"!=": \['
	'\{"and": \['
	'\{"or": \['
	'\{"not": \['
	'\{"if": \['
	'\{"in": \['
	'\{"not_null": \['
	'\{"coalesce": \['
	'"var:'
	'"op:'
)

violations=0
expr_tokens=0

for pat in "${PATTERNS[@]}"; do
	matches=$(grep -nE "$pat" "$TEMPLATE_PATH" 2>/dev/null || true)
	[[ -z "$matches" ]] && continue
	while IFS= read -r line; do
		[[ -z "$line" ]] && continue
		# Format the recorded line as `<rel-path>:<line>:<text>` so it
		# matches the baseline format the other ratchets use.
		formatted="${TEMPLATE_PATH#${REPO_ROOT}/}:$line"
		if grep -Fq "$formatted" "$BASELINE" 2>/dev/null; then
			expr_tokens=$((expr_tokens + 1))
			continue
		fi
		# Treat every match as a token to count; the paired-fixture
		# check below decides whether to fail.
		expr_tokens=$((expr_tokens + 1))
		echo "no_unparried_expr_in_step_template: $formatted"
	done <<< "$matches"
done

if (( expr_tokens == 0 )); then
	exit 0
fi

# Expression tokens present — fixture v2 must exist with >=50 conditional cases.
if [[ ! -f "$FIXTURE_V2" ]]; then
	echo "no_unparried_expr_in_step_template: $expr_tokens expr token(s) in Step.tsx.j2 but $FIXTURE_V2_REL is missing — invariant 5 at risk."
	exit 1
fi

# Count `"tag": "conditional"` lines as a cheap proxy for the case
# count. A more rigorous check would parse JSON, but the file is
# generated via _build_fixture_v2.py and the line shape is stable.
conditional_cases=$(grep -c '"tag": "conditional"' "$FIXTURE_V2" || true)

if (( conditional_cases < 50 )); then
	echo "no_unparried_expr_in_step_template: Step.tsx.j2 has $expr_tokens expression token(s) but fixture v2 only carries $conditional_cases conditional case(s); need >= 50."
	echo "  rebuild via: uv run python framework/tests/cross_runtime/_build_fixture_v2.py"
	exit 1
fi

if (( conditional_cases < expr_tokens )); then
	echo "no_unparried_expr_in_step_template: $expr_tokens expression token(s) in Step.tsx.j2 outpace $conditional_cases conditional fixture case(s); add coverage."
	exit 1
fi

# All constraints satisfied — token count <= conditional case count, and
# fixture v2 has the required floor.
exit 0
