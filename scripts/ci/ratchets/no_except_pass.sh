#!/usr/bin/env bash
# scripts/ci/ratchets/no_except_pass.sh
#
# Ratchet for audit findings J-10, JH-06, CL-04 (audit-fix-plan §4.3).
# Forbids the `except Exception: pass` idiom and friends — bare `except:`,
# `except BaseException: pass`. These swallow real bugs.
#
# The narrow legitimate use (intentional best-effort cleanup) must be
# rewritten as `except (Specific, Errors) as e: log.debug(..., exc_info=e)`
# or moved to baseline.txt with security-team review.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASELINE="$SCRIPT_DIR/baseline.txt"

cd "$REPO_ROOT"

# Match `except X:` followed (within the next non-blank line) by `pass`.
# git grep can't match across lines, so we use a Python helper for accuracy.

python3 - "$REPO_ROOT" "$BASELINE" <<'PY'
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
baseline_path = Path(sys.argv[2])

baseline_lines: set[str] = set()
if baseline_path.exists():
	for raw in baseline_path.read_text(encoding="utf-8").splitlines():
		stripped = raw.strip()
		if not stripped or stripped.startswith("#"):
			continue
		# baseline lines are stored as `<ratchet>: <path:line:text>`. The
		# ratchet name prefix is informational; the comparison key is the
		# `<path:line:text>` tail.
		if ":" in stripped:
			head, _, tail = stripped.partition(":")
			if head.startswith("no_") or head.startswith("ratchet"):
				stripped = tail.strip()
		baseline_lines.add(stripped)

EXCEPT_RE = re.compile(
	r"^(?P<indent>[\t ]*)except\b[^:]*:[\t ]*(?:#.*)?$"
)
SEARCH_ROOTS = [
	repo_root / "framework" / "python",
	repo_root / "backend" / "app",
]
EXCLUDE_PARTS = {
	"__pycache__",
	".venv",
	"node_modules",
	"audit_2026",   # tests/audit_2026 may exercise patterns
}

violations: list[str] = []

for root in SEARCH_ROOTS:
	if not root.exists():
		continue
	for path in root.rglob("*.py"):
		if any(part in EXCLUDE_PARTS for part in path.parts):
			continue
		try:
			lines = path.read_text(encoding="utf-8").splitlines()
		except (OSError, UnicodeDecodeError):
			continue
		i = 0
		while i < len(lines):
			m = EXCEPT_RE.match(lines[i])
			if not m:
				i += 1
				continue
			# look ahead for the next non-blank, non-comment line
			j = i + 1
			while j < len(lines):
				nxt = lines[j].strip()
				if nxt and not nxt.startswith("#"):
					break
				j += 1
			if j < len(lines):
				body = lines[j].strip()
				is_pass_only = body in ("pass",)
				is_bare_or_broad = bool(re.match(r"^[\t ]*except[\t ]*(Exception|BaseException)?[\t ]*:", lines[i]))
				if is_pass_only and is_bare_or_broad:
					rel = path.relative_to(repo_root)
					marker = f"{rel}:{i + 1}:{lines[i].strip()}"
					if marker not in baseline_lines:
						violations.append(f"no_except_pass: {marker}")
			i = j + 1

for v in violations:
	print(v)

if violations:
	print(f"no_except_pass: {len(violations)} new violation(s); narrow the except or update baseline.txt with security-team review.", file=sys.stderr)
	sys.exit(1)
sys.exit(0)
PY
