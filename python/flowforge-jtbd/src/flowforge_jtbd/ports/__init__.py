"""Ports — pluggable contracts for AI / external integrations.

Per ``framework/docs/jtbd-editor-arch.md`` §4.4. The ``LlmProvider``
Protocol covers every LLM call the JTBD IDE makes (NL→JTBD draft
generation, quality scoring, conflict prose). E-14 ships the canonical
Protocol + the Claude default; E-15 layers in ``EmbeddingProvider`` /
``EmbeddingStore``.
"""

from __future__ import annotations

from .llm import LlmProvider, LlmProviderError

__all__ = [
	"LlmProvider",
	"LlmProviderError",
]
