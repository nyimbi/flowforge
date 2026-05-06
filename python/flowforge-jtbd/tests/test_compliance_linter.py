"""Tests for E-23 ComplianceLinter — 8 regime catalogs + two lint rules."""

from __future__ import annotations

from typing import Any

import pytest

from flowforge_jtbd.compliance.catalog import REQUIRED_JOBS, missing_jobs, required_jobs_for
from flowforge_jtbd.lint.compliance import (
	ComplianceLinterPack,
	ComplianceMissingJobRule,
	SensitivityImpliesRegimeRule,
)
from flowforge_jtbd.spec import JtbdBundle, JtbdLintSpec


# ---------------------------------------------------------------------------
# Catalog tests
# ---------------------------------------------------------------------------


def test_catalog_loaded_8_regimes() -> None:
	assert len(REQUIRED_JOBS) == 8


def test_gdpr_requires_four_jobs() -> None:
	jobs = required_jobs_for("GDPR")
	assert {"data_export", "data_erasure", "consent_capture", "breach_notification"} <= jobs


def test_hipaa_requires_five_jobs() -> None:
	jobs = required_jobs_for("HIPAA")
	assert {"phi_access_control", "phi_audit_log", "breach_notification"} <= jobs


def test_pci_dss_requires_jobs() -> None:
	jobs = required_jobs_for("PCI-DSS")
	assert "cardholder_data_protection" in jobs


def test_sox_requires_jobs() -> None:
	jobs = required_jobs_for("SOX")
	assert "financial_reporting_audit" in jobs


def test_unknown_regime_returns_empty() -> None:
	assert required_jobs_for("UNKNOWN") == frozenset()


def test_missing_jobs_detects_gaps() -> None:
	gaps = missing_jobs(["GDPR"], set())
	assert "GDPR" in gaps
	assert len(gaps["GDPR"]) > 0


def test_missing_jobs_no_gaps_when_all_present() -> None:
	gdpr_jobs = required_jobs_for("GDPR")
	gaps = missing_jobs(["GDPR"], set(gdpr_jobs))
	assert gaps == {}


def test_all_8_regimes_have_at_least_3_jobs() -> None:
	for regime, jobs in REQUIRED_JOBS.items():
		assert len(jobs) >= 3, f"{regime} has fewer than 3 required jobs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bundle_with_specs(*specs: dict[str, Any]) -> JtbdBundle:
	"""Build a JtbdBundle from lint-spec dicts."""
	return JtbdBundle.model_validate({
		"bundle_id": "test-bundle",
		"jtbds": [
			{
				"jtbd_id": s.get("id", s.get("jtbd_id", "x")),
				"version": s.get("version", "1.0.0"),
				**s,
			}
			for s in specs
		],
	})


def _spec(
	jtbd_id: str,
	*,
	sensitivity: list[str] | None = None,
	compliance: list[str] | None = None,
) -> dict[str, Any]:
	s: dict[str, Any] = {
		"jtbd_id": jtbd_id,
		"version": "1.0.0",
	}
	if sensitivity is not None:
		s["data_sensitivity"] = sensitivity
	if compliance is not None:
		s["compliance"] = compliance
	return s


def _lint_spec(
	jtbd_id: str,
	*,
	sensitivity: list[str] | None = None,
	compliance: list[str] | None = None,
) -> JtbdLintSpec:
	return JtbdLintSpec.model_validate(_spec(
		jtbd_id, sensitivity=sensitivity, compliance=compliance
	))


# ---------------------------------------------------------------------------
# SensitivityImpliesRegimeRule
# ---------------------------------------------------------------------------


def test_sensitivity_rule_no_issue_when_no_sensitivity() -> None:
	bundle = _bundle_with_specs(_spec("x"))
	spec = _lint_spec("x")
	rule = SensitivityImpliesRegimeRule()
	assert rule.check(bundle, spec) == []


def test_sensitivity_rule_phi_with_hipaa_ok() -> None:
	bundle = _bundle_with_specs(_spec("x", sensitivity=["PHI"], compliance=["HIPAA"]))
	spec = _lint_spec("x", sensitivity=["PHI"], compliance=["HIPAA"])
	rule = SensitivityImpliesRegimeRule()
	assert rule.check(bundle, spec) == []


def test_sensitivity_rule_phi_missing_hipaa_is_error() -> None:
	bundle = _bundle_with_specs(_spec("x", sensitivity=["PHI"]))
	spec = _lint_spec("x", sensitivity=["PHI"])
	rule = SensitivityImpliesRegimeRule()
	issues = rule.check(bundle, spec)
	assert len(issues) == 1
	assert issues[0].severity == "error"
	assert "HIPAA" in issues[0].message
	assert issues[0].rule == "compliance.sensitivity_implies_regime"


def test_sensitivity_rule_pii_missing_gdpr_ccpa_is_error() -> None:
	bundle = _bundle_with_specs(_spec("x", sensitivity=["PII"]))
	spec = _lint_spec("x", sensitivity=["PII"])
	rule = SensitivityImpliesRegimeRule()
	issues = rule.check(bundle, spec)
	assert any("GDPR" in i.message or "CCPA" in i.message for i in issues)


def test_sensitivity_rule_skips_bundle_level_call() -> None:
	bundle = _bundle_with_specs(_spec("x", sensitivity=["PHI"]))
	rule = SensitivityImpliesRegimeRule()
	assert rule.check(bundle, None) == []


# ---------------------------------------------------------------------------
# ComplianceMissingJobRule
# ---------------------------------------------------------------------------


def test_missing_job_rule_no_compliance_no_issues() -> None:
	bundle = _bundle_with_specs(_spec("x"))
	rule = ComplianceMissingJobRule()
	assert rule.check(bundle, None) == []


def test_missing_job_rule_skips_per_spec_calls() -> None:
	bundle = _bundle_with_specs(_spec("x", compliance=["GDPR"]))
	spec = _lint_spec("x", compliance=["GDPR"])
	rule = ComplianceMissingJobRule()
	assert rule.check(bundle, spec) == []


def test_missing_job_rule_warns_on_missing_gdpr_jobs() -> None:
	bundle = _bundle_with_specs(_spec("claim_intake", compliance=["GDPR"]))
	rule = ComplianceMissingJobRule()
	issues = rule.check(bundle, None)
	# GDPR requires data_export, data_erasure etc. — none present in bundle
	assert len(issues) > 0
	assert issues[0].severity == "warning"
	assert "GDPR" in issues[0].message


def test_missing_job_rule_no_gap_when_all_jobs_present() -> None:
	gdpr_jobs = list(required_jobs_for("GDPR"))
	specs = [_spec("claim_intake", compliance=["GDPR"])]
	# Add all required GDPR job IDs as JTBD specs
	for job_id in gdpr_jobs:
		specs.append(_spec(job_id))
	bundle = _bundle_with_specs(*specs)
	rule = ComplianceMissingJobRule()
	issues = rule.check(bundle, None)
	assert issues == []


# ---------------------------------------------------------------------------
# ComplianceLinterPack integration
# ---------------------------------------------------------------------------


def test_pack_has_two_rules() -> None:
	pack = ComplianceLinterPack()
	assert len(pack.rules()) == 2
	rule_ids = {r.rule_id for r in pack.rules()}
	assert "compliance.sensitivity_implies_regime" in rule_ids
	assert "compliance.missing_required_job" in rule_ids


def test_pack_wires_into_full_linter() -> None:
	from flowforge_jtbd.lint.linter import Linter
	from flowforge_jtbd.lint.registry import RuleRegistry

	linter = Linter(registry=RuleRegistry([ComplianceLinterPack()]))
	bundle = JtbdBundle.model_validate({
		"bundle_id": "test",
		"jtbds": [_spec("phi_job", sensitivity=["PHI"], compliance=["HIPAA"])],
	})
	report = linter.lint(bundle)
	# PHI with HIPAA declared → no error
	compliance_errors = [
		i for i in report.errors()
		if "compliance" in i.rule
	]
	assert compliance_errors == []
