"""Tests for the JTBD generator fixture registry."""

from __future__ import annotations

from typing import Any, cast

import pytest

from flowforge_cli.jtbd.generators import _fixture_registry


def test_register_sorts_consumes_and_updates_lookup(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	registry = dict(_fixture_registry._REGISTRY)
	monkeypatch.setattr(_fixture_registry, "_REGISTRY", registry)

	assert _fixture_registry.get("missing") == ()

	_fixture_registry.register("custom_generator", ("project.package", "jtbds[].id"))

	assert _fixture_registry.get("custom_generator") == (
		"jtbds[].id",
		"project.package",
	)
	assert "custom_generator" in _fixture_registry.all_generators()


def test_registry_helpers_validate_input_types() -> None:
	with pytest.raises(AssertionError, match="generator_name must be a string"):
		_fixture_registry.get(cast(Any, 123))

	with pytest.raises(AssertionError, match="generator_name must be a string"):
		_fixture_registry.register(cast(Any, 123), ())

	with pytest.raises(AssertionError, match="consumes must be a tuple"):
		_fixture_registry.register("custom_generator", cast(Any, ["project.package"]))
