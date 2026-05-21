"""Hermetic coverage for the bundled Alembic env module."""

from __future__ import annotations

import importlib
import logging.config
import sys
import types
from typing import Any

import pytest


class _FakeConfig:
    def __init__(self, *, config_file_name: str | None = None) -> None:
        self.config_file_name = config_file_name
        self.config_ini_section = "alembic"

    def get_main_option(self, name: str) -> str:
        assert name == "sqlalchemy.url"
        return "sqlite:///offline.db"

    def get_section(self, name: str) -> dict[str, str]:
        assert name == "alembic"
        return {"sqlalchemy.url": "sqlite:///online.db"}


class _FakeTransaction:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls

    def __enter__(self) -> "_FakeTransaction":
        self.calls.append(("begin", None))
        return self

    def __exit__(self, *_exc: object) -> None:
        self.calls.append(("end", None))


class _FakeContext:
    def __init__(self, *, offline: bool, config_file_name: str | None = None) -> None:
        self.config = _FakeConfig(config_file_name=config_file_name)
        self.offline = offline
        self.calls: list[tuple[str, Any]] = []

    def is_offline_mode(self) -> bool:
        return self.offline

    def configure(self, **kwargs: Any) -> None:
        self.calls.append(("configure", kwargs))

    def begin_transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self.calls)

    def run_migrations(self) -> None:
        self.calls.append(("run", None))


class _FakeConnection:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls

    def __enter__(self) -> "_FakeConnection":
        self.calls.append(("connect_enter", None))
        return self

    def __exit__(self, *_exc: object) -> None:
        self.calls.append(("connect_exit", None))


class _FakeEngine:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls

    def connect(self) -> _FakeConnection:
        self.calls.append(("connect", None))
        return _FakeConnection(self.calls)


def _import_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    offline: bool,
    config_file_name: str | None = None,
) -> tuple[Any, _FakeContext, list[tuple[str, Any]]]:
    # Preload real SQLAlchemy-backed model modules before faking the narrow
    # ``sqlalchemy`` import that the env module itself needs.
    import flowforge_jtbd.db.models  # noqa: F401
    import flowforge_sqlalchemy  # noqa: F401

    module_name = "flowforge_jtbd.db.alembic_bundle.env"
    sys.modules.pop(module_name, None)
    context = _FakeContext(offline=offline, config_file_name=config_file_name)
    engine_calls: list[tuple[str, Any]] = []

    fake_alembic = types.ModuleType("alembic")
    setattr(fake_alembic, "context", context)
    fake_sqlalchemy = types.ModuleType("sqlalchemy")

    def engine_from_config(
        section: dict[str, str],
        *,
        prefix: str,
        poolclass: object,
    ) -> _FakeEngine:
        engine_calls.append(("engine", (section, prefix, poolclass)))
        return _FakeEngine(engine_calls)

    setattr(fake_sqlalchemy, "engine_from_config", engine_from_config)
    setattr(fake_sqlalchemy, "pool", types.SimpleNamespace(NullPool=object()))
    monkeypatch.setitem(sys.modules, "alembic", fake_alembic)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy)
    monkeypatch.setattr(
        logging.config,
        "fileConfig",
        lambda path: context.calls.append(("fileConfig", path)),
    )

    return importlib.import_module(module_name), context, engine_calls


def test_alembic_env_runs_offline_migrations_on_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env, context, _engine_calls = _import_env(
        monkeypatch,
        offline=True,
        config_file_name="logging.ini",
    )

    assert context.calls[0] == ("fileConfig", "logging.ini")
    configure = next(call for call in context.calls if call[0] == "configure")
    assert configure[1]["url"] == "sqlite:///offline.db"
    assert configure[1]["literal_binds"] is True
    assert ("run", None) in context.calls


def test_alembic_env_runs_online_migrations_on_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _env, context, engine_calls = _import_env(monkeypatch, offline=False)

    assert engine_calls[0][0] == "engine"
    assert engine_calls[0][1][0] == {"sqlalchemy.url": "sqlite:///online.db"}
    assert engine_calls[0][1][1] == "sqlalchemy."
    configure = next(call for call in context.calls if call[0] == "configure")
    assert configure[1]["target_metadata"] is not None
    assert ("run", None) in context.calls
