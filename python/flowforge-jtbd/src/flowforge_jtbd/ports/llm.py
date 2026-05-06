"""LlmProvider port.

Per ``framework/docs/jtbd-editor-arch.md`` §4.4. A pluggable contract
for every LLM call the JTBD IDE makes:

* :meth:`LlmProvider.generate` — single-shot text generation. Used by
  NL→JTBD (E-14) and the quality scorer (E-16).
* :meth:`LlmProvider.embed` — vector embedding for semantic search.
  Used by the recommender / domain inferer (E-15).
* :meth:`LlmProvider.stream_chat` — token-by-token streaming for
  interactive editor surfaces.

The Protocol is :func:`runtime_checkable` so unit tests can pass a
duck-typed fake and ``isinstance(fake, LlmProvider)`` returns ``True``.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


class LlmProviderError(RuntimeError):
	"""Raised by adapters when the underlying LLM call fails.

	Adapters wrap transport / auth / parse failures into this exception
	so callers can catch a single type regardless of backend (Anthropic,
	OpenAI, Ollama, …).
	"""


@runtime_checkable
class LlmProvider(Protocol):
	"""Pluggable contract for LLM-backed features.

	Every async method MUST be cancellation-safe (the editor cancels in
	flight on tab-switch) and MUST raise :class:`LlmProviderError` on
	any non-retryable failure.

	Adapters that lack a capability raise :class:`NotImplementedError`
	from the unsupported method — the caller is expected to feature-
	test before invocation rather than catch.
	"""

	async def generate(
		self,
		prompt: str,
		*,
		max_tokens: int = 4000,
		temperature: float = 0.2,
		system: str | None = None,
	) -> str:
		"""Return raw text from a single LLM call.

		Implementations are expected to enforce ``max_tokens`` and
		``temperature`` and to silently truncate the prompt when the
		backend's context window is smaller than ``len(prompt)``.
		"""
		...

	async def embed(self, text: str) -> list[float]:
		"""Return an embedding vector for *text*.

		Vector dimensions are adapter-specific. Callers persisting
		embeddings MUST also persist the adapter id so cosine similarity
		stays meaningful across reads.
		"""
		...

	def stream_chat(
		self,
		messages: list[dict[str, str]],
		*,
		max_tokens: int = 4000,
	) -> AsyncIterator[str]:
		"""Stream tokens for an interactive chat.

		Async generator function. ``messages`` follows the standard
		``[{role, content}, ...]`` shape. Implementations yield text
		deltas as they arrive and raise :class:`LlmProviderError` on
		transport failure mid-stream.

		Note: the Protocol declares this as ``def`` (not ``async def``)
		because calling an async-generator function returns an
		``AsyncIterator`` directly — there is no coroutine to await.
		"""
		...


__all__ = [
	"LlmProvider",
	"LlmProviderError",
]
