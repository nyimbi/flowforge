"""LifecycleAnalyzer."""

from __future__ import annotations

from flowforge_jtbd.lint.lifecycle import LifecycleAnalyzer
from flowforge_jtbd.spec import JtbdLintSpec, StageDecl

from .conftest import make_bundle, make_full_spec


def _issue_rules(issues) -> set[str]:
	return {i.rule for i in issues}


def test_complete_spec_emits_no_required_errors() -> None:
	spec = make_full_spec("complete")
	bundle = make_bundle([spec])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	errors = [i for i in issues if i.severity == "error"]
	assert errors == []


def test_missing_required_stage_is_error() -> None:
	spec = JtbdLintSpec(
		jtbd_id="incomplete",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
		],
	)
	bundle = make_bundle([spec])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	errors = [i for i in issues if i.severity == "error"]
	assert len(errors) == 1
	assert errors[0].rule == "missing_required_stage"
	assert errors[0].stage == "audit"
	assert "audit_handled_by" in (errors[0].fixhint or "")


def test_stage_delegation_resolves_to_present_jtbd() -> None:
	delegate = make_full_spec("audit_log")
	spec = JtbdLintSpec(
		jtbd_id="ledger",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			StageDecl(name="audit", handled_by="audit_log"),
		],
	)
	bundle = make_bundle([spec, delegate])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	errors = [i for i in issues if i.severity == "error"]
	assert errors == []


def test_stage_delegation_to_missing_jtbd_is_error() -> None:
	spec = JtbdLintSpec(
		jtbd_id="ledger",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			StageDecl(name="audit", handled_by="ghost"),
		],
	)
	bundle = make_bundle([spec])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	rules = _issue_rules(i for i in issues if i.severity == "error")
	assert "stage_delegation_unresolved" in rules


def test_stage_delegation_to_jtbd_lacking_stage_is_error() -> None:
	delegate = JtbdLintSpec(
		jtbd_id="audit_log",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			# audit missing
		],
	)
	spec = JtbdLintSpec(
		jtbd_id="ledger",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			StageDecl(name="audit", handled_by="audit_log"),
		],
	)
	bundle = make_bundle([spec, delegate])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	rules = _issue_rules(i for i in issues if i.severity == "error")
	assert "stage_delegation_unfulfilled" in rules


def test_undo_is_optional_info_hint() -> None:
	spec = make_full_spec("regular")
	bundle = make_bundle([spec])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	infos = [i for i in issues if i.severity == "info"]
	assert any(i.rule == "optional_stage_recommended" and i.stage == "undo" for i in infos)


def test_optional_hint_can_be_disabled() -> None:
	spec = make_full_spec("regular")
	bundle = make_bundle([spec])
	issues = LifecycleAnalyzer(hint_optional=False).analyze(bundle, spec)
	assert all(i.rule != "optional_stage_recommended" for i in issues)


def test_duplicate_stage_is_warning() -> None:
	spec = JtbdLintSpec(
		jtbd_id="dup",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			StageDecl(name="audit"),
		],
	)
	bundle = make_bundle([spec])
	issues = LifecycleAnalyzer().analyze(bundle, spec)
	dup = [i for i in issues if i.rule == "duplicate_stage"]
	assert len(dup) == 1
	assert dup[0].severity == "warning"
	assert dup[0].stage == "execute"


def test_custom_required_stages_override() -> None:
	spec = JtbdLintSpec(
		jtbd_id="x",
		version="1.0.0",
		stages=[StageDecl(name="execute")],
	)
	bundle = make_bundle([spec])
	analyzer = LifecycleAnalyzer(
		required_stages=("execute",),
		optional_stages=(),
		hint_optional=False,
	)
	issues = analyzer.analyze(bundle, spec)
	assert all(i.severity != "error" for i in issues)
