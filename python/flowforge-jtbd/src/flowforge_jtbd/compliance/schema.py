"""Compliance schema catalog for E-22.

Canonical sets and mappings for:

- :data:`DATA_SENSITIVITY_VALUES` — the five sensitivity tags.
- :data:`COMPLIANCE_REGIME_VALUES` — the eight compliance regime names.
- :data:`SENSITIVITY_IMPLIES_REGIME` — which sensitivity tags require
  specific compliance regimes (drives E-23's linter rule).

These constants mirror the JSON-schema enums added in E-22 and the
Literal types in :mod:`flowforge_jtbd.dsl.spec`.

Usage (in the E-23 linter)::

    from flowforge_jtbd.compliance.schema import SENSITIVITY_IMPLIES_REGIME

    for sensitivity_tag in jtbd.data_sensitivity:
        required_regimes = SENSITIVITY_IMPLIES_REGIME.get(sensitivity_tag, frozenset())
        for regime in required_regimes:
            if regime not in jtbd.compliance:
                yield Issue(severity='error', rule='compliance_missing', ...)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Data sensitivity values
# ---------------------------------------------------------------------------

#: Canonical set of data sensitivity tags.
DATA_SENSITIVITY_VALUES: frozenset[str] = frozenset(
	{"PII", "PHI", "PCI", "secrets", "regulated"}
)

#: Ordered tuple for deterministic iteration / display.
DATA_SENSITIVITY_ORDERED: tuple[str, ...] = (
	"PII",
	"PHI",
	"PCI",
	"secrets",
	"regulated",
)

# ---------------------------------------------------------------------------
# Compliance regime values
# ---------------------------------------------------------------------------

#: Canonical set of supported compliance regime names.
COMPLIANCE_REGIME_VALUES: frozenset[str] = frozenset(
	{"GDPR", "SOX", "HIPAA", "PCI-DSS", "ISO27001", "SOC2", "NIST-800-53", "CCPA"}
)

#: Ordered tuple for deterministic iteration / display.
COMPLIANCE_REGIME_ORDERED: tuple[str, ...] = (
	"GDPR",
	"SOX",
	"HIPAA",
	"PCI-DSS",
	"ISO27001",
	"SOC2",
	"NIST-800-53",
	"CCPA",
)

# ---------------------------------------------------------------------------
# Sensitivity → implied compliance regimes
# ---------------------------------------------------------------------------

#: Which compliance regimes a sensitivity tag implies.
#:
#: A JTBD spec declaring a sensitivity tag SHOULD declare all of the
#: corresponding regimes in ``compliance[]``. The E-23 linter enforces this
#: as an error (or warning in warn-only mode).
#:
#: Mappings reflect common regulatory overlaps:
#:
#: - ``PHI`` (Protected Health Information) → HIPAA mandatory.
#: - ``PII`` (Personal Identifiable Information) → GDPR + CCPA.
#: - ``PCI`` (Payment Card data) → PCI-DSS mandatory.
#: - ``secrets`` (credentials / keys) → SOC2 + ISO27001 (security controls).
#: - ``regulated`` (domain-specific regulated data) → NIST-800-53 (federal).
SENSITIVITY_IMPLIES_REGIME: dict[str, frozenset[str]] = {
	"PHI": frozenset({"HIPAA"}),
	"PII": frozenset({"GDPR", "CCPA"}),
	"PCI": frozenset({"PCI-DSS"}),
	"secrets": frozenset({"SOC2", "ISO27001"}),
	"regulated": frozenset({"NIST-800-53"}),
}


def implied_regimes(sensitivity_tags: list[str]) -> frozenset[str]:
	"""Return the union of all compliance regimes implied by *sensitivity_tags*.

	:param sensitivity_tags: List of sensitivity tag strings (may contain
	  unknowns; those are ignored).
	:returns: Frozenset of compliance regime names that must be declared.
	"""
	result: set[str] = set()
	for tag in sensitivity_tags:
		result |= SENSITIVITY_IMPLIES_REGIME.get(tag, frozenset())
	return frozenset(result)


def missing_regimes(
	sensitivity_tags: list[str],
	declared_compliance: list[str],
) -> frozenset[str]:
	"""Return compliance regimes implied by *sensitivity_tags* but absent
	from *declared_compliance*.

	A non-empty return value means the spec needs more compliance entries.
	"""
	implied = implied_regimes(sensitivity_tags)
	declared = frozenset(declared_compliance)
	return implied - declared


__all__ = [
	"COMPLIANCE_REGIME_ORDERED",
	"COMPLIANCE_REGIME_VALUES",
	"DATA_SENSITIVITY_ORDERED",
	"DATA_SENSITIVITY_VALUES",
	"SENSITIVITY_IMPLIES_REGIME",
	"implied_regimes",
	"missing_regimes",
]
