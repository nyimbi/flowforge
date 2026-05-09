"""``flowforge migration-safety`` — static analyzer for alembic migrations.

Item 1 of :doc:`docs/improvements`, W0 of
:doc:`docs/v0.3.0-engineering-plan`.

Scans a directory of alembic revision files, parses each with the
standard library :mod:`ast` module after a regex pre-scan, and emits
per-rev safety findings classified by severity:

* ``critical`` — multi-head detected (concurrent revisions sharing a
  ``down_revision``).
* ``high`` — type narrowing, ``CREATE INDEX`` without ``CONCURRENTLY`` on
  Postgres-targeted ops, column drop with no deprecation comment, NOT NULL
  add to a populated table (above the configured size threshold).
* ``warn`` — NOT NULL add when no ``table_size_hints.json`` is provided
  (advisory; we cannot tell if the target table is large or empty).
* ``info`` — first-create migrations, structural notes.

Exit codes:

* ``0`` — only INFO findings.
* ``1`` — at least one HIGH or CRITICAL finding.
* ``2`` — usage error / invalid input.

The same rule catalogue is mirrored by the generator-time per-bundle
report at :mod:`flowforge_cli.jtbd.generators.migration_safety`; this
CLI is the operator-facing tool that runs against an *existing* alembic
chain (e.g. a host's ``backend/migrations/versions`` directory).
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer


# ---------------------------------------------------------------------------
# Severity / Finding model
# ---------------------------------------------------------------------------


class Severity(str, Enum):
	"""Severity ordering: ``info < warn < high < critical``."""

	INFO = "info"
	WARN = "warn"
	HIGH = "high"
	CRITICAL = "critical"


_SEVERITY_RANK = {
	Severity.INFO: 0,
	Severity.WARN: 1,
	Severity.HIGH: 2,
	Severity.CRITICAL: 3,
}


@dataclass(frozen=True)
class Finding:
	"""A single safety finding emitted by the analyzer.

	The triple ``(file, line, rule)`` is unique within a single scan;
	the ratchet baseline format keys off this triple.
	"""

	rule: str
	severity: Severity
	location: str  # ``<path>:<line>`` or ``chain:<rev>``
	message: str
	suggested_rewrite: str
	blast_radius: str

	def to_baseline_line(self) -> str:
		"""Format for inclusion in ``migration_safety_baseline.txt``."""

		return f"migration_safety: {self.location}: {self.rule}"


@dataclass(frozen=True)
class MigrationFile:
	"""Parsed view of one migration revision file."""

	path: Path
	revision: str | None
	down_revision: str | tuple[str, ...] | None
	branch_labels: tuple[str, ...]
	source: str
	tree: ast.Module | None  # ``None`` if parse failed


# ---------------------------------------------------------------------------
# Size hints
# ---------------------------------------------------------------------------


_DEFAULT_BIG_TABLE_THRESHOLD = 1_000_000


def _load_size_hints(hints_path: Path | None) -> dict[str, int]:
	"""Load ``table_size_hints.json`` if present.

	Returns an empty dict on missing file or any decode error — the
	analyzer downgrades NOT NULL findings to WARN when no hints are
	available, so a missing file is non-fatal.
	"""

	if hints_path is None or not hints_path.is_file():
		return {}
	try:
		raw = json.loads(hints_path.read_text(encoding="utf-8"))
	except json.JSONDecodeError:
		return {}
	if not isinstance(raw, dict):
		return {}
	out: dict[str, int] = {}
	for k, v in raw.items():
		if isinstance(v, (int, float)) and isinstance(k, str):
			out[k] = int(v)
	return out


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------


_REVISION_RE = re.compile(r'^\s*revision\s*[:=]\s*["\'](?P<rev>[^"\']+)["\']', re.MULTILINE)
_DOWN_REVISION_RE = re.compile(
	r'^\s*down_revision\s*[:=]\s*(?P<dr>None|["\'][^"\']+["\']|\(.*\))',
	re.MULTILINE,
)


def _parse_migration_file(path: Path) -> MigrationFile:
	"""Best-effort parse: regex pre-scan for revision / down_revision, then AST."""

	source = path.read_text(encoding="utf-8")
	revision: str | None = None
	down_revision: str | tuple[str, ...] | None = None
	branch_labels: tuple[str, ...] = ()

	# Regex pre-scan for the simple cases — survives broken AST nicely.
	m = _REVISION_RE.search(source)
	if m:
		revision = m.group("rev")
	m = _DOWN_REVISION_RE.search(source)
	if m:
		raw = m.group("dr")
		if raw == "None":
			down_revision = None
		elif raw.startswith(("'", '"')):
			down_revision = raw.strip("'\"")
		elif raw.startswith("("):
			# tuple form for branch merges: ('a', 'b')
			items = re.findall(r'["\']([^"\']+)["\']', raw)
			down_revision = tuple(items) if items else None

	tree: ast.Module | None
	try:
		tree = ast.parse(source, filename=str(path))
	except SyntaxError:
		tree = None

	# Confirm via AST when available — it overrides regex guesses to
	# survive edge cases like multi-line assignments.
	if tree is not None:
		ast_rev, ast_dr_set, ast_dr = _extract_revision_assignments(tree)
		if ast_rev is not None:
			revision = ast_rev
		if ast_dr_set:
			down_revision = ast_dr
		branch_labels = _extract_branch_labels(tree)

	return MigrationFile(
		path=path,
		revision=revision,
		down_revision=down_revision,
		branch_labels=branch_labels,
		source=source,
		tree=tree,
	)


def _extract_branch_labels(tree: ast.Module) -> tuple[str, ...]:
	"""Walk the module for ``branch_labels = ("a",)`` / ``= "a"`` / ``= None``."""

	for node in tree.body:
		if not isinstance(node, ast.Assign) or len(node.targets) != 1:
			continue
		target = node.targets[0]
		if not isinstance(target, ast.Name) or target.id != "branch_labels":
			continue
		value = node.value
		if isinstance(value, ast.Constant):
			if isinstance(value.value, str):
				return (value.value,)
			return ()
		if isinstance(value, (ast.Tuple, ast.List)):
			out: list[str] = []
			for elt in value.elts:
				if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
					out.append(elt.value)
			return tuple(out)
	return ()


def _extract_revision_assignments(
	tree: ast.Module,
) -> tuple[str | None, bool, str | tuple[str, ...] | None]:
	"""Walk a parsed module for ``revision`` / ``down_revision`` assignments.

	Returns ``(revision, down_revision_was_set, down_revision_value)``.
	The middle flag distinguishes "we saw a ``down_revision = None``"
	(which we want to honour) from "we never saw any ``down_revision``
	assignment" (callers should keep the regex guess).
	"""

	revision: str | None = None
	down_set = False
	down_value: str | tuple[str, ...] | None = None
	for node in tree.body:
		if not isinstance(node, ast.Assign) or len(node.targets) != 1:
			continue
		target = node.targets[0]
		if not isinstance(target, ast.Name):
			continue
		if target.id == "revision" and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
			revision = node.value.value
		elif target.id == "down_revision":
			value = node.value
			if isinstance(value, ast.Constant):
				if value.value is None:
					down_set = True
					down_value = None
				elif isinstance(value.value, str):
					down_set = True
					down_value = value.value
			elif isinstance(value, ast.Tuple):
				items: list[str] = []
				for elt in value.elts:
					if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
						items.append(elt.value)
				if items:
					down_set = True
					down_value = tuple(items)
	return revision, down_set, down_value


# ---------------------------------------------------------------------------
# Per-file rules
# ---------------------------------------------------------------------------


_DEPRECATION_MARKERS = (
	"deprecation window",
	"deprecation-window",
	"deprecated_at",
	"will be dropped",
)


def _check_create_index_concurrent(mig: MigrationFile) -> list[Finding]:
	"""HIGH: ``op.create_index`` without ``postgresql_concurrently=True``.

	First-create migrations bundle ``create_index`` inside the same
	``op.create_table`` flow on an empty table — analyzer scans for
	the pair and downgrades to INFO when both appear in the same
	``upgrade()`` body.
	"""

	out: list[Finding] = []
	if mig.tree is None:
		return out

	upgrade_fn = _find_function(mig.tree, "upgrade")
	if upgrade_fn is None:
		return out

	has_create_table = False
	create_index_calls: list[tuple[ast.Call, bool]] = []
	for node in ast.walk(upgrade_fn):
		if not isinstance(node, ast.Call):
			continue
		fn_name = _attribute_chain(node.func)
		if fn_name == "op.create_table":
			has_create_table = True
		elif fn_name == "op.create_index":
			has_concurrent = _kwarg_truthy(node, "postgresql_concurrently")
			create_index_calls.append((node, has_concurrent))

	for call, concurrent in create_index_calls:
		if concurrent:
			continue
		if has_create_table:
			# First-create — empty table, safe.
			out.append(
				Finding(
					rule="create_index_first_create",
					severity=Severity.INFO,
					location=f"{mig.path}:{call.lineno}",
					message=(
						"`op.create_index` without CONCURRENTLY on a first-create "
						"migration. Safe because the table is empty."
					),
					suggested_rewrite=(
						"No action required for first-create. For any future index "
						"add to this table, set `postgresql_concurrently=True` and "
						"split into a non-transactional migration."
					),
					blast_radius=f"index inside `op.create_table` (rev `{mig.revision}`)",
				)
			)
			continue
		out.append(
			Finding(
				rule="create_index_without_concurrently",
				severity=Severity.HIGH,
				location=f"{mig.path}:{call.lineno}",
				message=(
					"`op.create_index` without CONCURRENTLY against a populated "
					"Postgres table will hold an exclusive lock for the duration "
					"of the index build."
				),
				suggested_rewrite=(
					"Pass `postgresql_concurrently=True` and run the migration in a "
					"non-transactional block: "
					"`with op.get_context().autocommit_block(): op.create_index(..., postgresql_concurrently=True)`."
				),
				blast_radius="entire table — write-blocking on production traffic",
			)
		)
	return out


def _check_not_null_backfill(
	mig: MigrationFile,
	hints: dict[str, int],
	threshold: int,
) -> list[Finding]:
	"""HIGH/WARN: ``op.add_column`` with ``nullable=False`` (no default).

	Detects the most common "backfill missing" shape: add a NOT NULL
	column to an existing table without a `server_default` and without
	a paired backfill operation.
	"""

	out: list[Finding] = []
	if mig.tree is None:
		return out

	upgrade_fn = _find_function(mig.tree, "upgrade")
	if upgrade_fn is None:
		return out

	# If the migration is a first-create, NOT NULL columns inside
	# create_table are fine.
	is_first_create = any(
		isinstance(n, ast.Call) and _attribute_chain(n.func) == "op.create_table"
		for n in ast.walk(upgrade_fn)
	)

	for node in ast.walk(upgrade_fn):
		if not isinstance(node, ast.Call):
			continue
		fn_name = _attribute_chain(node.func)
		if fn_name != "op.add_column":
			continue

		table = _string_arg(node, 0)
		if table is None:
			continue
		# `nullable=False` may sit on the outer `op.add_column` call OR on
		# the inner `sa.Column(...)` argument. Check both.
		column = _column_argument(node)
		nullable_false = _kwarg_truthy(
			node, "nullable", default_truthy=False, expect_false=True,
		) or (
			column is not None
			and _kwarg_truthy(
				column, "nullable", default_truthy=False, expect_false=True,
			)
		)
		if not nullable_false:
			# Column allows NULL — safe.
			continue
		# `nullable=False` — check for default in the Column() construction.
		has_default = (
			column is not None
			and (
				_kwarg_present(column, "server_default")
				or _kwarg_present(column, "default")
			)
		)
		if has_default:
			continue
		if is_first_create:
			# This shape is unusual (combining create_table + add_column),
			# but we keep it INFO-level when it appears in a first-create.
			out.append(
				Finding(
					rule="not_null_in_first_create",
					severity=Severity.INFO,
					location=f"{mig.path}:{node.lineno}",
					message=(
						"`op.add_column` with `nullable=False` inside a first-create "
						"migration; the table is empty so there is no backfill risk."
					),
					suggested_rewrite="No action required.",
					blast_radius=f"new table `{table}` (rev `{mig.revision}`)",
				)
			)
			continue

		size_hint = hints.get(table)
		if size_hint is not None and size_hint >= threshold:
			out.append(
				Finding(
					rule="not_null_backfill_over_threshold",
					severity=Severity.HIGH,
					location=f"{mig.path}:{node.lineno}",
					message=(
						f"`op.add_column` adds NOT NULL to `{table}` "
						f"({size_hint:,} rows, ≥ threshold {threshold:,}) without a "
						"server_default."
					),
					suggested_rewrite=(
						"Split into three migrations: 1) add nullable column; "
						"2) backfill rows online (chunked UPDATE); "
						"3) `op.alter_column(..., nullable=False)` after backfill verifies."
					),
					blast_radius=f"every row of `{table}` ({size_hint:,} rows)",
				)
			)
		else:
			# No hint or below threshold — advisory only.
			out.append(
				Finding(
					rule="not_null_backfill_no_hint",
					severity=Severity.WARN,
					location=f"{mig.path}:{node.lineno}",
					message=(
						f"`op.add_column` adds NOT NULL to `{table}` without a "
						"server_default. No `table_size_hints.json` hint for this table; "
						"if the table has rows in production this will fail at deploy."
					),
					suggested_rewrite=(
						"Provide a `table_size_hints.json` entry, or split into the "
						"three-step add-nullable / backfill / set-NOT-NULL pattern."
					),
					blast_radius=f"every row of `{table}` (size unknown)",
				)
			)
	return out


def _check_type_narrow(mig: MigrationFile) -> list[Finding]:
	"""HIGH: ``op.alter_column`` narrowing a ``String`` / ``Numeric`` width."""

	out: list[Finding] = []
	if mig.tree is None:
		return out

	upgrade_fn = _find_function(mig.tree, "upgrade")
	if upgrade_fn is None:
		return out

	for node in ast.walk(upgrade_fn):
		if not isinstance(node, ast.Call):
			continue
		if _attribute_chain(node.func) != "op.alter_column":
			continue
		new_type = _kwarg_value(node, "type_")
		existing_type = _kwarg_value(node, "existing_type")
		if new_type is None or existing_type is None:
			continue
		new_w = _string_or_numeric_width(new_type)
		old_w = _string_or_numeric_width(existing_type)
		if new_w is None or old_w is None:
			continue
		if new_w < old_w:
			table = _string_arg(node, 0) or "<unknown>"
			column = _string_arg(node, 1) or "<unknown>"
			out.append(
				Finding(
					rule="type_narrowing",
					severity=Severity.HIGH,
					location=f"{mig.path}:{node.lineno}",
					message=(
						f"`op.alter_column` narrows `{table}.{column}` from "
						f"width {old_w} to {new_w}."
					),
					suggested_rewrite=(
						"Validate every existing row fits the narrower bound before "
						"narrowing. If any row exceeds the bound, backfill or reject "
						"in a separate migration first."
					),
					blast_radius=f"`{table}.{column}` — every row scanned",
				)
			)
	return out


def _check_column_drop(mig: MigrationFile) -> list[Finding]:
	"""HIGH: ``op.drop_column`` without a deprecation-window comment."""

	out: list[Finding] = []
	if mig.tree is None:
		return out
	source_lines = mig.source.splitlines()

	upgrade_fn = _find_function(mig.tree, "upgrade")
	if upgrade_fn is None:
		return out

	for node in ast.walk(upgrade_fn):
		if not isinstance(node, ast.Call):
			continue
		if _attribute_chain(node.func) != "op.drop_column":
			continue
		# Look up to 3 lines above + the call itself for a deprecation marker.
		lo = max(0, node.lineno - 4)
		hi = min(len(source_lines), node.lineno + 1)
		ctx = "\n".join(source_lines[lo:hi]).lower()
		if any(marker in ctx for marker in _DEPRECATION_MARKERS):
			continue
		table = _string_arg(node, 0) or "<unknown>"
		column = _string_arg(node, 1) or "<unknown>"
		out.append(
			Finding(
				rule="column_drop_no_deprecation",
				severity=Severity.HIGH,
				location=f"{mig.path}:{node.lineno}",
				message=(
					f"`op.drop_column` on `{table}.{column}` without a "
					"deprecation-window comment in the surrounding 3 lines."
				),
				suggested_rewrite=(
					"Land the drop in two stages: 1) flip the column to nullable + "
					"emit a deprecation comment one release earlier; 2) drop after "
					"the deprecation window. Add a `# deprecation-window: <since-version>` "
					"comment to silence this finding."
				),
				blast_radius=f"`{table}.{column}` — data loss is permanent on apply",
			)
		)
	return out


# ---------------------------------------------------------------------------
# Chain-level rules
# ---------------------------------------------------------------------------


def _check_multi_head(migrations: list[MigrationFile]) -> list[Finding]:
	"""CRITICAL: more than one revision is a head (no successor) within the same chain.

	A head is a revision that no other revision points to via
	``down_revision``. Two heads in the *same chain* means the chain
	has a fork that alembic refuses to deploy without an explicit
	merge.

	Heads with distinct ``branch_labels`` are *intentional* parallel
	chains — the flowforge per-JTBD migration pattern uses
	``branch_labels = ("<package>_<jtbd>",)`` so each JTBD ships its
	own independent migration history. We do not flag those as a
	multi-head bug; alembic supports parallel chains and operators
	upgrade them independently or via ``alembic upgrade <branch>@head``.

	The CRITICAL only fires when ≥2 heads share an empty (or identical)
	branch_labels set — the actual "two devs created a head off the
	same parent" scenario.
	"""

	out: list[Finding] = []
	if not migrations:
		return out

	all_revs: set[str] = set()
	pointed_to: set[str] = set()
	by_rev: dict[str, MigrationFile] = {}
	for m in migrations:
		if m.revision is None:
			continue
		all_revs.add(m.revision)
		by_rev[m.revision] = m
		dr = m.down_revision
		if dr is None:
			continue
		if isinstance(dr, str):
			pointed_to.add(dr)
		else:
			pointed_to.update(dr)

	heads = sorted(all_revs - pointed_to)
	if len(heads) <= 1:
		return out

	# Group heads by their branch_labels. Distinct labels = distinct
	# parallel chains (flowforge per-JTBD pattern).
	by_branch: dict[tuple[str, ...], list[str]] = defaultdict(list)
	for h in heads:
		mig = by_rev.get(h)
		key: tuple[str, ...] = mig.branch_labels if mig is not None else ()
		by_branch[key].append(h)

	for branch, members in sorted(by_branch.items()):
		if len(members) <= 1:
			continue
		head_locations = ", ".join(f"`{h}`" for h in members)
		branch_desc = (
			f"branch_labels={branch}" if branch else "no branch_labels"
		)
		for h in members:
			mig = by_rev.get(h)
			location = f"{mig.path}:1" if mig is not None else f"chain:{h}"
			out.append(
				Finding(
					rule="multi_head",
					severity=Severity.CRITICAL,
					location=location,
					message=(
						f"Multiple alembic heads detected within {branch_desc}: "
						f"{head_locations}. `alembic upgrade head` will refuse to run."
					),
					suggested_rewrite=(
						"Run `alembic merge -m 'merge heads' " + " ".join(members) + "` "
						"to produce a merge revision; commit the merge alongside the "
						"new feature branch."
					),
					blast_radius=f"deploy refuses to start ({len(members)} heads in same chain)",
				)
			)
	return out


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
	for node in tree.body:
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
			return node
	return None


def _attribute_chain(node: ast.expr) -> str:
	"""Return ``a.b.c`` for an Attribute / Name chain, else empty string."""

	parts: list[str] = []
	cur: ast.expr | None = node
	while isinstance(cur, ast.Attribute):
		parts.append(cur.attr)
		cur = cur.value
	if isinstance(cur, ast.Name):
		parts.append(cur.id)
		return ".".join(reversed(parts))
	return ""


def _kwarg_value(call: ast.Call, name: str) -> ast.expr | None:
	for kw in call.keywords:
		if kw.arg == name:
			return kw.value
	return None


def _kwarg_present(call: ast.Call, name: str) -> bool:
	return _kwarg_value(call, name) is not None


def _kwarg_truthy(
	call: ast.Call,
	name: str,
	*,
	default_truthy: bool = True,
	expect_false: bool = False,
) -> bool:
	"""Return whether kwarg *name* on *call* is set to a truthy literal.

	If ``expect_false`` is set, returns ``True`` when the kwarg is the
	literal ``False`` — handy for the NOT NULL case where we want to
	flag ``nullable=False`` specifically.
	"""

	val = _kwarg_value(call, name)
	if val is None:
		return False
	if isinstance(val, ast.Constant):
		if expect_false:
			return val.value is False
		return bool(val.value)
	if expect_false:
		return False
	return default_truthy


def _string_arg(call: ast.Call, idx: int) -> str | None:
	if idx >= len(call.args):
		return None
	val = call.args[idx]
	if isinstance(val, ast.Constant) and isinstance(val.value, str):
		return val.value
	return None


def _column_argument(call: ast.Call) -> ast.Call | None:
	"""Return the first positional ``sa.Column(...)`` argument, if any."""

	for arg in call.args:
		if isinstance(arg, ast.Call):
			fn = _attribute_chain(arg.func)
			if fn.endswith("Column"):
				return arg
	return None


def _string_or_numeric_width(node: ast.expr) -> int | None:
	"""Extract ``sa.String(N)``-style width, ``sa.Numeric(p, s)`` precision."""

	if not isinstance(node, ast.Call):
		return None
	fn = _attribute_chain(node.func)
	if fn.endswith(("String", "Text", "Integer", "Numeric")):
		# String(length=N) or String(N)
		for kw in node.keywords:
			if kw.arg in ("length", "precision") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
				return int(kw.value.value)
		if node.args:
			first = node.args[0]
			if isinstance(first, ast.Constant) and isinstance(first.value, int):
				return int(first.value)
	return None


# ---------------------------------------------------------------------------
# Public scan API
# ---------------------------------------------------------------------------


@dataclass
class ScanReport:
	"""Aggregate of all findings from a scan."""

	migrations: list[MigrationFile] = field(default_factory=list)
	findings: list[Finding] = field(default_factory=list)

	def by_severity(self, sev: Severity) -> list[Finding]:
		return [f for f in self.findings if f.severity == sev]

	def has_blocking(self) -> bool:
		return any(
			_SEVERITY_RANK[f.severity] >= _SEVERITY_RANK[Severity.HIGH]
			for f in self.findings
		)


def scan_directory(
	migrations_dir: Path,
	*,
	hints_path: Path | None = None,
	threshold: int = _DEFAULT_BIG_TABLE_THRESHOLD,
) -> ScanReport:
	"""Scan every ``*.py`` file directly under *migrations_dir*."""

	assert migrations_dir is not None, "migrations_dir is required"
	report = ScanReport()
	if not migrations_dir.is_dir():
		return report

	hints = _load_size_hints(hints_path)

	files = sorted(p for p in migrations_dir.glob("*.py") if p.is_file() and not p.name.startswith("_"))
	for path in files:
		mig = _parse_migration_file(path)
		report.migrations.append(mig)
		if mig.tree is None:
			report.findings.append(
				Finding(
					rule="parse_error",
					severity=Severity.HIGH,
					location=f"{mig.path}:1",
					message="Migration file failed to parse as Python.",
					suggested_rewrite="Inspect the file and fix the syntax error before running again.",
					blast_radius=f"single revision (`{mig.path.name}`)",
				)
			)
			continue
		report.findings.extend(_check_create_index_concurrent(mig))
		report.findings.extend(_check_not_null_backfill(mig, hints, threshold))
		report.findings.extend(_check_type_narrow(mig))
		report.findings.extend(_check_column_drop(mig))

	report.findings.extend(_check_multi_head(report.migrations))

	# Stable order: severity desc, then location.
	report.findings.sort(
		key=lambda f: (-_SEVERITY_RANK[f.severity], f.location, f.rule),
	)
	return report


# ---------------------------------------------------------------------------
# Markdown emission
# ---------------------------------------------------------------------------


def render_findings_markdown(report: ScanReport) -> str:
	"""Render findings as a deterministic markdown report."""

	lines: list[str] = []
	lines.append("# Migration safety scan")
	lines.append("")
	if not report.findings:
		lines.append("No findings.")
		lines.append("")
		return "\n".join(lines)

	# Group by severity (already sorted by severity desc in the report).
	by_sev: dict[Severity, list[Finding]] = defaultdict(list)
	for f in report.findings:
		by_sev[f.severity].append(f)

	for sev in (Severity.CRITICAL, Severity.HIGH, Severity.WARN, Severity.INFO):
		bucket = by_sev.get(sev) or []
		if not bucket:
			continue
		lines.append(f"## {sev.value.upper()} ({len(bucket)})")
		lines.append("")
		for f in bucket:
			lines.append(f"- `{f.rule}` @ `{f.location}` — {f.message}")
			lines.append(f"  - Blast radius: {f.blast_radius}")
			lines.append(f"  - Suggested rewrite: {f.suggested_rewrite}")
		lines.append("")
	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------


def migration_safety_cmd(
	migrations_dir: Annotated[
		Path,
		typer.Argument(
			exists=False,
			file_okay=False,
			dir_okay=True,
			readable=True,
			help="Directory of alembic revision files to scan (e.g. backend/migrations/versions).",
		),
	],
	hints: Annotated[
		Path | None,
		typer.Option(
			"--hints",
			dir_okay=False,
			help="Optional `table_size_hints.json` mapping table names to row counts.",
		),
	] = None,
	threshold: Annotated[
		int,
		typer.Option(
			"--threshold",
			min=0,
			help="Row count above which NOT NULL adds become HIGH (default 1,000,000).",
		),
	] = _DEFAULT_BIG_TABLE_THRESHOLD,
	fmt: Annotated[
		str,
		typer.Option("--format", help="Output format: 'text', 'json', or 'markdown'."),
	] = "text",
	baseline: Annotated[
		Path | None,
		typer.Option(
			"--baseline",
			dir_okay=False,
			help="Baseline file with allowed findings (one per line, see ratchets/migration_safety_baseline.txt).",
		),
	] = None,
) -> None:
	"""Statically scan alembic migrations for safety findings.

	Exits ``0`` if no HIGH/CRITICAL findings (after baseline filter),
	``1`` otherwise.
	"""

	if not migrations_dir.exists():
		typer.echo(f"error: directory not found: {migrations_dir}", err=True)
		raise typer.Exit(2)
	if not migrations_dir.is_dir():
		typer.echo(f"error: not a directory: {migrations_dir}", err=True)
		raise typer.Exit(2)

	report = scan_directory(
		migrations_dir,
		hints_path=hints,
		threshold=threshold,
	)

	# Apply baseline filter if provided.
	if baseline is not None and baseline.is_file():
		allowed = _parse_baseline(baseline)
		report.findings = [
			f for f in report.findings if f.to_baseline_line() not in allowed
		]

	if fmt == "json":
		payload = {
			"migrations_scanned": len(report.migrations),
			"findings": [
				{
					"rule": f.rule,
					"severity": f.severity.value,
					"location": f.location,
					"message": f.message,
					"blast_radius": f.blast_radius,
					"suggested_rewrite": f.suggested_rewrite,
				}
				for f in report.findings
			],
		}
		typer.echo(json.dumps(payload, indent=2, sort_keys=True))
	elif fmt == "markdown":
		typer.echo(render_findings_markdown(report))
	else:
		_print_text(report)

	if report.has_blocking():
		raise typer.Exit(1)


def _print_text(report: ScanReport) -> None:
	typer.echo(f"migration-safety: scanned {len(report.migrations)} revision(s)")
	if not report.findings:
		typer.echo("  ok — no findings.")
		return
	for f in report.findings:
		typer.echo(f"  [{f.severity.value.upper()}] {f.location}: {f.rule} — {f.message}")
		typer.echo(f"    blast radius: {f.blast_radius}")
		typer.echo(f"    suggested rewrite: {f.suggested_rewrite}")


def _parse_baseline(path: Path) -> set[str]:
	"""Return the set of allowed ``migration_safety: ...`` lines from *path*."""

	out: set[str] = set()
	for raw in path.read_text(encoding="utf-8").splitlines():
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		if line.startswith("migration_safety:"):
			out.add(line)
	return out


def register(app: typer.Typer) -> None:
	"""Mount ``flowforge migration-safety`` on the root app."""

	app.command(
		"migration-safety",
		help=(
			"Static safety analyzer for alembic migrations "
			"(item 1 of v0.3.0 — improvements.md)."
		),
	)(migration_safety_cmd)
