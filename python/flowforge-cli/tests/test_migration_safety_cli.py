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

import json
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from flowforge_cli.commands.migration_safety import (
	Severity,
	scan_directory,
)
from flowforge_cli.main import app


runner = CliRunner()


def _write_migration(dir_: Path, name: str, body: str) -> Path:
	"""Write a minimal alembic-shaped revision file."""
	path = dir_ / name
	path.write_text(textwrap.dedent(body), encoding="utf-8")
	return path


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


def test_cli_missing_dir_exit_2(tmp_path: Path) -> None:
	r = runner.invoke(app, ["migration-safety", str(tmp_path / "nope")])
	assert r.exit_code == 2


# ---------------------------------------------------------------------------
# Baseline file format
# ---------------------------------------------------------------------------


def test_repo_baseline_file_has_required_headers() -> None:
	"""The shipped baseline declares each severity bucket."""
	repo_root = Path(__file__).resolve().parents[3]
	bp = repo_root / "scripts" / "ci" / "ratchets" / "migration_safety_baseline.txt"
	assert bp.is_file(), f"baseline file missing at {bp}"
	body = bp.read_text(encoding="utf-8")
	assert "## severity=critical" in body
	assert "## severity=high" in body
	assert "## severity=warn" in body
