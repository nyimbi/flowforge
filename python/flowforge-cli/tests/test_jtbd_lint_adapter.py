"""Adapter coverage for ``flowforge jtbd lint`` (E-9).

The CLI-level smoke tests live in ``test_jtbd_lint_cmd.py``. This file
focuses on the on-disk → lint-side bundle adapter (``_adapt_to_lint_bundle``
and ``_adapt_shared_roles``) and on the role-shape semantics that
distinguish a list-of-names ``shared.roles`` (default-tier=0) from a
dict-shape ``shared.roles`` (per-role default_tier).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.commands.jtbd_lint import (
	_adapt_shared_roles,
	_adapt_to_lint_bundle,
)
from flowforge_cli.main import app


runner = CliRunner()


_FULL_STAGES: list[dict[str, str]] = [
	{"name": "discover"},
	{"name": "execute"},
	{"name": "error_handle"},
	{"name": "report"},
	{"name": "audit"},
]


def _spec(
	*,
	jtbd_id: str,
	stages: list[dict[str, str]] | None = None,
	requires: list[str] | None = None,
	actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
	out: dict[str, Any] = {
		"id": jtbd_id,
		"version": "1.0.0",
		"stages": stages if stages is not None else list(_FULL_STAGES),
	}
	if requires is not None:
		out["requires"] = requires
	if actor is not None:
		out["actor"] = actor
	return out


def _bundle(
	*,
	name: str = "demo",
	jtbds: list[dict[str, Any]] | None = None,
	shared_roles: Any = None,
) -> dict[str, Any]:
	bundle: dict[str, Any] = {
		"project": {"name": name, "version": "1.0.0"},
		"jtbds": jtbds or [_spec(jtbd_id="job_a")],
	}
	if shared_roles is not None:
		bundle["shared"] = {"roles": shared_roles}
	return bundle


@pytest.fixture
def write_bundle(tmp_path: Path):
	def _write(bundle: dict[str, Any], *, name: str = "jtbd-bundle.json") -> Path:
		path = tmp_path / name
		path.write_text(json.dumps(bundle), encoding="utf-8")
		return path

	return _write


# ---------------------------------------------------------------------------
# _adapt_to_lint_bundle
# ---------------------------------------------------------------------------


def test_adapt_to_lint_bundle_minimal() -> None:
	out = _adapt_to_lint_bundle(_bundle())
	assert out["bundle_id"] == "demo"
	assert out["jtbds"][0]["jtbd_id"] == "job_a"
	assert out["jtbds"][0]["version"] == "1.0.0"
	assert out["shared_roles"] == {}


def test_adapt_to_lint_bundle_defaults_unknown_bundle_id() -> None:
	bundle = _bundle()
	bundle["project"] = {}
	out = _adapt_to_lint_bundle(bundle)
	assert out["bundle_id"] == "unknown"


def test_adapt_to_lint_bundle_keeps_explicit_jtbd_id() -> None:
	bundle = _bundle(jtbds=[{
		"jtbd_id": "explicit",
		"version": "2.0.0",
		"stages": list(_FULL_STAGES),
	}])
	out = _adapt_to_lint_bundle(bundle)
	assert out["jtbds"][0]["jtbd_id"] == "explicit"
	assert out["jtbds"][0]["version"] == "2.0.0"


def test_adapt_to_lint_bundle_defaults_missing_version() -> None:
	bundle = _bundle(jtbds=[{"id": "x", "stages": list(_FULL_STAGES)}])
	out = _adapt_to_lint_bundle(bundle)
	assert out["jtbds"][0]["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# _adapt_shared_roles
# ---------------------------------------------------------------------------


def test_adapt_shared_roles_list_form_uses_default_tier_zero() -> None:
	out = _adapt_shared_roles({"roles": ["clerk", "banker"]})
	assert out == {
		"clerk": {"name": "clerk"},
		"banker": {"name": "banker"},
	}


def test_adapt_shared_roles_dict_form_preserves_tier_and_capacities() -> None:
	out = _adapt_shared_roles({"roles": {
		"banker": {"default_tier": 2, "capacities": ["approver"]},
	}})
	assert out["banker"]["name"] == "banker"
	assert out["banker"]["default_tier"] == 2
	assert out["banker"]["capacities"] == ["approver"]


def test_adapt_shared_roles_int_shorthand_sets_default_tier() -> None:
	out = _adapt_shared_roles({"roles": {"banker": 2}})
	assert out["banker"]["default_tier"] == 2


def test_adapt_shared_roles_empty_inputs() -> None:
	assert _adapt_shared_roles({}) == {}
	assert _adapt_shared_roles({"roles": []}) == {}
	assert _adapt_shared_roles({"roles": None}) == {}


# ---------------------------------------------------------------------------
# Role-shape end-to-end semantics through the CLI
# ---------------------------------------------------------------------------


def test_lint_role_dict_satisfies_tier_check(write_bundle) -> None:
	# banker default_tier=2 declared via dict shape ⇒ no authority error
	# when a JTBD requires tier=2.
	spec = _spec(jtbd_id="x", actor={"role": "banker", "tier": 2})
	bundle_path = write_bundle(_bundle(
		jtbds=[spec],
		shared_roles={"banker": {"default_tier": 2}},
	))
	result = runner.invoke(app, ["jtbd", "lint", "--bundle", str(bundle_path)])
	assert result.exit_code == 0, result.output
	assert "actor_authority_insufficient" not in result.output


def test_lint_role_list_yields_authority_error(write_bundle) -> None:
	# List-shape ⇒ default_tier=0 ⇒ tier=2 spec fails authority check.
	spec = _spec(jtbd_id="x", actor={"role": "banker", "tier": 2})
	bundle_path = write_bundle(_bundle(
		jtbds=[spec],
		shared_roles=["banker"],
	))
	result = runner.invoke(app, ["jtbd", "lint", "--bundle", str(bundle_path)])
	assert result.exit_code == 1, result.output
	assert "actor_authority_insufficient" in result.output


def test_lint_strict_promotes_warning_to_failure(write_bundle) -> None:
	# Undeclared role → warning. Non-strict: exit 0. Strict: exit 1.
	spec = _spec(jtbd_id="x", actor={"role": "ghost"})
	bundle_path = write_bundle(_bundle(jtbds=[spec]))

	non_strict = runner.invoke(app, [
		"jtbd", "lint", "--bundle", str(bundle_path),
	])
	assert non_strict.exit_code == 0
	assert "actor_role_undeclared" in non_strict.output

	strict = runner.invoke(app, [
		"jtbd", "lint", "--bundle", str(bundle_path), "--strict",
	])
	assert strict.exit_code == 1
