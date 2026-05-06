"""AI-assisted authoring helpers for the JTBD IDE.

E-14 — NL→JTBD generator (paired with the ``LlmProvider`` port in
       :mod:`flowforge_jtbd.ports.llm`).
E-15 — EmbeddingStore + DomainInferer (separate ticket).
E-16 — QualityScorer: deterministic rubric + optional LLM pass.
"""

from __future__ import annotations

from .nl_to_jtbd import (
	GenerationResult,
	NlToJtbdError,
	NlToJtbdGenerator,
	PromptInjectionRejected,
)
from .quality import (
	DimensionScore,
	LlmProvider,
	QualityReport,
	QualityScorer,
	score_jtbd,
)

__all__ = [
	"DimensionScore",
	"GenerationResult",
	"LlmProvider",
	"NlToJtbdError",
	"NlToJtbdGenerator",
	"PromptInjectionRejected",
	"QualityReport",
	"QualityScorer",
	"score_jtbd",
]
