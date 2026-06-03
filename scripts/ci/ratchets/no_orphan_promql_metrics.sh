#!/usr/bin/env bash
# scripts/ci/ratchets/no_orphan_promql_metrics.sh
#
# E-75: verify every metric name referenced in the PromQL alert file has
# at least one emitter in the Python source tree.
#
# Parses metric names from `expr:` blocks in audit-2026.yml by extracting
# bare metric names (identifiers that look like flowforge_*) from expr lines,
# then greps the Python source tree for each name.  Exits 1 if any metric
# name has no source emitter.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

PROMQL_FILE="$REPO_ROOT/tests/observability/promql/audit-2026.yml"
PYTHON_SRC="$REPO_ROOT/python"

if [[ ! -f "$PROMQL_FILE" ]]; then
	echo "ERROR: PromQL alert file not found: $PROMQL_FILE" >&2
	exit 1
fi

# Extract metric names from expr: blocks.
# Strategy: grab all words matching flowforge_[a-z0-9_]+ from expr lines,
# strip PromQL suffixes (_bucket, _total, _count, _sum) only when the base
# name without suffix is the canonical emitter name.
# We keep the full name (including _total/_bucket) since that is what the
# Python emitters reference verbatim.
METRIC_NAMES=$(grep -E '^\s+(expr|increase|rate|sum|histogram_quantile)' "$PROMQL_FILE" | \
	grep -oE 'flowforge_[a-z0-9_]+' | sort -u)

if [[ -z "$METRIC_NAMES" ]]; then
	echo "WARNING: no metric names extracted from $PROMQL_FILE" >&2
	exit 0
fi

# Known framework-internal histogram metrics that are tracked via the OTEL/metrics
# port under a dotted name convention (e.g. "flowforge.outbox.dispatch.duration_seconds")
# rather than a direct emit() call with the underscore PromQL name.
# These are legitimately cross-referenced — the port constant and the PromQL name
# both refer to the same histogram but use different separator conventions.
# Add to this list only with a comment explaining the cross-reference.
KNOWN_FRAMEWORK_HISTOGRAMS=(
	"flowforge_outbox_dispatch_duration_seconds_bucket"  # OUTBOX_DISPATCH_DURATION_HISTOGRAM in ports/metrics.py (dotted form)
)

FAILED=()

while IFS= read -r metric; do
	# Check known framework histogram exceptions first.
	skip=0
	for known in "${KNOWN_FRAMEWORK_HISTOGRAMS[@]}"; do
		if [[ "$metric" == "$known" ]]; then
			skip=1
			break
		fi
	done
	if (( skip )); then
		continue
	fi

	# Strip PromQL histogram suffixes — the emitter uses the base name.
	base="${metric%_bucket}"
	base="${base%_count}"
	base="${base%_sum}"

	# Search for the metric name (or base name) in Python sources.
	if grep -rq --include="*.py" "$metric" "$PYTHON_SRC" 2>/dev/null; then
		continue
	fi
	if [[ "$base" != "$metric" ]] && grep -rq --include="*.py" "$base" "$PYTHON_SRC" 2>/dev/null; then
		continue
	fi
	FAILED+=("$metric")
done <<< "$METRIC_NAMES"

if (( ${#FAILED[@]} > 0 )); then
	echo "ERROR: the following PromQL alert metrics have no emitter in Python source:" >&2
	for m in "${FAILED[@]}"; do
		echo "  - $m" >&2
	done
	echo "" >&2
	echo "Each metric name must appear in at least one .py file under python/." >&2
	echo "Add emit() calls or update the PromQL file if the metric was renamed." >&2
	exit 1
fi

echo "OK: all PromQL alert metrics have source emitters (${#METRIC_NAMES} checked)"
