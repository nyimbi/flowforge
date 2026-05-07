"""E-38 — Migration RLS DDL hardening regression tests (J-01).

Audit finding (audit-fix-plan §4.1 J-01, §7 E-38):

The alembic ``r2_jtbd`` migration installs RLS policies via
``op.execute(f"ALTER TABLE {table} ...")`` over module-level table-name
tuples. Today those tuples are constants, but the f-string splice is a
SQL-injection foothold the moment a future refactor pulls table names
from any non-constant source. Audit J-01 requires:

1. An explicit allow-list of permitted table names; unknown table → ``ValueError``.
2. Identifier quoting via :func:`sqlalchemy.sql.quoted_name` (or equivalent
   strict identifier validator) for every spliced table name.

Acceptance tests:
- ``test_J_01_migration_table_allowlist`` — monkey-patched table tuple
  containing ``"users; DROP"`` causes ``_install_rls_if_postgres`` to
  raise ``ValueError`` before any SQL is emitted.
- ``test_J_01_migration_quoted_name`` — every identifier exposed for
  splicing is wrapped via :func:`quoted_name` so callers see the
  identifier-shape, not the raw string.
- ``test_J_01_alembic_dryrun_prod_shape`` — the SQLite dry-run still
  succeeds end-to-end (covered indirectly by the existing
  ``test_jtbd_alembic_upgrade.py`` suite which we re-run from this
  file via the alembic command API).

Plan reference: framework/docs/audit-fix-plan.md §4.1 J-01, §7 E-38.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# J-01 — allow-list catches malicious table names
# ---------------------------------------------------------------------------


def test_J_01_migration_table_allowlist_constant_present() -> None:
	"""The migration module exposes an immutable allow-list."""
	from flowforge_jtbd.db.alembic_bundle.versions import r2_jtbd

	assert hasattr(r2_jtbd, "_RLS_ALLOWLIST"), "missing _RLS_ALLOWLIST symbol"
	allow = r2_jtbd._RLS_ALLOWLIST
	# frozenset (or similarly immutable) — running tests must not be able to
	# mutate the allow-list and still see writes.
	assert isinstance(allow, frozenset), f"_RLS_ALLOWLIST must be frozenset, got {type(allow)}"
	# Every table in the per-tier tuples must be in the allow-list.
	for table in (
		*r2_jtbd._RLS_TABLES_TENANT_NULLABLE,
		*r2_jtbd._RLS_TABLES_TENANT_REQUIRED,
		"jtbd_domains",
	):
		assert table in allow, f"{table} not in _RLS_ALLOWLIST"


def test_J_01_migration_assert_known_table_rejects_malicious(monkeypatch) -> None:
	"""Passing a malicious identifier directly raises ``ValueError``."""
	from flowforge_jtbd.db.alembic_bundle.versions import r2_jtbd

	for bogus in (
		"users; DROP TABLE users; --",
		"jtbd_libraries; DROP",
		"; DROP",
		"' OR 1=1 --",
		"jtbd_unknown",
		"jtbd specs",  # space
		"jtbd-specs",  # hyphen — valid identifier letter set is letters/digits/_
		"",
		"1jtbd",  # leading digit
		"JTBD_LIBRARIES",  # different case → not in allow-list
	):
		with pytest.raises(ValueError):
			r2_jtbd._assert_known_table(bogus)


def test_J_01_migration_assert_known_table_accepts_valid() -> None:
	"""Valid table names pass and round-trip through ``quoted_name``."""
	from sqlalchemy.sql import quoted_name

	from flowforge_jtbd.db.alembic_bundle.versions import r2_jtbd

	for table in (
		"jtbd_libraries",
		"jtbd_specs",
		"jtbd_compositions",
		"jtbd_compositions_pins",
		"jtbd_lockfiles",
		"jtbd_domains",
	):
		got = r2_jtbd._assert_known_table(table)
		assert isinstance(got, quoted_name), f"{table} did not round-trip via quoted_name"
		assert str(got) == table


def test_J_01_install_rls_raises_on_monkeypatched_malicious_table(monkeypatch) -> None:
	"""``_install_rls_if_postgres`` must reject a poisoned tuple before any SQL.

	This is the audit's mandated test: a monkey-patched table list containing
	``"users; DROP"`` must raise ``ValueError``. We force the postgres branch
	by stubbing ``_is_postgres`` so the test runs without a live PG instance.
	"""
	from flowforge_jtbd.db.alembic_bundle.versions import r2_jtbd

	executed: list[str] = []

	# Stub op.execute and op.get_bind so we'd notice if any SQL escaped.
	class _StubOp:
		@staticmethod
		def execute(sql, *a, **kw):  # noqa: D401
			executed.append(str(sql))

	monkeypatch.setattr(r2_jtbd, "op", _StubOp)
	monkeypatch.setattr(r2_jtbd, "_is_postgres", lambda: True)
	monkeypatch.setattr(
		r2_jtbd,
		"_RLS_TABLES_TENANT_NULLABLE",
		("users; DROP TABLE users; --",),
	)

	with pytest.raises(ValueError):
		r2_jtbd._install_rls_if_postgres()

	assert executed == [], (
		f"SQL emitted before the allow-list check fired: {executed!r}"
	)


def test_J_01_drop_rls_also_validates(monkeypatch) -> None:
	"""Symmetric protection on the downgrade path."""
	from flowforge_jtbd.db.alembic_bundle.versions import r2_jtbd

	executed: list[str] = []

	class _StubOp:
		@staticmethod
		def execute(sql, *a, **kw):
			executed.append(str(sql))

	monkeypatch.setattr(r2_jtbd, "op", _StubOp)
	monkeypatch.setattr(r2_jtbd, "_is_postgres", lambda: True)
	monkeypatch.setattr(
		r2_jtbd,
		"_RLS_TABLES_TENANT_REQUIRED",
		("ok_table; DROP",),
	)

	with pytest.raises(ValueError):
		r2_jtbd._drop_rls_if_postgres()

	assert executed == [], "downgrade emitted SQL before validation"


# ---------------------------------------------------------------------------
# J-01 — alembic dry-run on prod-shape (SQLite stand-in for CI)
# ---------------------------------------------------------------------------


def test_J_01_alembic_dryrun_prod_shape(tmp_path: Path) -> None:
	"""End-to-end alembic upgrade succeeds on the SQLite prod-shape stand-in.

	The full PG variant is gated behind ``FLOWFORGE_TEST_PG_URL`` and lives
	in :mod:`flowforge_jtbd.tests.ci.test_jtbd_alembic_upgrade`. This test
	is a smoke that the hardened migration still runs on the dialect-guarded
	branch — the dry-run F-4 mitigation listed in audit-fix-plan §2 F-4.
	"""
	from alembic import command
	from alembic.config import Config
	from flowforge_jtbd.db.alembic_bundle import VERSIONS_DIR as JTBD_VERSIONS_DIR
	from flowforge_sqlalchemy.alembic_bundle import (
		BUNDLE_DIR as ENGINE_BUNDLE_DIR,
		VERSIONS_DIR as ENGINE_VERSIONS_DIR,
	)

	cfg = Config()
	cfg.set_main_option("script_location", ENGINE_BUNDLE_DIR)
	cfg.set_main_option(
		"version_locations",
		f"{ENGINE_VERSIONS_DIR} {JTBD_VERSIONS_DIR}",
	)
	cfg.set_main_option("path_separator", "space")
	cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'audit-2026.db'}")

	# upgrade then immediately downgrade — proves migration is reversible.
	command.upgrade(cfg, "r2_jtbd")
	command.downgrade(cfg, "base")
