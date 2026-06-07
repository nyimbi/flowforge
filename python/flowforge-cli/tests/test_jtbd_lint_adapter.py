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

from flowforge_cli.commands import jtbd_lint as jtbd_lint_module
from flowforge_cli.commands.jtbd_lint import (
	_adapt_shared_roles,
	_adapt_to_lint_bundle,
	_find_default_bundle,
	_format_text,
)
from flowforge_cli.main import app
from flowforge_jtbd.lint.results import Issue, JtbdResult, LintReport


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


def test_adapt_to_lint_bundle_strips_generator_actor_external_flag() -> None:
	bundle = _bundle(jtbds=[
		_spec(jtbd_id="x", actor={"role": "claimant", "external": True})
	])
	out = _adapt_to_lint_bundle(bundle)
	assert out["jtbds"][0]["actor"] == {"role": "claimant"}


# ---------------------------------------------------------------------------
# _adapt_shared_roles
# ---------------------------------------------------------------------------


def test_adapt_shared_roles_list_form_uses_default_tier_zero() -> None:
	out = _adapt_shared_roles({"roles": ["clerk", "banker"]})
	assert out == {
		"clerk": {"name": "clerk"},
		"banker": {"name": "banker"},
	}


def test_adapt_shared_roles_list_form_accepts_role_dicts() -> None:
	out = _adapt_shared_roles({"roles": ["clerk", {"name": "banker", "default_tier": 2}, ""]})
	assert out == {
		"clerk": {"name": "clerk"},
		"banker": {"name": "banker", "default_tier": 2},
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


def test_adapt_shared_roles_ignores_unknown_shapes() -> None:
	assert _adapt_shared_roles({"roles": {"banker": "tier-two"}}) == {}
	assert _adapt_shared_roles({"roles": "banker"}) == {}


def test_adapt_shared_roles_empty_inputs() -> None:
	assert _adapt_shared_roles({}) == {}
	assert _adapt_shared_roles({"roles": []}) == {}
	assert _adapt_shared_roles({"roles": None}) == {}


# ---------------------------------------------------------------------------
# Formatting and default discovery
# ---------------------------------------------------------------------------


def test_format_text_includes_fixhints_and_topological_order() -> None:
	report = LintReport(
		ok=False,
		bundle_issues=[
			Issue(
				severity="error",
				rule="bundle_rule",
				message="Bundle failed",
				fixhint="Fix the bundle",
			)
		],
		results=[
			JtbdResult(
				jtbd_id="claim_intake",
				version="1.0.0",
				issues=[
					Issue(
						severity="warning",
						rule="jtbd_rule",
						message="JTBD warning",
						fixhint="Fix the JTBD",
					)
				],
			)
		],
		topological_order=["a", "b"],
	)

	out = _format_text(report, "demo")

	assert "[ERR] bundle" in out
	assert "fixhint: Fix the bundle" in out
	assert "[WRN] claim_intake" in out
	assert "fixhint: Fix the JTBD" in out
	assert "topological order: a → b" in out
	assert "result: FAIL" in out


def test_format_text_handles_clean_report_and_issues_without_fixhints() -> None:
	clean = _format_text(LintReport(ok=True), "demo")
	assert "ok — no issues found" in clean
	assert "result: ok" in clean

	no_fixhints = _format_text(
		LintReport(
			ok=False,
			bundle_issues=[
				Issue(severity="error", rule="bundle_rule", message="Bundle failed")
			],
			results=[
				JtbdResult(
					jtbd_id="claim_intake",
					version="1.0.0",
					issues=[
						Issue(
							severity="warning",
							rule="jtbd_rule",
							message="JTBD warning",
						)
					],
				)
			],
		),
		"demo",
	)
	assert "fixhint:" not in no_fixhints
	assert "[ERR] bundle" in no_fixhints
	assert "[WRN] claim_intake" in no_fixhints


def test_find_default_bundle_uses_first_existing_candidate(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.chdir(tmp_path)
	(tmp_path / "jtbd-bundle.json").write_text("{}", encoding="utf-8")

	assert _find_default_bundle() == Path("jtbd-bundle.json")


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
	# Exit 2 = warnings present, non-strict (per jtbd_lint_cmd docstring:
	# "0=clean, 1=errors or strict-warnings, 2=warnings-only").
	assert non_strict.exit_code == 2
	assert "actor_role_undeclared" in non_strict.output

	strict = runner.invoke(app, [
		"jtbd", "lint", "--bundle", str(bundle_path), "--strict",
	])
	assert strict.exit_code == 1


def test_lint_without_bundle_reports_missing_default(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.chdir(tmp_path)

	result = runner.invoke(app, ["jtbd", "lint"])

	assert result.exit_code == 1
	assert "no bundle file found" in result.output


def test_lint_uses_default_bundle_when_omitted(
	write_bundle,
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.chdir(tmp_path)
	write_bundle(_bundle(), name="jtbd-bundle.json")

	result = runner.invoke(app, ["jtbd", "lint"])

	assert result.exit_code == 0, result.output
	assert "bundle: demo" in result.output


def test_lint_reports_linter_exceptions(
	write_bundle,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	class ExplodingLinter:
		def lint(self, _adapted: dict[str, Any]) -> LintReport:
			raise RuntimeError("boom")

	monkeypatch.setattr(jtbd_lint_module, "Linter", ExplodingLinter)
	bundle_path = write_bundle(_bundle())

	result = runner.invoke(app, ["jtbd", "lint", "--bundle", str(bundle_path)])

	assert result.exit_code == 1
	assert "linter raised an exception: boom" in result.output
