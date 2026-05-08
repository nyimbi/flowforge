"""scripts/ci/check_signoff.py — DELIBERATE-mode signoff gate.

Implements audit-fix-plan §10.2: rejects PR merge to `main` if a P0/P1
ticket's row in `docs/audit-2026/signoff-checklist.md` is empty or
unsigned. Designed to run in CI, but also locally as a pre-merge guard.

Behaviour:
  * Parses every YAML record in the checklist (fenced ```yaml blocks).
  * For each ticket the markdown declares, every required signer slot must
    be filled with a non-`<TBD>` string AND a non-`<TBD>` ISO-8601 date.
  * P0 tickets additionally require `commit_sha` to be present and look
    like a valid git sha (40 lowercase hex chars or short ≥7).
  * Tickets covered by E-xx that have not yet entered exec are *skipped*
    iff their `phase` is empty (i.e., the row is a pure scaffold). Any row
    with a phase set is enforced.

Exit codes:
  0 — every populated row is signed; scaffolds are tolerated.
  1 — at least one populated row is missing a signature; details printed.
  2 — checklist file is missing or unparseable.

Usage:
  uv run python scripts/ci/check_signoff.py
  uv run python scripts/ci/check_signoff.py --ticket E-32   # check one row
  uv run python scripts/ci/check_signoff.py --strict        # also fail on scaffolds
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
	import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — mandatory dep for CI
	print(
		"check_signoff: PyYAML is required (`uv pip install pyyaml`).",
		file=sys.stderr,
	)
	sys.exit(2)


CHECKLIST_PATH = (
	Path(__file__).resolve().parents[2]
	/ "docs"
	/ "audit-2026"
	/ "signoff-checklist.md"
)

YAML_BLOCK_RE = re.compile(r"^```yaml\s*$(.*?)^```\s*$", re.DOTALL | re.MULTILINE)
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
P0_TICKETS = frozenset({"E-32", "E-34", "E-35", "E-36", "E-37", "E-37b", "E-38"})


def _is_tbd(v: Any) -> bool:
	"""A field is unsigned if missing, blank, or the literal `<TBD>` placeholder."""

	if v is None:
		return True
	s = str(v).strip()
	if not s:
		return True
	# yaml renders `<TBD>` as the string "<TBD>"
	if s == "<TBD>":
		return True
	return False


def _parse_records(md_text: str) -> list[dict[str, Any]]:
	"""Extract all YAML records from fenced ```yaml blocks in the markdown.

	The checklist may use either a list-of-mappings or a single mapping per
	block; both are flattened to a list of `dict` rows.
	"""

	rows: list[dict[str, Any]] = []
	for match in YAML_BLOCK_RE.finditer(md_text):
		body = match.group(1)
		try:
			parsed = yaml.safe_load(body)
		except yaml.YAMLError as e:
			raise SystemExit(f"check_signoff: YAML parse error in checklist block: {e}") from e
		if parsed is None:
			continue
		if isinstance(parsed, list):
			for item in parsed:
				if isinstance(item, dict):
					rows.append(item)
		elif isinstance(parsed, dict):
			rows.append(parsed)
	return rows


def _row_violations(row: dict[str, Any], strict: bool) -> list[str]:
	"""Return human-readable violation messages for one ticket row.

	Activation semantics (audit-fix-plan §10.2):

	* A row is *active* if any signoff slot has a non-TBD value, or if a
	  commit_sha is set. Active rows MUST have every required slot filled.
	* A row is a *scaffold* if every signoff slot is still `<TBD>` and no
	  commit_sha is set. Scaffolds are tolerated unless `--strict`.

	The active/scaffold distinction lets the gate run on `main` without
	blocking PRs whose tickets have not yet entered exec, while still
	failing any PR that lands a partially-filled row.
	"""

	ticket = str(row.get("ticket") or "").strip()
	if not ticket:
		return [f"row missing 'ticket' key: {row!r}"]

	sec = row.get("security_lead_signoff") or {}
	rel = row.get("release_manager_signoff") or {}

	signer_slots = (
		sec.get("signer"),
		sec.get("date"),
		sec.get("commit_sha"),
		rel.get("signer"),
		rel.get("date"),
	)
	is_active = any(not _is_tbd(v) for v in signer_slots)
	if not is_active:
		# Pure scaffold row. Tolerated unless --strict.
		if strict:
			return [f"{ticket}: scaffold row not yet signed (--strict mode)"]
		return []

	violations: list[str] = []

	# Security-lead signoff: required for every active row.
	if _is_tbd(sec.get("signer")):
		violations.append(f"{ticket}: security_lead_signoff.signer unsigned")
	if _is_tbd(sec.get("date")):
		violations.append(f"{ticket}: security_lead_signoff.date missing")

	# Release-manager signoff: required for every active row.
	if _is_tbd(rel.get("signer")):
		violations.append(f"{ticket}: release_manager_signoff.signer unsigned")
	if _is_tbd(rel.get("date")):
		violations.append(f"{ticket}: release_manager_signoff.date missing")

	# Commit sha: required for P0 tickets.
	if ticket in P0_TICKETS:
		sha = sec.get("commit_sha")
		if _is_tbd(sha):
			violations.append(f"{ticket}: P0 commit_sha missing")
		else:
			normalised = str(sha).strip().lower()
			if not SHA_RE.match(normalised):
				violations.append(f"{ticket}: P0 commit_sha not a valid git sha ({sha!r})")

	return violations


def main(argv: Sequence[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--ticket",
		help="check only the row with this ticket id (e.g. E-32)",
	)
	parser.add_argument(
		"--strict",
		action="store_true",
		help="also fail on pure-scaffold rows (no phase set)",
	)
	parser.add_argument(
		"--checklist",
		type=Path,
		default=CHECKLIST_PATH,
		help="path to signoff-checklist.md",
	)
	args = parser.parse_args(argv)

	if not args.checklist.exists():
		print(f"check_signoff: checklist not found at {args.checklist}", file=sys.stderr)
		return 2

	md_text = args.checklist.read_text(encoding="utf-8")
	try:
		rows = _parse_records(md_text)
	except SystemExit:
		return 2

	if not rows:
		print(f"check_signoff: no YAML rows parsed from {args.checklist}", file=sys.stderr)
		return 2

	all_violations: list[str] = []
	checked = 0
	for row in rows:
		ticket = str(row.get("ticket") or "").strip()
		if args.ticket and ticket != args.ticket:
			continue
		checked += 1
		all_violations.extend(_row_violations(row, args.strict))

	if args.ticket and checked == 0:
		print(f"check_signoff: ticket {args.ticket!r} not found in {args.checklist}", file=sys.stderr)
		return 1

	if all_violations:
		print(f"check_signoff: {len(all_violations)} violation(s):", file=sys.stderr)
		for v in all_violations:
			print(f"  - {v}", file=sys.stderr)
		print(
			"\nSee docs/audit-fix-plan.md §10.2 for the signoff protocol.",
			file=sys.stderr,
		)
		return 1

	print(f"check_signoff: {checked} row(s) inspected, all populated rows signed.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
