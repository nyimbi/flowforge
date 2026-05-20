"""Alembic bundle round-trips on SQLite (RLS skipped) and Postgres-if-available."""

from __future__ import annotations

import os
import runpy
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.postgresql import JSONB

from flowforge_sqlalchemy.alembic_bundle import BUNDLE_DIR, VERSIONS_DIR
from flowforge_sqlalchemy.base import JsonB

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


def test_jsonb_uses_postgres_jsonb_type() -> None:
	seen: list[Any] = []

	class Dialect:
		name = "postgresql"

		def type_descriptor(self, typ: Any) -> Any:
			seen.append(typ)
			return typ

	typ = JsonB().load_dialect_impl(Dialect())

	assert isinstance(typ, JSONB)
	assert seen == [typ]


def test_alembic_env_runs_offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	events: list[str] = []

	class FakeConfig:
		config_file_name = str(tmp_path / "alembic.ini")

		def get_main_option(self, key: str) -> str:
			assert key == "sqlalchemy.url"
			return "sqlite:///offline.db"

	class FakeContext:
		config = FakeConfig()

		def is_offline_mode(self) -> bool:
			return True

		def configure(self, **kwargs: Any) -> None:
			events.append(f"configure:{kwargs['url']}")
			assert kwargs["literal_binds"] is True

		@contextmanager
		def begin_transaction(self):
			events.append("begin")
			yield
			events.append("end")

		def run_migrations(self) -> None:
			events.append("migrate")

	monkeypatch.setattr("logging.config.fileConfig", lambda filename: events.append(filename))
	monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(context=FakeContext()))

	runpy.run_module(
		"flowforge_sqlalchemy.alembic_bundle.env",
		run_name="__flowforge_alembic_env_offline__",
	)

	assert events == [
		str(tmp_path / "alembic.ini"),
		"configure:sqlite:///offline.db",
		"begin",
		"migrate",
		"end",
	]


def test_alembic_env_runs_online(monkeypatch: pytest.MonkeyPatch) -> None:
	events: list[str] = []

	class FakeConfig:
		config_file_name = None
		config_ini_section = "alembic"

		def get_section(self, section: str) -> dict[str, str]:
			assert section == "alembic"
			return {"sqlalchemy.url": "sqlite:///online.db"}

	class FakeContext:
		config = FakeConfig()

		def is_offline_mode(self) -> bool:
			return False

		def configure(self, **kwargs: Any) -> None:
			events.append("configure")
			assert kwargs["connection"] == "connection"

		@contextmanager
		def begin_transaction(self):
			events.append("begin")
			yield
			events.append("end")

		def run_migrations(self) -> None:
			events.append("migrate")

	class FakeConnection:
		def __enter__(self) -> str:
			events.append("connect")
			return "connection"

		def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
			events.append("disconnect")

	class FakeConnectable:
		def connect(self) -> FakeConnection:
			return FakeConnection()

	def fake_engine_from_config(
		section: dict[str, str],
		*,
		prefix: str,
		poolclass: object,
	) -> FakeConnectable:
		assert section == {"sqlalchemy.url": "sqlite:///online.db"}
		assert prefix == "sqlalchemy."
		assert poolclass is not None
		return FakeConnectable()

	import sqlalchemy

	monkeypatch.setattr(sqlalchemy, "engine_from_config", fake_engine_from_config)
	monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(context=FakeContext()))

	runpy.run_module(
		"flowforge_sqlalchemy.alembic_bundle.env",
		run_name="__flowforge_alembic_env_online__",
	)

	assert events == ["connect", "configure", "begin", "migrate", "end", "disconnect"]


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
