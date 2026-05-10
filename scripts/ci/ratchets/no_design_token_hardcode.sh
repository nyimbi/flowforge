#!/usr/bin/env bash
# scripts/ci/ratchets/no_design_token_hardcode.sh
#
# Ratchet for v0.3.0 W3 (item 18 of docs/improvements.md).
#
# Background. The W3 design-token generator emits the canonical hex
# palette into ``design_tokens.css``; every other generated frontend
# artefact (Step.tsx, admin App.tsx / pages, layouts, Tailwind config,
# theme.ts) must consume the palette via ``var(--color-primary)`` /
# ``var(--color-accent)`` / ``var(--radius-*)`` references rather than
# inlining a hex literal. A future change that bakes a hex back into a
# template re-introduces the "every generated app looks identical" bug
# the design-token block is meant to solve.
#
# Heuristic. Grep the customer-facing real-path Step template plus the
# admin templates for hex colour literals (`#RGB`, `#RRGGBB`,
# `#RRGGBBAA`). Skip the canonical token files where literal hex
# legitimately lives:
#
#   * ``design_tokens.css`` — the source of truth for the palette.
#   * ``theme.ts`` — exports a ``defaults`` block of generation-pinned
#     hex strings for SSR / node consumers that cannot read CSS
#     variables. The same module's ``tokens`` export already uses
#     ``var(--…)`` references, so the literal hex stays scoped to the
#     fallback path.
#
# Also walk the *generated* outputs under
# ``examples/*/generated/frontend/**`` and
# ``examples/*/generated/frontend-admin/**`` so a regen that bakes a
# hex back into the rendered file fails CI before merge.
#
# Add a legitimate exception by appending the matching path:line:text to
# ``no_design_token_hardcode_baseline.txt``; landing such a line
# requires a v0.3.0-engineering visual-design review.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/no_design_token_hardcode_baseline.txt"

# The pattern matches `#` followed by 3, 6, or 8 hex digits with a
# trailing word boundary so `#abcdefg` doesn't masquerade as #abcdef.
HEX_PATTERN='#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b'

# Template paths grepped. The customer-facing frontend's Step.tsx.j2 +
# every file under frontend_admin/ except the design-token templates
# themselves (which are the canonical hex source). Some checkouts host
# the framework tree under a parent ``framework/`` dir; fall back if the
# bare path is missing.
TEMPLATE_BASE="$REPO_ROOT/python/flowforge-cli/src/flowforge_cli/jtbd/templates"
if [[ ! -d "$TEMPLATE_BASE" ]]; then
	TEMPLATE_BASE="$REPO_ROOT/framework/python/flowforge-cli/src/flowforge_cli/jtbd/templates"
fi

if [[ ! -d "$TEMPLATE_BASE" ]]; then
	echo "no_design_token_hardcode: templates dir not found; nothing to check"
	exit 0
fi

# Build the list of template files to grep:
#   * frontend/Step.tsx.j2 (real path is the design-token consumer)
#   * frontend_admin/**/*.{tsx,html,ts}.j2 except design_tokens.css.j2
TEMPLATE_PATHS=()
STEP_TEMPLATE="$TEMPLATE_BASE/frontend/Step.tsx.j2"
if [[ -f "$STEP_TEMPLATE" ]]; then
	TEMPLATE_PATHS+=("$STEP_TEMPLATE")
fi

while IFS= read -r path; do
	[[ -z "$path" ]] && continue
	# Skip the canonical token template (literal hex source) and
	# theme.ts (its ``defaults`` block carries SSR / node fallback hex
	# values pinned at generation time; the same module's ``tokens``
	# export already reaches through CSS variables).
	case "$path" in
		*design_tokens/design_tokens.css.j2) continue ;;
		*design_tokens/theme.ts.j2) continue ;;
	esac
	TEMPLATE_PATHS+=("$path")
done < <(
	find "$TEMPLATE_BASE/frontend_admin" \
		\( -name "*.tsx.j2" -o -name "*.ts.j2" -o -name "*.html.j2" \) \
		-type f 2>/dev/null
)

violations=0

for path in ${TEMPLATE_PATHS[@]+"${TEMPLATE_PATHS[@]}"}; do
	[[ -f "$path" ]] || continue
	rel="${path#${REPO_ROOT}/}"
	matches=$(grep -nE "$HEX_PATTERN" "$path" 2>/dev/null || true)
	[[ -z "$matches" ]] && continue
	while IFS= read -r match; do
		[[ -z "$match" ]] && continue
		line_num="${match%%:*}"
		text="${match#*:}"
		formatted="${rel}:${line_num}:${text}"
		if grep -Fq "$formatted" "$BASELINE" 2>/dev/null; then
			continue
		fi
		echo "no_design_token_hardcode: $formatted"
		violations=$((violations + 1))
	done <<< "$matches"
done

# Also scan generated outputs so a regen that bakes a hex back in fails
# before merge. Skip the canonical ``design_tokens.css`` files that
# legitimately carry the hex palette.
GENERATED_FILES=()
while IFS= read -r path; do
	[[ -z "$path" ]] && continue
	# Skip the canonical hex carriers — design_tokens.css (palette
	# source) and theme.ts (SSR fallback block of generation-pinned
	# hex values).
	case "$path" in
		*/design_tokens.css) continue ;;
		*/theme.ts) continue ;;
	esac
	GENERATED_FILES+=("$path")
done < <(
	find "$REPO_ROOT/examples" \
		\( -path "*/generated/frontend/*" -o -path "*/generated/frontend-admin/*" \) \
		\( -name "*.tsx" -o -name "*.ts" -o -name "*.html" -o -name "*.css" \) \
		-type f 2>/dev/null
)

for path in ${GENERATED_FILES[@]+"${GENERATED_FILES[@]}"}; do
	rel="${path#${REPO_ROOT}/}"
	matches=$(grep -nE "$HEX_PATTERN" "$path" 2>/dev/null || true)
	[[ -z "$matches" ]] && continue
	while IFS= read -r match; do
		[[ -z "$match" ]] && continue
		line_num="${match%%:*}"
		text="${match#*:}"
		formatted="${rel}:${line_num}:${text}"
		if grep -Fq "$formatted" "$BASELINE" 2>/dev/null; then
			continue
		fi
		echo "no_design_token_hardcode: $formatted"
		violations=$((violations + 1))
	done <<< "$matches"
done

if (( violations > 0 )); then
	echo "no_design_token_hardcode: $violations violation(s); reference design tokens via var(--color-primary) instead"
	echo "  see scripts/ci/ratchets/README.md and add legitimate exceptions to $BASELINE"
	exit 1
fi

exit 0
