#!/usr/bin/env bash
# scripts/ci/regen_flag_flip.sh
#
# v0.3.0 W2 closeout helper: regen-diff loop on the 3 example bundles
# crossed with both ``form_renderer`` flag values (skeleton | real).
#
# For every (example, flag) pair:
#   * copy the example bundle to a worktree-local scratch dir,
#   * patch ``project.frontend.form_renderer`` to the target flag,
#   * generate twice into separate dirs from the same patched bundle,
#   * diff the two outputs — must be byte-identical (self-determinism).
#
# Reference: docs/v0.3.0-engineering-plan.md §7 W2 acceptance gates.
# Closeout protocol mirrors the W1 commit (942ff22) cross-flag check.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

OUT_ROOT="$REPO_ROOT/.omc/state/regen-flag-flip"
rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

EXAMPLES=(insurance_claim building-permit hiring-pipeline)
FLAGS=(skeleton real)

FAIL=0
for flag in "${FLAGS[@]}"; do
	for ex in "${EXAMPLES[@]}"; do
		bundle="$OUT_ROOT/$ex.$flag.bundle.json"
		cp "examples/$ex/jtbd-bundle.json" "$bundle"
		uv run python -c "
import json,sys
p='$bundle'
b=json.load(open(p))
proj=b.setdefault('project',{})
proj.setdefault('frontend',{})['form_renderer']='$flag'
json.dump(b,open(p,'w'),indent=2,ensure_ascii=False)
" || exit 1
		mkdir -p "$OUT_ROOT/run1/$flag/$ex" "$OUT_ROOT/run2/$flag/$ex"
		uv run flowforge jtbd-generate --jtbd "$bundle" --out "$OUT_ROOT/run1/$flag/$ex" --force >/dev/null 2>&1
		uv run flowforge jtbd-generate --jtbd "$bundle" --out "$OUT_ROOT/run2/$flag/$ex" --force >/dev/null 2>&1
		if diff -rq --exclude='*.pyc' --exclude='__pycache__' \
			"$OUT_ROOT/run1/$flag/$ex" "$OUT_ROOT/run2/$flag/$ex" >/dev/null 2>&1; then
			echo "  $ex x form_renderer=$flag : self-deterministic OK"
		else
			echo "  $ex x form_renderer=$flag : DRIFT"
			diff -rq --exclude='*.pyc' --exclude='__pycache__' \
				"$OUT_ROOT/run1/$flag/$ex" "$OUT_ROOT/run2/$flag/$ex" | head -10
			FAIL=1
		fi
	done
done

if (( FAIL == 0 )); then
	echo "regen flag-flip: 6/6 byte-identical (3 examples x 2 flag values)"
fi
exit $FAIL
