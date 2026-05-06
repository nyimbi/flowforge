"""QualityScorer linter integration — E-16.

Registers a :class:`LowQualityRule` that runs the deterministic
:class:`QualityScorer` heuristic on each JTBD spec and emits a
``low_quality_jtbd`` **warning** when the score falls below the threshold
(default 60 per jtbd-editor-arch.md §4.3).

The rule runs once per spec; bundle-level invocation (``spec=None``) is
a no-op.

Usage
-----
.. code-block:: python

    from flowforge_jtbd.lint import Linter, RuleRegistry
    from flowforge_jtbd.lint.quality import LowQualityRulePack

    registry = RuleRegistry([LowQualityRulePack()])
    report = Linter(registry=registry).lint(bundle)
"""

from __future__ import annotations

from typing import Any

from flowforge_jtbd.ai.quality import QualityScorer
from flowforge_jtbd.spec import JtbdBundle, JtbdLintSpec

from .registry import JtbdRule
from .results import Issue


class LowQualityRule:
	"""Warn when a JTBD spec's heuristic quality score is below threshold.

	The threshold defaults to 60.  Scores below that value are considered
	low quality per the rubric in ``jtbd-editor-arch.md`` §4.3.
	"""

	rule_id: str = "low_quality_jtbd"

	def __init__(self, *, threshold: int = 60) -> None:
		assert 0 <= threshold <= 100
		self._scorer = QualityScorer(low_quality_threshold=threshold)
		self._threshold = threshold

	def check(
		self,
		_bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		if spec is None:
			# Bundle-level call — no-op for this rule.
			return []

		raw = _spec_to_dict(spec)
		report = self._scorer.score_sync(raw)

		if not report.low_quality:
			return []

		dim_summary = "; ".join(
			f"{d.name}={d.score}/100" for d in report.dimensions
		)
		return [
			Issue(
				severity="warning",
				rule="low_quality_jtbd",
				message=(
					f"JTBD '{spec.jtbd_id}' quality score {report.score}/100 is"
					f" below threshold {self._threshold}. Dimensions: {dim_summary}."
				),
				fixhint=(
					"Improve situation/motivation/outcome clarity, add measurable"
					" success_criteria, and remove solution-coupled language."
				),
				doc_url="/docs/jtbd-editor#quality",
				context=spec.jtbd_id,
				related_jtbds=[spec.jtbd_id],
				extra={"score": report.score, "threshold": self._threshold},
			)
		]


class LowQualityRulePack:
	"""A :class:`JtbdRulePack` that ships the low-quality warning rule.

	.. code-block:: python

		from flowforge_jtbd.lint.quality import LowQualityRulePack

		pack = LowQualityRulePack(threshold=70)
	"""

	pack_id: str = "quality"

	def __init__(self, *, threshold: int = 60) -> None:
		self._rule = LowQualityRule(threshold=threshold)

	def rules(self) -> list[JtbdRule]:
		return [self._rule]  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _spec_to_dict(spec: JtbdLintSpec) -> dict[str, Any]:
	"""Convert a :class:`JtbdLintSpec` to a plain dict for the scorer.

	The scorer needs the natural-language fields (situation, motivation,
	outcome, success_criteria) which live in ``model_extra`` since
	``JtbdLintSpec`` uses ``extra='allow'``.
	"""
	extra: dict[str, Any] = spec.model_extra or {}
	return {
		"id": spec.jtbd_id,
		"jtbd_id": spec.jtbd_id,
		"situation": extra.get("situation", ""),
		"motivation": extra.get("motivation", ""),
		"outcome": extra.get("outcome", ""),
		"success_criteria": extra.get("success_criteria", []),
	}


__all__ = ["LowQualityRule", "LowQualityRulePack"]
