"""AI-assisted authoring helpers for the JTBD IDE.

E-16 — QualityScorer: deterministic rubric + optional LLM pass.
E-14 — LlmProvider port + NL→JTBD generator (separate ticket).
E-15 — EmbeddingStore + DomainInferer (separate ticket).
"""

from __future__ import annotations

from .quality import (
	DimensionScore,
	LlmProvider,
	QualityReport,
	QualityScorer,
	score_jtbd,
)

__all__ = [
	"DimensionScore",
	"LlmProvider",
	"QualityReport",
	"QualityScorer",
	"score_jtbd",
]
