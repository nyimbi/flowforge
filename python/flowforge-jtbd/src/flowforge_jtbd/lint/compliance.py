"""ComplianceLinter — sensitivity→regime and regime→required-job rules (E-23).

Two lint rules:

sensitivity_implies_regime
    Per-spec rule. If a JTBD spec declares a data_sensitivity tag
    (e.g. ``PHI``), the spec (or its bundle project) MUST declare the
    implied compliance regime (e.g. ``HIPAA``). Severity: ``error``.

compliance_missing_required_job
    Bundle-level rule (``spec=None``). If the bundle project declares
    a compliance regime (e.g. ``GDPR``), the bundle MUST contain a
    JTBD whose id matches each required job id for that regime.
    Severity: ``warning`` — bundles may be built incrementally.

Both rules fire ``0`` issues when their prerequisite data is absent
(``data_sensitivity=[]``, ``compliance=[]``, no catalog entry) so the
linter degrades gracefully before the compliance catalog is populated.

Usage::

    from flowforge_jtbd.lint.compliance import ComplianceLinterPack
    from flowforge_jtbd.lint import Linter, RuleRegistry

    linter = Linter(registry=RuleRegistry([ComplianceLinterPack()]))
    report = linter.lint(bundle)
"""

from __future__ import annotations

from ..compliance.catalog import missing_jobs
from ..compliance.schema import missing_regimes
from ..spec import JtbdBundle, JtbdLintSpec
from .registry import JtbdRule
from .results import Issue


# ---------------------------------------------------------------------------
# Rule: sensitivity_implies_regime
# ---------------------------------------------------------------------------


class SensitivityImpliesRegimeRule:
	"""Flag specs that declare sensitivity tags without the implied regimes."""

	rule_id = "compliance.sensitivity_implies_regime"

	def check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		if spec is None:
			return []  # bundle-level pass handled by ComplianceMissingJobRule

		sensitivity = list(getattr(spec, "data_sensitivity", None) or [])
		compliance = list(getattr(spec, "compliance", None) or [])
		if not sensitivity:
			return []

		gaps = missing_regimes(sensitivity, compliance)
		if not gaps:
			return []

		return [
			Issue(
				severity="error",
				rule=self.rule_id,
				message=(
					f"JTBD '{spec.jtbd_id}' declares data_sensitivity "
					f"{sorted(sensitivity)} but is missing required compliance "
					f"regime(s): {sorted(gaps)}"
				),
				fixhint=(
					f"Add the missing regime(s) to this JTBD's compliance[]: "
					f"{sorted(gaps)}"
				),
				related_jtbds=[spec.jtbd_id],
			)
		]


# ---------------------------------------------------------------------------
# Rule: compliance_missing_required_job
# ---------------------------------------------------------------------------


class ComplianceMissingJobRule:
	"""Warn when a compliance regime's required JTBD jobs are absent from bundle."""

	rule_id = "compliance.missing_required_job"

	def check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		if spec is not None:
			return []  # per-spec pass handled by SensitivityImpliesRegimeRule

		# Collect compliance regimes declared anywhere in the bundle.
		regime_sources: dict[str, list[str]] = {}  # regime → source jtbd_ids
		for s in bundle.jtbds:
			for regime in (getattr(s, "compliance", None) or []):
				regime_sources.setdefault(regime, []).append(s.jtbd_id)

		if not regime_sources:
			return []

		bundle_ids = {s.jtbd_id for s in bundle.jtbds}
		declared_regimes = list(regime_sources.keys())
		gaps = missing_jobs(declared_regimes, bundle_ids)

		issues: list[Issue] = []
		for regime, missing in gaps.items():
			sources = regime_sources.get(regime, [])
			issues.append(
				Issue(
					severity="warning",
					rule=self.rule_id,
					message=(
						f"Compliance regime '{regime}' (declared by "
						f"{sources}) requires JTBD job(s) not present in "
						f"bundle: {sorted(missing)}"
					),
					fixhint=(
						f"Add JTBD specs with these ids to cover '{regime}': "
						f"{sorted(missing)}"
					),
					related_jtbds=sources,
				)
			)
		return issues


# ---------------------------------------------------------------------------
# Rule pack
# ---------------------------------------------------------------------------


class ComplianceLinterPack:
	"""JtbdRulePack bundling the two compliance lint rules."""

	pack_id = "compliance"

	def rules(self) -> list[JtbdRule]:
		return [
			SensitivityImpliesRegimeRule(),  # type: ignore[return-value]
			ComplianceMissingJobRule(),       # type: ignore[return-value]
		]


__all__ = [
	"ComplianceLinterPack",
	"ComplianceMissingJobRule",
	"SensitivityImpliesRegimeRule",
]
