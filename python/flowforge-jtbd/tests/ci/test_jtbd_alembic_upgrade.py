"""Alembic ``r2_jtbd`` round-trips on SQLite + (when configured) Postgres.

Mirrors the contract in :mod:`flowforge_sqlalchemy.tests.test_alembic_upgrade`
but with the JTBD versions directory chained after ``r1_initial``.
SQLite has no RLS, so the migration's RLS DDL is dialect-guarded and
skipped here; Postgres-backed runs (when ``FLOWFORGE_TEST_PG_URL`` is
set) verify the policies install + drop cleanly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from flowforge_jtbd.db.alembic_bundle import VERSIONS_DIR as JTBD_VERSIONS_DIR
from flowforge_sqlalchemy.alembic_bundle import (
	BUNDLE_DIR as ENGINE_BUNDLE_DIR,
	VERSIONS_DIR as ENGINE_VERSIONS_DIR,
)
from sqlalchemy import create_engine, inspect

EXPECTED_JTBD_TABLES = {
	"jtbd_libraries",
	"jtbd_domains",
	"jtbd_specs",
	"jtbd_compositions",
	"jtbd_compositions_pins",
	"jtbd_lockfiles",
}

EXPECTED_ENGINE_TABLES = {
	"workflow_definitions",
	"workflow_definition_versions",
	"workflow_instances",
	"workflow_instance_tokens",
	"workflow_events",
	"workflow_saga_steps",
	"workflow_instance_quarantine",
	"business_calendars",
	"pending_signals",
	"workflow_instance_snapshots",
}


def _alembic_cfg(url: str) -> Config:
	cfg = Config()
	cfg.set_main_option("script_location", ENGINE_BUNDLE_DIR)
	# Two version directories — engine + JTBD — so alembic can resolve
	# the down_revision chain ``r1_initial → r2_jtbd``.
	cfg.set_main_option(
		"version_locations",
		f"{ENGINE_VERSIONS_DIR} {JTBD_VERSIONS_DIR}",
	)
	cfg.set_main_option("path_separator", "space")
	cfg.set_main_option("sqlalchemy.url", url)
	return cfg


def test_versions_dir_points_at_bundle() -> None:
	p = Path(JTBD_VERSIONS_DIR)
	assert p.is_dir(), f"versions dir missing: {p}"
	assert (p / "r2_jtbd.py").is_file()


def test_sqlite_upgrade_creates_jtbd_tables(tmp_path: Path) -> None:
	db_path = tmp_path / "ff.sqlite"
	url = f"sqlite:///{db_path}"
	cfg = _alembic_cfg(url)

	command.upgrade(cfg, "r2_jtbd")

	engine = create_engine(url)
	insp = inspect(engine)
	tables = set(insp.get_table_names())
	assert EXPECTED_JTBD_TABLES.issubset(tables)
	assert EXPECTED_ENGINE_TABLES.issubset(tables)
	engine.dispose()


def test_sqlite_downgrade_removes_jtbd_tables_only(tmp_path: Path) -> None:
	db_path = tmp_path / "ff.sqlite"
	url = f"sqlite:///{db_path}"
	cfg = _alembic_cfg(url)

	command.upgrade(cfg, "r2_jtbd")
	command.downgrade(cfg, "r1_initial")

	engine = create_engine(url)
	insp = inspect(engine)
	tables = set(insp.get_table_names())
	# JTBD tables are gone; engine tables stay.
	leftover_jtbd = EXPECTED_JTBD_TABLES & tables
	assert not leftover_jtbd, f"downgrade left jtbd tables: {leftover_jtbd}"
	missing_engine = EXPECTED_ENGINE_TABLES - tables
	assert not missing_engine, (
		f"downgrade also dropped engine tables: {missing_engine}"
	)
	engine.dispose()


def test_full_downgrade_to_base_clears_everything(tmp_path: Path) -> None:
	db_path = tmp_path / "ff.sqlite"
	url = f"sqlite:///{db_path}"
	cfg = _alembic_cfg(url)

	command.upgrade(cfg, "r2_jtbd")
	command.downgrade(cfg, "base")

	engine = create_engine(url)
	insp = inspect(engine)
	tables = set(insp.get_table_names())
	leftover = (EXPECTED_JTBD_TABLES | EXPECTED_ENGINE_TABLES) & tables
	assert not leftover, f"downgrade left tables behind: {leftover}"
	engine.dispose()


@pytest.mark.skipif(
	not os.environ.get("FLOWFORGE_TEST_PG_URL"),
	reason="postgres URL not provided (set FLOWFORGE_TEST_PG_URL to enable)",
)
def test_postgres_upgrade_installs_rls() -> None:
	from sqlalchemy import text

	url = os.environ["FLOWFORGE_TEST_PG_URL"]
	cfg = _alembic_cfg(url)
	command.upgrade(cfg, "r2_jtbd")

	engine = create_engine(url)
	with engine.connect() as conn:
		# RLS enabled on every JTBD table.
		for table in EXPECTED_JTBD_TABLES:
			row = conn.execute(
				text(
					"SELECT relrowsecurity FROM pg_class"
					" WHERE relname = :name AND relnamespace = 'public'::regnamespace"
				),
				{"name": table},
			).scalar()
			assert row is True, f"RLS not enabled on {table}"
	engine.dispose()
	command.downgrade(cfg, "base")
