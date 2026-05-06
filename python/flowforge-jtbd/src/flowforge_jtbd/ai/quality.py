"""QualityScorer — deterministic rubric for JTBD spec quality (E-16).

Per ``framework/docs/jtbd-editor-arch.md`` §4.3 and
``framework/docs/flowforge-evolution.md`` §6.

Rubric dimensions (each 0-100, averaged with equal weight):

.. list-table::
   :header-rows: 1

   * - Dimension
     - Weight
     - What is measured
   * - Clarity
     - 25 %
     - Readability of ``situation``, ``motivation``, ``outcome`` (length,
       structure, absence of jargon).
   * - Actionability
     - 25 %
     - ``success_criteria`` present, measurable (numbers / time bounds /
       binary observable conditions), not merely aspirational.
   * - Absence of solution-coupling
     - 25 %
     - The spec describes the *job*, not the implementation.  Phrases like
       "click the X button", "use the Y system", "navigate to", "fill in"
       are penalised.
   * - Presence of measurable outcome
     - 25 %
     - The ``outcome`` field is observable (a record exists, a message was
       sent, a decision was recorded) rather than vague ("is good",
       "is handled properly").

Scoring
-------
The deterministic heuristic pass always runs.  If an :class:`LlmProvider`
is supplied, its rubric assessment is blended in (60 % heuristic / 40 %
LLM).  The final score is a 0-100 integer.

Scores below 60 raise a ``low_quality_jtbd`` warning in the linter when
:class:`LowQualityRule` is registered (see ``flowforge_jtbd.lint.quality``).

Usage
-----
.. code-block:: python

    from flowforge_jtbd.ai.quality import QualityScorer, score_jtbd

    # Heuristic-only (no LLM):
    report = score_jtbd({"id": "claim_intake", "situation": "...", ...})
    print(report.score)   # 0-100

    # With an LLM provider (E-14):
    scorer = QualityScorer(llm=my_llm_provider)
    report = await scorer.score_async(spec_dict)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# LlmProvider protocol stub (full impl lands in E-14)
# ---------------------------------------------------------------------------

@runtime_checkable
class LlmProvider(Protocol):
	"""Minimal protocol needed by the quality scorer.

	Full implementation (Claude default + OpenAI + local Ollama) ships in
	ticket E-14. This stub lets the scorer be developed and tested
	independently.
	"""

	async def generate(
		self, prompt: str, *, max_tokens: int = 4000, temperature: float = 0.2,
	) -> str:
		"""Return raw text from the LLM."""
		...


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DimensionScore:
	"""Score + explanation for one rubric dimension."""

	name: str
	"""Dimension identifier: ``clarity``, ``actionability``,
	``solution_decoupling``, ``measurable_outcome``."""

	score: int
	"""0-100 integer for this dimension."""

	findings: list[str] = field(default_factory=list)
	"""Human-readable notes explaining the score (positives and negatives)."""


@dataclass(frozen=True)
class QualityReport:
	"""Full quality assessment for one JTBD spec.

	``score`` is the weighted average of the four dimension scores
	(equal 25 % weight each).  The editor renders it as a badge on the
	JTBD card.  ``score < 60`` triggers a linter warning.
	"""

	jtbd_id: str
	score: int
	"""0-100 overall quality score."""

	dimensions: list[DimensionScore]
	"""Per-dimension breakdown."""

	low_quality: bool
	"""``True`` iff ``score < 60`` (threshold per jtbd-editor-arch.md §4.3)."""

	llm_blended: bool = False
	"""Whether an LLM pass was blended into the score."""


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

# Solution-coupled phrases that indicate the spec describes the UI/system
# rather than the job to be done.
_SOLUTION_COUPLED_RE = re.compile(
	r"\b("
	r"click(?:ing)?|button|dropdown|checkbox|text\s*field|input\s*field|"
	r"navigate\s*to|go\s*to\s*(?:the\s*)?(?:page|screen|tab)|"
	r"use\s+the\s+\w+\s+(?:system|tool|platform|module|app(?:lication)?)|"
	r"fill\s+(?:in|out)\s+the|select\s+from\s+the|"
	r"open\s+the\s+\w+\s+dialog|menu\s+item|sidebar|dashboard"
	r")\b",
	re.IGNORECASE,
)

# Observable outcome verbs — good signs in the outcome field.
_OBSERVABLE_RE = re.compile(
	r"\b("
	r"exists?|created?|sent|recorded|saved?|stored?|"
	r"approved?|rejected?|submitted?|completed?|triggered?|"
	r"dispatched?|logged?|audited?|notif(?:ied|ication)|"
	r"resolved?|closed?|cancelled?|escalated?"
	r")\b",
	re.IGNORECASE,
)

# Vague outcome language — deduct.
_VAGUE_OUTCOME_RE = re.compile(
	r"\b("
	r"good|better|nice|properly|correctly|well|handled|"
	r"effectively|efficiently|successfully\s+(?:done|handled)|"
	r"as\s+expected|in\s+a\s+timely\s+(?:fashion|manner)"
	r")\b",
	re.IGNORECASE,
)

# Measurable success-criteria signals.
_MEASURABLE_RE = re.compile(
	r"("
	r"\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|%|percent)|"
	r"within\s+\d+|at\s+least\s+\d+|no\s+more\s+than\s+\d+|"
	r"less\s+than\s+\d+|greater\s+than\s+\d+|"
	r"\bSLA\b|\bSLO\b|measur|quantif|count|rate|ratio|threshold"
	r")",
	re.IGNORECASE,
)

_WORD_RE = re.compile(r"\b\w+\b")


def _word_count(text: str) -> int:
	return len(_WORD_RE.findall(text))


def _count_matches(pattern: re.Pattern[str], texts: list[str]) -> int:
	return sum(len(pattern.findall(t)) for t in texts)


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_clarity(situation: str, motivation: str, outcome: str) -> DimensionScore:
	"""Clarity: readability of the three core narrative fields."""
	findings: list[str] = []
	score = 100

	required = {"situation": situation, "motivation": motivation, "outcome": outcome}
	for name, text in required.items():
		if not text or not text.strip():
			findings.append(f"'{name}' is empty.")
			score -= 30
			continue
		wc = _word_count(text)
		if wc < 5:
			findings.append(f"'{name}' is very short ({wc} words).")
			score -= 15
		elif wc < 10:
			findings.append(f"'{name}' could be expanded ({wc} words).")
			score -= 5
		elif wc > 80:
			findings.append(f"'{name}' may be overly long ({wc} words); consider tightening.")
			score -= 5

	score = max(0, min(100, score))
	if score >= 80:
		findings.insert(0, "All three narrative fields are present and reasonably sized.")
	return DimensionScore(name="clarity", score=score, findings=findings)


def _score_actionability(success_criteria: list[str]) -> DimensionScore:
	"""Actionability: success_criteria are measurable and present."""
	findings: list[str] = []
	score = 0

	if not success_criteria:
		findings.append("No success_criteria defined — add at least one measurable criterion.")
		return DimensionScore(name="actionability", score=0, findings=findings)

	score = 50  # base for having criteria at all
	findings.append(f"{len(success_criteria)} success criteri{'on' if len(success_criteria) == 1 else 'a'} found.")

	measurable_count = _count_matches(_MEASURABLE_RE, success_criteria)
	if measurable_count > 0:
		score += min(40, measurable_count * 15)
		findings.append(f"{measurable_count} criteri{'on' if measurable_count == 1 else 'a'} contain measurable language.")
	else:
		findings.append("Success criteria lack measurable language (numbers, time bounds, SLA thresholds).")
		score -= 10

	if len(success_criteria) >= 2:
		score += 10
		findings.append("Multiple criteria improve verifiability.")

	score = max(0, min(100, score))
	return DimensionScore(name="actionability", score=score, findings=findings)


def _score_solution_decoupling(all_text: list[str]) -> DimensionScore:
	"""Solution-coupling: the spec describes the job, not the implementation."""
	findings: list[str] = []

	coupled_count = _count_matches(_SOLUTION_COUPLED_RE, all_text)
	if coupled_count == 0:
		findings.append("No solution-coupled language detected.")
		score = 100
	elif coupled_count == 1:
		findings.append("1 solution-coupled phrase detected — consider rephrasing.")
		score = 70
	elif coupled_count == 2:
		findings.append(f"{coupled_count} solution-coupled phrases — spec may describe UI/system rather than the job.")
		score = 40
	else:
		findings.append(
			f"{coupled_count} solution-coupled phrases — spec is likely describing an implementation, not a job."
		)
		score = max(0, 20 - (coupled_count - 3) * 5)

	return DimensionScore(name="solution_decoupling", score=score, findings=findings)


def _score_measurable_outcome(outcome: str) -> DimensionScore:
	"""Measurable outcome: the outcome field is observable."""
	findings: list[str] = []

	if not outcome or not outcome.strip():
		findings.append("'outcome' is empty.")
		return DimensionScore(name="measurable_outcome", score=0, findings=findings)

	observable_count = len(_OBSERVABLE_RE.findall(outcome))
	vague_count = len(_VAGUE_OUTCOME_RE.findall(outcome))

	score = 50  # base
	if observable_count > 0:
		score += min(40, observable_count * 20)
		findings.append(f"Outcome uses {observable_count} observable term(s).")
	else:
		findings.append("Outcome lacks observable language (e.g., 'record exists', 'was sent').")
		score -= 20

	if vague_count > 0:
		score -= min(30, vague_count * 10)
		findings.append(f"Outcome contains {vague_count} vague term(s) (e.g., 'good', 'properly').")

	score = max(0, min(100, score))
	return DimensionScore(name="measurable_outcome", score=score, findings=findings)


# ---------------------------------------------------------------------------
# QualityScorer
# ---------------------------------------------------------------------------

class QualityScorer:
	"""Compute a 0-100 quality score for a JTBD spec.

	Parameters
	----------
	llm:
		Optional :class:`LlmProvider`.  When supplied, the LLM rubric
		assessment is blended with the heuristic at a 60/40 ratio.
		When ``None``, only the deterministic heuristic runs.
	low_quality_threshold:
		Score below which the spec is flagged as low quality.  Default 60.
	"""

	def __init__(
		self,
		llm: LlmProvider | None = None,
		*,
		low_quality_threshold: int = 60,
	) -> None:
		assert 0 <= low_quality_threshold <= 100, "threshold must be 0-100"
		self._llm = llm
		self._threshold = low_quality_threshold

	def score_sync(self, spec: dict[str, Any]) -> QualityReport:
		"""Heuristic-only score (synchronous).

		For the LLM-blended score, use :meth:`score_async`.
		"""
		return _heuristic_report(spec, self._threshold)

	async def score_async(self, spec: dict[str, Any]) -> QualityReport:
		"""Score with optional LLM blending (asynchronous).

		If no :class:`LlmProvider` was supplied at construction, this
		falls back to the heuristic-only pass.
		"""
		heuristic = _heuristic_report(spec, self._threshold)
		if self._llm is None:
			return heuristic

		# LLM rubric pass — prompt returns a JSON dict with per-dimension
		# 0-100 scores.  Any parse failure falls back to heuristic-only.
		try:
			llm_scores = await _llm_rubric_pass(self._llm, spec)
		except Exception:
			return heuristic

		# Blend: 60 % heuristic, 40 % LLM.
		blended_dims: list[DimensionScore] = []
		llm_map = {name: s for name, s in llm_scores.items()}
		for dim in heuristic.dimensions:
			llm_s = llm_map.get(dim.name, dim.score)
			blended = round(dim.score * 0.6 + llm_s * 0.4)
			blended_dims.append(
				DimensionScore(
					name=dim.name,
					score=blended,
					findings=dim.findings + [f"LLM assessment: {llm_s}/100."],
				)
			)

		blended_score = _average_score(blended_dims)
		return QualityReport(
			jtbd_id=heuristic.jtbd_id,
			score=blended_score,
			dimensions=blended_dims,
			low_quality=blended_score < self._threshold,
			llm_blended=True,
		)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def score_jtbd(spec: dict[str, Any], *, threshold: int = 60) -> QualityReport:
	"""Heuristic-only quality score for *spec*.

	Convenience wrapper for the common no-LLM case.  For LLM blending,
	instantiate :class:`QualityScorer` with an :class:`LlmProvider`.
	"""
	return _heuristic_report(spec, threshold)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_fields(spec: dict[str, Any]) -> tuple[str, str, str, list[str]]:
	"""Pull the four narrative fields out of a raw spec dict."""
	situation = str(spec.get("situation") or "")
	motivation = str(spec.get("motivation") or "")
	outcome = str(spec.get("outcome") or "")
	raw_criteria = spec.get("success_criteria") or []
	if isinstance(raw_criteria, str):
		criteria = [raw_criteria]
	elif isinstance(raw_criteria, list):
		criteria = [str(c) for c in raw_criteria if c]
	else:
		criteria = []
	return situation, motivation, outcome, criteria


def _average_score(dims: list[DimensionScore]) -> int:
	if not dims:
		return 0
	return round(sum(d.score for d in dims) / len(dims))


def _heuristic_report(spec: dict[str, Any], threshold: int) -> QualityReport:
	jtbd_id = str(spec.get("id") or spec.get("jtbd_id") or "unknown")
	situation, motivation, outcome, criteria = _extract_fields(spec)

	all_text = [situation, motivation, outcome] + criteria

	dims = [
		_score_clarity(situation, motivation, outcome),
		_score_actionability(criteria),
		_score_solution_decoupling(all_text),
		_score_measurable_outcome(outcome),
	]
	score = _average_score(dims)
	return QualityReport(
		jtbd_id=jtbd_id,
		score=score,
		dimensions=dims,
		low_quality=score < threshold,
	)


async def _llm_rubric_pass(
	llm: LlmProvider,
	spec: dict[str, Any],
) -> dict[str, int]:
	"""Ask the LLM to score each dimension; return a dict of name→score."""
	situation, motivation, outcome, criteria = _extract_fields(spec)
	criteria_text = "\n".join(f"  - {c}" for c in criteria) or "  (none)"

	prompt = f"""You are evaluating the quality of a JTBD (Jobs-To-Be-Done) specification.

JTBD spec:
  situation: {situation}
  motivation: {motivation}
  outcome: {outcome}
  success_criteria:
{criteria_text}

Score each dimension from 0-100 and respond with ONLY a JSON object like:
{{"clarity": 80, "actionability": 60, "solution_decoupling": 90, "measurable_outcome": 75}}

Rubric:
- clarity: readability and completeness of situation/motivation/outcome
- actionability: success_criteria are measurable, time-bound, falsifiable
- solution_decoupling: describes the job, not UI/system implementation
- measurable_outcome: outcome is observable, not vague
"""
	import json as _json

	raw = await llm.generate(prompt, max_tokens=200, temperature=0.1)
	# Extract JSON from response.
	match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
	if not match:
		return {}
	data = _json.loads(match.group())
	return {k: int(max(0, min(100, v))) for k, v in data.items() if isinstance(v, (int, float))}


__all__ = [
	"DimensionScore",
	"LlmProvider",
	"QualityReport",
	"QualityScorer",
	"score_jtbd",
]
