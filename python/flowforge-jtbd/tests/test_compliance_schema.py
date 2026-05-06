"""Tests for E-22 sensitivity + compliance schema additions."""

from __future__ import annotations

from typing import Any

import pytest

from flowforge_jtbd.compliance.schema import (
	COMPLIANCE_REGIME_VALUES,
	DATA_SENSITIVITY_VALUES,
	SENSITIVITY_IMPLIES_REGIME,
	implied_regimes,
	missing_regimes,
)
from flowforge_jtbd.dsl.spec import (
	ComplianceRegime,
	DataSensitivity,
	JtbdBundle,
	JtbdField,
	JtbdSpec,
)


# ---------------------------------------------------------------------------
# Catalog constants
# ---------------------------------------------------------------------------


def test_five_sensitivity_values() -> None:
	assert DATA_SENSITIVITY_VALUES == {"PII", "PHI", "PCI", "secrets", "regulated"}


def test_eight_compliance_regimes() -> None:
	assert len(COMPLIANCE_REGIME_VALUES) == 8
	for regime in ("GDPR", "SOX", "HIPAA", "PCI-DSS", "ISO27001", "SOC2", "NIST-800-53", "CCPA"):
		assert regime in COMPLIANCE_REGIME_VALUES


def test_sensitivity_implies_regime_covers_all_tags() -> None:
	# Every sensitivity tag has a mapping (even if empty).
	for tag in DATA_SENSITIVITY_VALUES:
		assert tag in SENSITIVITY_IMPLIES_REGIME


def test_phi_implies_hipaa() -> None:
	assert "HIPAA" in SENSITIVITY_IMPLIES_REGIME["PHI"]


def test_pii_implies_gdpr_and_ccpa() -> None:
	assert {"GDPR", "CCPA"} <= SENSITIVITY_IMPLIES_REGIME["PII"]


def test_pci_implies_pci_dss() -> None:
	assert "PCI-DSS" in SENSITIVITY_IMPLIES_REGIME["PCI"]


# ---------------------------------------------------------------------------
# implied_regimes helper
# ---------------------------------------------------------------------------


def test_implied_regimes_phi() -> None:
	result = implied_regimes(["PHI"])
	assert "HIPAA" in result


def test_implied_regimes_multiple_tags() -> None:
	result = implied_regimes(["PHI", "PII"])
	assert "HIPAA" in result
	assert "GDPR" in result
	assert "CCPA" in result


def test_implied_regimes_empty_input() -> None:
	assert implied_regimes([]) == frozenset()


def test_implied_regimes_unknown_tag_ignored() -> None:
	result = implied_regimes(["UNKNOWN_TAG"])
	assert result == frozenset()


# ---------------------------------------------------------------------------
# missing_regimes helper
# ---------------------------------------------------------------------------


def test_missing_regimes_none_missing() -> None:
	assert missing_regimes(["PHI"], ["HIPAA"]) == frozenset()


def test_missing_regimes_detects_gap() -> None:
	gaps = missing_regimes(["PHI"], [])
	assert "HIPAA" in gaps


def test_missing_regimes_extra_declared_ok() -> None:
	# Declaring more than required is fine — no gap.
	assert missing_regimes(["PCI"], ["PCI-DSS", "SOC2"]) == frozenset()


# ---------------------------------------------------------------------------
# JtbdSpec model — compliance + data_sensitivity fields
# ---------------------------------------------------------------------------


def _minimal_spec(jtbd_id: str = "claim_intake", **extra: Any) -> dict[str, Any]:
	spec: dict[str, Any] = {
		"id": jtbd_id,
		"actor": {"role": "user"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["ok"],
	}
	spec.update(extra)
	return spec


def test_spec_default_empty_compliance() -> None:
	spec = JtbdSpec.model_validate(_minimal_spec())
	assert spec.compliance == []
	assert spec.data_sensitivity == []


def test_spec_accepts_valid_compliance_regimes() -> None:
	spec = JtbdSpec.model_validate(
		_minimal_spec(compliance=["GDPR", "HIPAA"])
	)
	assert "GDPR" in spec.compliance
	assert "HIPAA" in spec.compliance


def test_spec_rejects_unknown_compliance_regime() -> None:
	with pytest.raises(Exception):
		JtbdSpec.model_validate(_minimal_spec(compliance=["UNKNOWN"]))


def test_spec_accepts_valid_sensitivity_tags() -> None:
	spec = JtbdSpec.model_validate(
		_minimal_spec(data_sensitivity=["PHI", "PII"])
	)
	assert "PHI" in spec.data_sensitivity


def test_spec_rejects_unknown_sensitivity_tag() -> None:
	with pytest.raises(Exception):
		JtbdSpec.model_validate(_minimal_spec(data_sensitivity=["INTERNAL"]))


# ---------------------------------------------------------------------------
# JtbdField — sensitivity list
# ---------------------------------------------------------------------------


def test_field_default_empty_sensitivity() -> None:
	field = JtbdField.model_validate({"id": "name", "kind": "text", "pii": True})
	assert field.sensitivity == []


def test_field_accepts_sensitivity_tags() -> None:
	field = JtbdField.model_validate({
		"id": "ssn",
		"kind": "text",
		"pii": True,
		"sensitivity": ["PII", "regulated"],
	})
	assert "PII" in field.sensitivity
	assert "regulated" in field.sensitivity


def test_field_rejects_unknown_sensitivity() -> None:
	with pytest.raises(Exception):
		JtbdField.model_validate({
			"id": "ssn",
			"kind": "text",
			"pii": True,
			"sensitivity": ["CONFIDENTIAL"],
		})


# ---------------------------------------------------------------------------
# JSON schema validation (via parse.py)
# ---------------------------------------------------------------------------


def test_schema_accepts_compliance_and_sensitivity_in_bundle() -> None:
	"""The jtbd-1.0 JSON schema now allows compliance[] and data_sensitivity[]."""
	from flowforge_cli.jtbd.parse import parse_bundle  # noqa: PLC0415

	bundle = {
		"project": {"name": "test", "package": "test_pkg", "domain": "test"},
		"shared": {"roles": ["user"], "permissions": ["test.read"]},
		"jtbds": [{
			"id": "claim_intake",
			"actor": {"role": "user"},
			"situation": "s",
			"motivation": "m",
			"outcome": "o",
			"success_criteria": ["ok"],
			"compliance": ["HIPAA", "GDPR"],
			"data_sensitivity": ["PHI", "PII"],
		}],
	}
	result = parse_bundle(bundle)
	jtbd = result["jtbds"][0]
	assert "HIPAA" in jtbd["compliance"]
	assert "PHI" in jtbd["data_sensitivity"]
