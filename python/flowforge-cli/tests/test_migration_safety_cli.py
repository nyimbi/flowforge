"""Tests for ``flowforge migration-safety`` (W0 item 1).

Covers:

* CLI happy path on a clean first-create migration set (exit 0).
* Each safety rule fires with correct severity:
  - ``create_index_without_concurrently`` (HIGH)
  - ``not_null_backfill_over_threshold`` (HIGH, with hints)
  - ``not_null_backfill_no_hint`` (WARN, no hints)
  - ``type_narrowing`` (HIGH)
  - ``column_drop_no_deprecation`` (HIGH)
  - ``multi_head`` (CRITICAL)
* Baseline filter accepts a finding listed in baseline.txt.
* JSON / markdown output formats.
"""

from __future__ import annotations

import ast
import json
import textwrap
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from flowforge_cli.commands import migration_safety as migration_safety_module
from flowforge_cli.commands.migration_safety import (
	Finding,
	MigrationFile,
	ScanReport,
	Severity,
	_check_multi_head,
	_attribute_chain,
	_check_column_drop,
	_check_create_index_concurrent,
	_check_not_null_backfill,
	_check_type_narrow,
	_column_argument,
	_extract_revision_assignments,
	_kwarg_truthy,
	_load_size_hints,
	_parse_baseline,
	_parse_migration_file,
	_string_arg,
	_string_or_numeric_width,
	migration_safety_cmd,
	render_findings_markdown,
	scan_directory,
)
from flowforge_cli.main import app


runner = CliRunner()


def _write_migration(dir_: Path, name: str, body: str) -> Path:
	"""Write a minimal alembic-shaped revision file."""
	path = dir_ / name
	path.write_text(textwrap.dedent(body), encoding="utf-8")
	return path


def _call(expr: str) -> ast.Call:
	"""Parse a single call expression for helper-level assertions."""
	node = ast.parse(expr).body[0]
	assert isinstance(node, ast.Expr)
	assert isinstance(node.value, ast.Call)
	return node.value


def _migration(path: Path, source: str, tree: ast.Module | None) -> MigrationFile:
	return MigrationFile(
		path=path,
		revision="rev",
		down_revision=None,
		branch_labels=(),
		source=textwrap.dedent(source),
		tree=tree,
	)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_first_create_only_yields_info(tmp_path: Path) -> None:
	"""A fresh CREATE TABLE migration should emit only INFO findings."""
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"abc123_create_users.py",
		"""
		\"\"\"create users table.\"\"\"

		from alembic import op
		import sqlalchemy as sa

		revision = "abc123"
		down_revision = None
		branch_labels = None
		depends_on = None


		def upgrade() -> None:
			op.create_table(
				"users",
				sa.Column("id", sa.String(length=36), primary_key=True),
				sa.Column("email", sa.String(320), nullable=False),
			)
			op.create_index("ix_users_email", "users", ["email"])


		def downgrade() -> None:
			op.drop_index("ix_users_email", table_name="users")
			op.drop_table("users")
		""",
	)
	report = scan_directory(d)
	assert len(report.migrations) == 1
	# Only INFO from create_index_first_create — no HIGH/CRITICAL.
	assert not report.has_blocking()
	for f in report.findings:
		assert f.severity == Severity.INFO


def test_scan_directory_ignores_missing_path(tmp_path: Path) -> None:
	report = scan_directory(tmp_path / "missing")

	assert report.migrations == []
	assert report.findings == []


def test_size_hints_loader_handles_bad_json_and_mixed_values(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	assert _load_size_hints(None) == {}
	assert _load_size_hints(tmp_path / "missing.json") == {}

	hints = tmp_path / "hints.json"
	hints.write_text("{not-json", encoding="utf-8")
	assert _load_size_hints(hints) == {}

	hints.write_text('["orders"]', encoding="utf-8")
	assert _load_size_hints(hints) == {}

	hints.write_text("{}", encoding="utf-8")
	monkeypatch.setattr(
		migration_safety_module.json,
		"loads",
		lambda _payload: {1: 20, "orders": 2.9, "bad": "300"},
	)
	assert _load_size_hints(hints) == {"orders": 2}


def test_parser_keeps_regex_metadata_when_syntax_is_broken(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	path = _write_migration(
		d,
		"broken.py",
		"""
		revision = "broken"
		down_revision = ("base_a", "base_b")

		def upgrade(:
			pass
		""",
	)

	migration = _parse_migration_file(path)
	assert migration.revision == "broken"
	assert migration.down_revision == ("base_a", "base_b")
	assert migration.tree is None

	report = scan_directory(d)
	assert [f.rule for f in report.findings] == ["parse_error"]
	assert report.has_blocking()


def test_parser_ast_metadata_overrides_regex_guess(tmp_path: Path) -> None:
	path = _write_migration(
		tmp_path,
		"metadata.py",
		"""
		revision = "regex"
		down_revision = "regex_parent"
		revision = "ast"
		down_revision = ("parent_a", 5, "parent_b")
		branch_labels = ["pkg_branch", 10]
		""",
	)

	migration = _parse_migration_file(path)

	assert migration.revision == "ast"
	assert migration.down_revision == ("parent_a", "parent_b")
	assert migration.branch_labels == ("pkg_branch",)


def test_parser_handles_missing_metadata_and_empty_tuple_down_revision(
	tmp_path: Path,
) -> None:
	path = _write_migration(
		tmp_path,
		"metadata.py",
		"""
		down_revision = ()
		branch_labels = branch_name
		""",
	)

	migration = _parse_migration_file(path)

	assert migration.revision is None
	assert migration.down_revision is None
	assert migration.branch_labels == ()


def test_parser_honors_down_revision_when_revision_missing(tmp_path: Path) -> None:
	path = _write_migration(
		tmp_path,
		"down_only.py",
		"""
		down_revision = "base"
		""",
	)

	migration = _parse_migration_file(path)

	assert migration.revision is None
	assert migration.down_revision == "base"


def test_parser_keeps_revision_when_down_revision_missing(tmp_path: Path) -> None:
	path = _write_migration(
		tmp_path,
		"revision_only.py",
		"""
		revision = "rev"
		""",
	)

	migration = _parse_migration_file(path)

	assert migration.revision == "rev"
	assert migration.down_revision is None


def test_parser_accepts_string_branch_label(tmp_path: Path) -> None:
	path = _write_migration(
		tmp_path,
		"branch.py",
		"""
		revision = "branch"
		down_revision = None
		branch_labels = "pkg_branch"
		""",
	)

	assert _parse_migration_file(path).branch_labels == ("pkg_branch",)


def test_revision_assignment_extraction_skips_unsupported_targets() -> None:
	tree = ast.parse(textwrap.dedent(
		"""
		a = down_revision = "skip"
		obj.revision = "skip"
		revision = "rev"
		down_revision = ("base_a", 2, "base_b")
		"""
	))

	assert _extract_revision_assignments(tree) == (
		"rev",
		True,
		("base_a", "base_b"),
	)


def test_revision_assignment_extraction_ignores_unsupported_values() -> None:
	tree = ast.parse(textwrap.dedent(
		"""
		down_revision = 123
		down_revision = [\"base\"]
		down_revision = (1, 2)
		"""
	))

	assert _extract_revision_assignments(tree) == (None, False, None)


# ---------------------------------------------------------------------------
# Per-rule
# ---------------------------------------------------------------------------


def test_create_index_without_concurrently_high(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"def456_add_index.py",
		"""
		from alembic import op

		revision = "def456"
		down_revision = "abc123"


		def upgrade() -> None:
			op.create_index("ix_users_name", "users", ["name"])


		def downgrade() -> None:
			op.drop_index("ix_users_name", table_name="users")
		""",
	)
	report = scan_directory(d)
	rules = {f.rule for f in report.findings}
	assert "create_index_without_concurrently" in rules
	high = report.by_severity(Severity.HIGH)
	assert any(f.rule == "create_index_without_concurrently" for f in high)


def test_create_index_concurrently_clean(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"def456_add_index.py",
		"""
		from alembic import op

		revision = "def456"
		down_revision = "abc123"


		def upgrade() -> None:
			op.create_index("ix_users_name", "users", ["name"], postgresql_concurrently=True)


		def downgrade() -> None:
			op.drop_index("ix_users_name", table_name="users")
		""",
	)
	report = scan_directory(d)
	# Should not emit a create-index finding.
	assert not any(
		f.rule.startswith("create_index_") for f in report.findings
	)


def test_rule_checks_return_cleanly_without_parse_tree_or_upgrade(tmp_path: Path) -> None:
	no_tree = _migration(tmp_path / "broken.py", "", None)
	no_upgrade = _migration(
		tmp_path / "no_upgrade.py",
		"def downgrade() -> None:\n\tpass\n",
		ast.parse("def downgrade() -> None:\n\tpass\n"),
	)

	for mig in (no_tree, no_upgrade):
		assert _check_create_index_concurrent(mig) == []
		assert _check_not_null_backfill(mig, {}, 1) == []
		assert _check_type_narrow(mig) == []
		assert _check_column_drop(mig) == []


def test_not_null_backfill_with_hint_over_threshold(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"ghi789_add_required_col.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "ghi789"
		down_revision = "abc123"


		def upgrade() -> None:
			op.add_column("orders", sa.Column("status", sa.String(64), nullable=False))


		def downgrade() -> None:
			op.drop_column("orders", "status")
		""",
	)
	hints = tmp_path / "table_size_hints.json"
	hints.write_text(json.dumps({"orders": 5_000_000}), encoding="utf-8")
	report = scan_directory(d, hints_path=hints, threshold=1_000_000)
	rules = {f.rule for f in report.findings}
	assert "not_null_backfill_over_threshold" in rules
	high = report.by_severity(Severity.HIGH)
	assert any(f.rule == "not_null_backfill_over_threshold" for f in high)


def test_not_null_backfill_without_hint_warn(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"ghi789_add_required_col.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "ghi789"
		down_revision = "abc123"


		def upgrade() -> None:
			op.add_column("orders", sa.Column("status", sa.String(64), nullable=False))


		def downgrade() -> None:
			op.drop_column("orders", "status")
		""",
	)
	report = scan_directory(d)
	rules = {f.rule for f in report.findings}
	assert "not_null_backfill_no_hint" in rules
	warn = report.by_severity(Severity.WARN)
	assert any(f.rule == "not_null_backfill_no_hint" for f in warn)


def test_not_null_with_server_default_clean(tmp_path: Path) -> None:
	"""``server_default=...`` makes NOT NULL safe — no finding."""
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"ghi789_add_required_col.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "ghi789"
		down_revision = "abc123"


		def upgrade() -> None:
			op.add_column(
				"orders",
				sa.Column("status", sa.String(64), nullable=False, server_default="open"),
			)


		def downgrade() -> None:
			op.drop_column("orders", "status")
		""",
	)
	report = scan_directory(d)
	assert not any(
		f.rule.startswith("not_null_backfill") for f in report.findings
	)


def test_not_null_in_first_create_is_info(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"first_create_add_column.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "first"
		down_revision = None


		def upgrade() -> None:
			op.create_table("orders", sa.Column("id", sa.String(36), primary_key=True))
			op.add_column("orders", sa.Column("status", sa.String(64), nullable=False))
		""",
	)

	report = scan_directory(d)

	assert any(
		f.rule == "not_null_in_first_create" and f.severity == Severity.INFO
		for f in report.findings
	)


def test_not_null_ignores_dynamic_table_and_nullable_column(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"nullable_shapes.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "nullable"
		down_revision = "base"


		def upgrade() -> None:
			op.add_column(table_name, sa.Column("status", sa.String(64), nullable=False))
			op.add_column("orders", sa.Column("notes", sa.String(64), nullable=True))
		""",
	)

	report = scan_directory(d)

	assert not any(f.rule.startswith("not_null") for f in report.findings)


def test_type_narrowing_high(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"jkl012_narrow_email.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "jkl012"
		down_revision = "abc123"


		def upgrade() -> None:
			op.alter_column(
				"users",
				"email",
				existing_type=sa.String(length=320),
				type_=sa.String(length=64),
			)


		def downgrade() -> None:
			op.alter_column(
				"users",
				"email",
				existing_type=sa.String(length=64),
				type_=sa.String(length=320),
			)
		""",
	)
	report = scan_directory(d)
	rules = {f.rule for f in report.findings}
	assert "type_narrowing" in rules
	high = report.by_severity(Severity.HIGH)
	assert any(f.rule == "type_narrowing" for f in high)


def test_type_narrowing_ignores_missing_non_width_and_wider_shapes(
	tmp_path: Path,
) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"safe_alters.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "safe_alters"
		down_revision = "base"


		def upgrade() -> None:
			op.alter_column("users", "name", type_=sa.String(64))
			op.alter_column(
				"users",
				"active",
				existing_type=sa.Boolean(),
				type_=sa.Boolean(),
			)
			op.alter_column(
				"users",
				"email",
				existing_type=sa.String(64),
				type_=sa.String(320),
			)
		""",
	)

	report = scan_directory(d)

	assert not any(f.rule == "type_narrowing" for f in report.findings)


def test_type_narrowing_reports_unknown_dynamic_table_and_column(
	tmp_path: Path,
) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"numeric_narrow.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "numeric_narrow"
		down_revision = "base"


		def upgrade() -> None:
			op.alter_column(
				table_name,
				column_name,
				existing_type=sa.Numeric(10, 2),
				type_=sa.Numeric(5, 2),
			)
		""",
	)

	report = scan_directory(d)

	hit = next(f for f in report.findings if f.rule == "type_narrowing")
	assert "`<unknown>.<unknown>`" in hit.message


def test_column_drop_no_deprecation_high(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"mno345_drop_legacy.py",
		"""
		from alembic import op

		revision = "mno345"
		down_revision = "abc123"


		def upgrade() -> None:
			op.drop_column("users", "legacy_token")


		def downgrade() -> None:
			pass
		""",
	)
	report = scan_directory(d)
	rules = {f.rule for f in report.findings}
	assert "column_drop_no_deprecation" in rules


def test_column_drop_with_deprecation_comment_clean(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"mno345_drop_legacy.py",
		"""
		from alembic import op

		revision = "mno345"
		down_revision = "abc123"


		def upgrade() -> None:
			# deprecation window: legacy_token marked deprecated in v0.1.0.
			op.drop_column("users", "legacy_token")


		def downgrade() -> None:
			pass
		""",
	)
	report = scan_directory(d)
	assert not any(
		f.rule == "column_drop_no_deprecation" for f in report.findings
	)


def test_multi_head_critical(tmp_path: Path) -> None:
	"""Two revisions sharing a down_revision but neither pointing to each other."""
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"head_a.py",
		"""
		from alembic import op

		revision = "head_a"
		down_revision = "root"


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"head_b.py",
		"""
		from alembic import op

		revision = "head_b"
		down_revision = "root"


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"root.py",
		"""
		from alembic import op

		revision = "root"
		down_revision = None


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	report = scan_directory(d)
	crit = report.by_severity(Severity.CRITICAL)
	assert len(crit) == 2  # one per head
	rules = {f.rule for f in crit}
	assert rules == {"multi_head"}


def test_multi_head_helper_handles_empty_and_unrevised_entries(
	tmp_path: Path,
) -> None:
	assert _check_multi_head([]) == []

	unrevised = MigrationFile(
		path=tmp_path / "unrevised.py",
		revision=None,
		down_revision=None,
		branch_labels=(),
		source="",
		tree=ast.parse(""),
	)

	assert _check_multi_head([unrevised]) == []


def test_distinct_branch_labels_not_flagged(tmp_path: Path) -> None:
	"""Two heads with *different* branch_labels are intentional parallel chains
	(flowforge per-JTBD migration pattern). Should NOT trigger multi_head."""
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"a.py",
		"""
		revision = "a"
		down_revision = None
		branch_labels = ("pkg_a",)


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"b.py",
		"""
		revision = "b"
		down_revision = None
		branch_labels = ("pkg_b",)


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	report = scan_directory(d)
	assert not any(f.rule == "multi_head" for f in report.findings)


def test_single_head_clean(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"a.py",
		"""
		revision = "a"
		down_revision = None


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	_write_migration(
		d,
		"b.py",
		"""
		revision = "b"
		down_revision = "a"


		def upgrade() -> None:
			pass


		def downgrade() -> None:
			pass
		""",
	)
	report = scan_directory(d)
	assert not any(f.rule == "multi_head" for f in report.findings)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_happy_path_zero_exit(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"abc123_create_users.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "abc123"
		down_revision = None


		def upgrade() -> None:
			op.create_table(
				"users",
				sa.Column("id", sa.String(length=36), primary_key=True),
			)


		def downgrade() -> None:
			op.drop_table("users")
		""",
	)
	r = runner.invoke(app, ["migration-safety", str(d)])
	assert r.exit_code == 0, r.output
	assert "scanned 1 revision" in r.output


def test_cli_blocking_finding_nonzero_exit(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"narrow.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "narrow"
		down_revision = None


		def upgrade() -> None:
			op.alter_column(
				"users",
				"email",
				existing_type=sa.String(length=320),
				type_=sa.String(length=64),
			)


		def downgrade() -> None:
			pass
		""",
	)
	r = runner.invoke(app, ["migration-safety", str(d)])
	assert r.exit_code == 1, r.output
	assert "type_narrowing" in r.output


def test_cli_json_output(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"abc123_create_users.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "abc123"
		down_revision = None


		def upgrade() -> None:
			op.create_table("users", sa.Column("id", sa.String(36), primary_key=True))


		def downgrade() -> None:
			op.drop_table("users")
		""",
	)
	r = runner.invoke(app, ["migration-safety", str(d), "--format", "json"])
	assert r.exit_code == 0, r.output
	payload = json.loads(r.output)
	assert payload["migrations_scanned"] == 1
	assert isinstance(payload["findings"], list)


def test_cli_markdown_output(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"abc123_create_users.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "abc123"
		down_revision = None


		def upgrade() -> None:
			op.create_table("users", sa.Column("id", sa.String(36), primary_key=True))


		def downgrade() -> None:
			op.drop_table("users")
		""",
	)
	r = runner.invoke(app, ["migration-safety", str(d), "--format", "markdown"])
	assert r.exit_code == 0, r.output
	assert "# Migration safety scan" in r.output


def test_markdown_output_reports_no_findings_for_empty_report() -> None:
	body = render_findings_markdown(ScanReport())

	assert "No findings." in body


def test_markdown_output_groups_findings_by_severity() -> None:
	report = ScanReport(
		findings=[
			Finding(
				rule="type_narrowing",
				severity=Severity.HIGH,
				location="rev.py:7",
				message="narrowing",
				suggested_rewrite="widen first",
				blast_radius="users.email",
			),
			Finding(
				rule="not_null_in_first_create",
				severity=Severity.INFO,
				location="rev.py:8",
				message="first create",
				suggested_rewrite="no action",
				blast_radius="new table",
			),
		],
	)

	body = render_findings_markdown(report)

	assert "## HIGH (1)" in body
	assert "## INFO (1)" in body
	assert "type_narrowing" in body
	assert "Suggested rewrite: widen first" in body


def test_cli_baseline_filter_silences_finding(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"narrow.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "narrow"
		down_revision = None


		def upgrade() -> None:
			op.alter_column(
				"users",
				"email",
				existing_type=sa.String(length=320),
				type_=sa.String(length=64),
			)


		def downgrade() -> None:
			pass
		""",
	)
	# First, run unfiltered to discover the exact baseline line.
	r1 = runner.invoke(app, ["migration-safety", str(d), "--format", "json"])
	assert r1.exit_code == 1
	payload = json.loads(r1.output)
	hit = next(f for f in payload["findings"] if f["rule"] == "type_narrowing")
	location = hit["location"]
	# Format: `migration_safety: <location>: <rule>`
	baseline_line = f"migration_safety: {location}: type_narrowing"
	baseline = tmp_path / "baseline.txt"
	baseline.write_text(
		"## severity=high\n" + baseline_line + "\n",
		encoding="utf-8",
	)

	r2 = runner.invoke(
		app,
		["migration-safety", str(d), "--baseline", str(baseline)],
	)
	assert r2.exit_code == 0, r2.output


def test_cli_missing_baseline_leaves_blocking_finding_active(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"narrow.py",
		"""
		from alembic import op
		import sqlalchemy as sa

		revision = "narrow"
		down_revision = None


		def upgrade() -> None:
			op.alter_column(
				"users",
				"email",
				existing_type=sa.String(320),
				type_=sa.String(64),
			)
		""",
	)

	r = runner.invoke(
		app,
		["migration-safety", str(d), "--baseline", str(tmp_path / "missing.txt")],
	)

	assert r.exit_code == 1, r.output
	assert "type_narrowing" in r.output


def test_cli_unknown_format_uses_text_output(tmp_path: Path) -> None:
	d = tmp_path / "versions"
	d.mkdir()
	_write_migration(
		d,
		"empty.py",
		"""
		revision = "empty"
		down_revision = None


		def upgrade() -> None:
			pass
		""",
	)

	r = runner.invoke(app, ["migration-safety", str(d), "--format", "other"])

	assert r.exit_code == 0, r.output
	assert "migration-safety: scanned 1 revision(s)" in r.output


def test_cli_missing_dir_exit_2(tmp_path: Path) -> None:
	r = runner.invoke(app, ["migration-safety", str(tmp_path / "nope")])
	assert r.exit_code == 2


def test_cli_file_path_exit_2(tmp_path: Path) -> None:
	path = tmp_path / "migration.py"
	path.write_text("revision = 'x'\n", encoding="utf-8")

	r = runner.invoke(app, ["migration-safety", str(path)])

	assert r.exit_code == 2
	assert "is a file" in r.output


def test_command_rejects_file_path_when_called_directly(tmp_path: Path) -> None:
	path = tmp_path / "migration.py"
	path.write_text("revision = 'x'\n", encoding="utf-8")

	with pytest.raises(typer.Exit) as exc_info:
		migration_safety_cmd(path)

	assert exc_info.value.exit_code == 2


def test_ast_helper_edge_cases() -> None:
	assert _attribute_chain(_call("factory().create_index()").func) == ""

	dynamic_kwarg = _call("f(flag=value)")
	assert _kwarg_truthy(dynamic_kwarg, "flag") is True
	assert _kwarg_truthy(dynamic_kwarg, "flag", expect_false=True) is False

	assert _string_arg(_call("f()"), 0) is None
	assert _string_arg(_call("f(123)"), 0) is None

	assert _column_argument(_call("op.add_column('orders', field)")) is None
	assert _column_argument(_call("op.add_column('orders', sa.Field('status'))")) is None

	assert _string_or_numeric_width(ast.Name(id="field", ctx=ast.Load())) is None
	assert _string_or_numeric_width(_call("sa.Boolean()")) is None
	assert _string_or_numeric_width(_call("sa.String(size=12)")) is None
	assert _string_or_numeric_width(_call("sa.String()")) is None
	assert _string_or_numeric_width(_call("sa.String('wide')")) is None
	assert _string_or_numeric_width(_call("sa.String(12)")) == 12


# ---------------------------------------------------------------------------
# Baseline file format
# ---------------------------------------------------------------------------


def test_parse_baseline_ignores_blank_comments_and_other_lines(tmp_path: Path) -> None:
	baseline = tmp_path / "baseline.txt"
	baseline.write_text(
		"\n"
		"# comment\n"
		"not migration safety\n"
		"migration_safety: rev.py:1: type_narrowing\n",
		encoding="utf-8",
	)

	assert _parse_baseline(baseline) == {
		"migration_safety: rev.py:1: type_narrowing",
	}


def test_repo_baseline_file_has_required_headers() -> None:
	"""The shipped baseline declares each severity bucket."""
	repo_root = Path(__file__).resolve().parents[3]
	bp = repo_root / "scripts" / "ci" / "ratchets" / "migration_safety_baseline.txt"
	assert bp.is_file(), f"baseline file missing at {bp}"
	body = bp.read_text(encoding="utf-8")
	assert "## severity=critical" in body
	assert "## severity=high" in body
	assert "## severity=warn" in body
