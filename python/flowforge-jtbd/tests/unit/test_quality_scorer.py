"""Tests for E-16 — QualityScorer.

Covers:
- DimensionScore and QualityReport models
- Individual dimension heuristics (clarity, actionability, solution_decoupling,
  measurable_outcome)
- QualityScorer.score_sync with full/partial/empty specs
- score_jtbd convenience function
- Low-quality threshold behaviour
- LowQualityRule + LowQualityRulePack linter integration
- LlmProvider protocol conformance
"""

from __future__ import annotations

from typing import Any

from flowforge_jtbd.ai.quality import (
	DimensionScore,
	LlmProvider,
	QualityReport,
	QualityScorer,
	score_jtbd,
)
from flowforge_jtbd.lint import Linter, RuleRegistry
from flowforge_jtbd.lint.quality import LowQualityRule, LowQualityRulePack
from flowforge_jtbd.spec import JtbdLintSpec, StageDecl

from .conftest import make_bundle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _good_spec() -> dict[str, Any]:
	return {
		"id": "claim_intake",
		"situation": "A policyholder needs to report a loss event to start the claim process.",
		"motivation": "Recover insured losses quickly and document the FNOL accurately.",
		"outcome": "A claim record is created and queued within the SLA window.",
		"success_criteria": [
			"Claim record created within 2 minutes of submission.",
			"FNOL data captured with no required fields missing.",
			"Adjuster assigned within 4 hours of submission.",
		],
	}


def _poor_spec() -> dict[str, Any]:
	return {
		"id": "bad_jtbd",
		"situation": "",
		"motivation": "",
		"outcome": "handled properly",
		"success_criteria": [],
	}


def _solution_coupled_spec() -> dict[str, Any]:
	return {
		"id": "coupled_jtbd",
		"situation": "User should navigate to the claims screen and click the submit button.",
		"motivation": "Use the ClaimsHub system to fill in the claim form.",
		"outcome": "Claim form submitted via the dashboard.",
		"success_criteria": ["User clicks the confirm button."],
	}


# ---------------------------------------------------------------------------
# DimensionScore model
# ---------------------------------------------------------------------------

def test_dimension_score_fields() -> None:
	d = DimensionScore(name="clarity", score=80, findings=["Good."])
	assert d.name == "clarity"
	assert d.score == 80
	assert d.findings == ["Good."]


def test_dimension_score_score_bounds() -> None:
	d = DimensionScore(name="test", score=0)
	assert d.score == 0
	d2 = DimensionScore(name="test", score=100)
	assert d2.score == 100


# ---------------------------------------------------------------------------
# QualityReport model
# ---------------------------------------------------------------------------

def test_quality_report_low_quality_flag() -> None:
	dims = [DimensionScore(name="x", score=50)]
	r = QualityReport(jtbd_id="x", score=50, dimensions=dims, low_quality=True)
	assert r.low_quality


def test_quality_report_not_low_quality() -> None:
	dims = [DimensionScore(name="x", score=80)]
	r = QualityReport(jtbd_id="x", score=80, dimensions=dims, low_quality=False)
	assert not r.low_quality


# ---------------------------------------------------------------------------
# score_jtbd convenience function
# ---------------------------------------------------------------------------

def test_good_spec_scores_above_60() -> None:
	report = score_jtbd(_good_spec())
	assert report.score >= 60, f"Expected ≥60, got {report.score}"


def test_poor_spec_scores_below_good_spec() -> None:
	good = score_jtbd(_good_spec())
	poor = score_jtbd(_poor_spec())
	assert good.score > poor.score


def test_empty_spec_is_low_quality() -> None:
	report = score_jtbd({"id": "empty"})
	assert report.low_quality


def test_solution_coupled_spec_scores_lower_than_good() -> None:
	good = score_jtbd(_good_spec())
	coupled = score_jtbd(_solution_coupled_spec())
	assert good.score > coupled.score


def test_report_has_four_dimensions() -> None:
	report = score_jtbd(_good_spec())
	names = {d.name for d in report.dimensions}
	assert names == {"clarity", "actionability", "solution_decoupling", "measurable_outcome"}


def test_jtbd_id_extracted_from_id_field() -> None:
	report = score_jtbd({"id": "my_jtbd"})
	assert report.jtbd_id == "my_jtbd"


def test_jtbd_id_falls_back_to_jtbd_id_field() -> None:
	report = score_jtbd({"jtbd_id": "other_jtbd"})
	assert report.jtbd_id == "other_jtbd"


def test_low_quality_flag_matches_threshold() -> None:
	# Default threshold is 60.
	report = score_jtbd({"id": "x"})
	assert report.low_quality == (report.score < 60)


def test_custom_threshold_applied() -> None:
	report = score_jtbd(_good_spec(), threshold=90)
	# Even a good spec might not reach 90.
	assert report.low_quality == (report.score < 90)


# ---------------------------------------------------------------------------
# Dimension heuristics
# ---------------------------------------------------------------------------

def test_measurable_criteria_boosts_actionability() -> None:
	with_criteria = score_jtbd({**_good_spec()})
	without = score_jtbd({**_good_spec(), "success_criteria": []})
	a_with = next(d for d in with_criteria.dimensions if d.name == "actionability")
	a_without = next(d for d in without.dimensions if d.name == "actionability")
	assert a_with.score > a_without.score


def test_observable_outcome_boosts_measurable_outcome() -> None:
	good_outcome = score_jtbd({**_good_spec(), "outcome": "A claim record is created."})
	vague_outcome = score_jtbd({**_good_spec(), "outcome": "Claim is handled properly."})
	mo_good = next(d for d in good_outcome.dimensions if d.name == "measurable_outcome")
	mo_vague = next(d for d in vague_outcome.dimensions if d.name == "measurable_outcome")
	assert mo_good.score > mo_vague.score


def test_solution_coupled_spec_low_decoupling_score() -> None:
	report = score_jtbd(_solution_coupled_spec())
	decoupling = next(d for d in report.dimensions if d.name == "solution_decoupling")
	# Heavy coupling → low score.
	assert decoupling.score < 70


def test_clean_spec_high_decoupling_score() -> None:
	report = score_jtbd(_good_spec())
	decoupling = next(d for d in report.dimensions if d.name == "solution_decoupling")
	assert decoupling.score >= 80


def test_empty_fields_low_clarity() -> None:
	report = score_jtbd(_poor_spec())
	clarity = next(d for d in report.dimensions if d.name == "clarity")
	assert clarity.score < 60


def test_findings_non_empty() -> None:
	report = score_jtbd(_good_spec())
	for dim in report.dimensions:
		assert len(dim.findings) >= 1, f"No findings for {dim.name}"


# ---------------------------------------------------------------------------
# QualityScorer class
# ---------------------------------------------------------------------------

def test_scorer_score_sync_returns_report() -> None:
	scorer = QualityScorer()
	report = scorer.score_sync(_good_spec())
	assert isinstance(report, QualityReport)
	assert 0 <= report.score <= 100


def test_scorer_llm_blended_false_without_llm() -> None:
	report = QualityScorer().score_sync(_good_spec())
	assert not report.llm_blended


# ---------------------------------------------------------------------------
# LowQualityRule linter integration
# ---------------------------------------------------------------------------

def _make_lint_spec(jtbd_id: str, **extra_fields: Any) -> JtbdLintSpec:
	"""Build a JtbdLintSpec with extra natural-language payload."""
	return JtbdLintSpec(
		jtbd_id=jtbd_id,
		version="1.0.0",
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			StageDecl(name="audit"),
		],
		**extra_fields,
	)


def test_low_quality_rule_warns_on_poor_spec() -> None:
	rule = LowQualityRule()
	spec = _make_lint_spec("bad_jtbd")
	bundle = make_bundle([spec])
	issues = rule.check(bundle, spec)
	assert any(i.rule == "low_quality_jtbd" for i in issues)
	assert all(i.severity == "warning" for i in issues)


def test_low_quality_rule_no_issue_on_bundle_level() -> None:
	rule = LowQualityRule()
	bundle = make_bundle([_make_lint_spec("demo")])
	issues = rule.check(bundle, None)
	assert issues == []


def test_low_quality_rule_no_warning_for_high_quality() -> None:
	"""A spec with all NL fields populated and measurable criteria passes."""
	rule = LowQualityRule(threshold=1)  # threshold=1 → almost everything passes
	spec = _make_lint_spec("demo")
	bundle = make_bundle([spec])
	issues = rule.check(bundle, spec)
	assert issues == []


def test_low_quality_rule_issue_has_score_in_extra() -> None:
	rule = LowQualityRule()
	spec = _make_lint_spec("bad_jtbd")
	bundle = make_bundle([spec])
	issues = rule.check(bundle, spec)
	if issues:
		assert "score" in issues[0].extra
		assert "threshold" in issues[0].extra


# ---------------------------------------------------------------------------
# LowQualityRulePack + Linter integration
# ---------------------------------------------------------------------------

def test_pack_id_is_quality() -> None:
	pack = LowQualityRulePack()
	assert pack.pack_id == "quality"


def test_pack_has_one_rule() -> None:
	pack = LowQualityRulePack()
	assert len(pack.rules()) == 1
	assert pack.rules()[0].rule_id == "low_quality_jtbd"


def test_linter_with_quality_pack_warns_on_poor_spec() -> None:
	pack = LowQualityRulePack()
	registry = RuleRegistry([pack])
	spec = _make_lint_spec("bad_jtbd")
	bundle = make_bundle([spec])
	report = Linter(registry=registry).lint(bundle)
	# Warnings don't flip ok to False.
	assert report.ok
	all_issues = [i for r in report.results for i in r.issues]
	assert any(i.rule == "low_quality_jtbd" for i in all_issues)


def test_linter_quality_pack_no_error_on_clean_bundle() -> None:
	pack = LowQualityRulePack()
	registry = RuleRegistry([pack])
	bundle = make_bundle([_make_lint_spec("x")])
	report = Linter(registry=registry).lint(bundle)
	assert not report.errors()


# ---------------------------------------------------------------------------
# LlmProvider protocol conformance
# ---------------------------------------------------------------------------

class _MockLlm:
	"""Minimal mock that satisfies the LlmProvider Protocol."""

	async def generate(self, _prompt: str, *, max_tokens: int = 4000, temperature: float = 0.2) -> str:  # noqa: ARG002
		return '{"clarity": 90, "actionability": 85, "solution_decoupling": 95, "measurable_outcome": 88}'


def test_mock_llm_satisfies_protocol() -> None:
	assert isinstance(_MockLlm(), LlmProvider)


async def test_scorer_with_llm_blends_scores() -> None:
	scorer = QualityScorer(llm=_MockLlm())
	report = await scorer.score_async(_good_spec())
	assert report.llm_blended
	assert 0 <= report.score <= 100
