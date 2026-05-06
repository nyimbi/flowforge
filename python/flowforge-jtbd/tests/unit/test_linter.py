"""End-to-end Linter orchestration."""

from __future__ import annotations

from flowforge_jtbd.lint import (
	Issue,
	Linter,
	RuleRegistry,
	StaticRulePack,
)
from flowforge_jtbd.lint.lifecycle import LifecycleAnalyzer
from flowforge_jtbd.spec import (
	ActorRef,
	JtbdBundle,
	JtbdLintSpec,
	RoleDef,
	StageDecl,
)

from .conftest import make_bundle, make_full_spec


def test_clean_bundle_is_ok() -> None:
	a = make_full_spec(
		"party_kyc",
		actor=ActorRef(role="clerk", tier=1),
	)
	b = make_full_spec(
		"account_open",
		actor=ActorRef(role="banker", tier=2),
		requires=["party_kyc"],
	)
	bundle = make_bundle(
		[a, b],
		shared_roles={
			"clerk": RoleDef(name="clerk", default_tier=1),
			"banker": RoleDef(name="banker", default_tier=2),
		},
	)
	report = Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
	).lint(bundle)
	assert report.ok, report.errors()
	assert report.topological_order == ["party_kyc", "account_open"]
	# All specs accounted for.
	assert {r.jtbd_id for r in report.results} == {"party_kyc", "account_open"}


def test_lifecycle_error_makes_report_not_ok() -> None:
	bad = JtbdLintSpec(
		jtbd_id="bad",
		version="1.0.0",
		stages=[StageDecl(name="execute")],  # missing four required stages
	)
	bundle = make_bundle([bad])
	report = Linter().lint(bundle)
	assert report.ok is False
	# Error issues attached to the spec, not bundle level.
	by_id = {r.jtbd_id: r for r in report.results}
	rules = {i.rule for i in by_id["bad"].issues}
	assert "missing_required_stage" in rules


def test_dependency_cycle_makes_report_not_ok() -> None:
	a = make_full_spec("a", requires=["b"])
	b = make_full_spec("b", requires=["a"])
	bundle = make_bundle([a, b])
	report = Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
	).lint(bundle)
	assert report.ok is False
	rules = {i.rule for i in report.bundle_issues}
	assert "cycle_detected" in rules
	assert report.topological_order is None


def test_actor_authority_insufficient_makes_report_not_ok() -> None:
	spec = make_full_spec(
		"x",
		actor=ActorRef(role="clerk", tier=5),
	)
	bundle = make_bundle(
		[spec],
		shared_roles={"clerk": RoleDef(name="clerk", default_tier=1)},
	)
	report = Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
	).lint(bundle)
	assert report.ok is False


def test_dict_input_accepted() -> None:
	d = {
		"bundle_id": "from-dict",
		"jtbds": [
			{
				"jtbd_id": "x",
				"version": "1.0.0",
				"stages": [
					{"name": "discover"},
					{"name": "execute"},
					{"name": "error_handle"},
					{"name": "report"},
					{"name": "audit"},
				],
			},
		],
	}
	report = Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
	).lint(d)
	assert report.ok


def test_pluggable_rule_invoked_per_spec() -> None:
	captured: list[str] = []

	class _Capture:
		rule_id = "capture"

		def check(self, bundle: JtbdBundle, spec: JtbdLintSpec | None) -> list[Issue]:
			captured.append(spec.jtbd_id if spec is not None else "<bundle>")
			return []

	registry = RuleRegistry(packs=[StaticRulePack("p", [_Capture()])])
	a = make_full_spec("a")
	b = make_full_spec("b")
	bundle = make_bundle([a, b])
	Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
		registry=registry,
	).lint(bundle)
	# One bundle-level call + one per spec.
	assert "<bundle>" in captured
	assert "a" in captured
	assert "b" in captured


def test_pluggable_rule_issues_are_aggregated() -> None:
	class _Reject:
		rule_id = "reject-all"

		def check(self, bundle: JtbdBundle, spec: JtbdLintSpec | None) -> list[Issue]:
			if spec is None:
				return []
			return [Issue(
				severity="error",
				rule=self.rule_id,
				message=f"rejected {spec.jtbd_id}",
			)]

	registry = RuleRegistry(packs=[StaticRulePack("p", [_Reject()])])
	a = make_full_spec("a")
	bundle = make_bundle([a])
	report = Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
		registry=registry,
	).lint(bundle)
	assert report.ok is False
	rules = {i.rule for r in report.results for i in r.issues}
	assert "reject-all" in rules


def test_report_warnings_helper_collects_warnings() -> None:
	# Configure a bundle with a duplicate stage (warning) and missing
	# stage (error). Helpers should bucket each correctly.
	bad = JtbdLintSpec(
		jtbd_id="bad",
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			# audit missing
		],
	)
	bundle = make_bundle([bad])
	report = Linter(
		lifecycle=LifecycleAnalyzer(hint_optional=False),
	).lint(bundle)
	assert any(i.rule == "duplicate_stage" for i in report.warnings())
	assert any(i.rule == "missing_required_stage" for i in report.errors())
