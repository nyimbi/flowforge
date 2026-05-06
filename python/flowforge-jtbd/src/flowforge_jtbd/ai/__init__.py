"""AI-assisted authoring helpers for the JTBD IDE.

E-7  — Recommender: embedding-based top-K JTBD similarity.
E-14 — NL→JTBD generator (paired with the ``LlmProvider`` port in
       :mod:`flowforge_jtbd.ports.llm`).
E-15 — DomainInferer: starter library JTBDs from an NL description.
E-16 — QualityScorer: deterministic rubric + optional LLM pass.
"""

from __future__ import annotations

from .domain_inference import (
	DomainHit,
	DomainInferenceResult,
	DomainInferer,
)
from .nl_to_jtbd import (
	GenerationResult,
	NlToJtbdError,
	NlToJtbdGenerator,
	PromptInjectionRejected,
)
from .pgvector_store import (
	GoldenQuery,
	HnswIndexSwapper,
	IndexSwapAborted,
	PgVectorEmbeddingStore,
	PgVectorUnavailable,
	SwapReport,
	TableSpec,
)
from .quality import (
	DimensionScore,
	LlmProvider,
	QualityReport,
	QualityScorer,
	score_jtbd,
)
from .recommender import (
	BagOfWordsEmbeddingProvider,
	EmbeddingProvider,
	EmbeddingStore,
	InMemoryEmbeddingStore,
	RecommendationResult,
	Recommender,
	build_recommender,
)

__all__ = [
	"BagOfWordsEmbeddingProvider",
	"DimensionScore",
	"DomainHit",
	"DomainInferenceResult",
	"DomainInferer",
	"EmbeddingProvider",
	"EmbeddingStore",
	"GenerationResult",
	"GoldenQuery",
	"HnswIndexSwapper",
	"IndexSwapAborted",
	"InMemoryEmbeddingStore",
	"LlmProvider",
	"NlToJtbdError",
	"NlToJtbdGenerator",
	"PgVectorEmbeddingStore",
	"PgVectorUnavailable",
	"PromptInjectionRejected",
	"QualityReport",
	"QualityScorer",
	"RecommendationResult",
	"Recommender",
	"SwapReport",
	"TableSpec",
	"build_recommender",
	"score_jtbd",
]
