"""Alembic bundle round-trips on SQLite (RLS skipped) and Postgres-if-available."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from flowforge_sqlalchemy.alembic_bundle import BUNDLE_DIR, VERSIONS_DIR

EXPECTED_TABLES = {
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
	# script_location holds env.py + script.py.mako; versions live in the
	# nested versions/ directory.
	cfg.set_main_option("script_location", BUNDLE_DIR)
	cfg.set_main_option("version_locations", VERSIONS_DIR)
	cfg.set_main_option("path_separator", "os")
	cfg.set_main_option("sqlalchemy.url", url)
	return cfg


def test_versions_dir_points_at_bundle() -> None:
	p = Path(VERSIONS_DIR)
	assert p.is_dir(), f"versions dir missing: {p}"
	assert (p / "r1_initial.py").is_file()


def test_sqlite_upgrade_then_downgrade_roundtrip(tmp_path: Path) -> None:
	db_path = tmp_path / "ff.sqlite"
	url = f"sqlite:///{db_path}"
	cfg = _alembic_cfg(url)

	command.upgrade(cfg, "r1_initial")

	engine = create_engine(url)
	insp = inspect(engine)
	tables_after_up = set(insp.get_table_names())
	missing = EXPECTED_TABLES - tables_after_up
	assert not missing, f"upgrade missed tables: {missing}"
	engine.dispose()

	command.downgrade(cfg, "base")

	engine = create_engine(url)
	insp = inspect(engine)
	tables_after_down = set(insp.get_table_names())
	# Alembic's own bookkeeping table can remain; everything we created
	# must be gone.
	leftover = EXPECTED_TABLES & tables_after_down
	assert not leftover, f"downgrade left tables behind: {leftover}"
	engine.dispose()


@pytest.mark.skipif(
	not os.environ.get("FLOWFORGE_TEST_PG_URL"),
	reason="postgres URL not provided (set FLOWFORGE_TEST_PG_URL to enable)",
)
def test_postgres_upgrade_roundtrip() -> None:
	url = os.environ["FLOWFORGE_TEST_PG_URL"]
	cfg = _alembic_cfg(url)
	command.upgrade(cfg, "r1_initial")
	engine = create_engine(url)
	insp = inspect(engine)
	tables = set(insp.get_table_names())
	assert EXPECTED_TABLES.issubset(tables)
	engine.dispose()
	command.downgrade(cfg, "base")
