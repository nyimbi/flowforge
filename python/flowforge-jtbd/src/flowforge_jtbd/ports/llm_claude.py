"""Anthropic Claude default :class:`LlmProvider` implementation.

The adapter imports the official ``anthropic`` SDK lazily so a host
that prefers OpenAI / Ollama does not pay the dependency cost. When
the SDK is missing, instantiating :class:`LlmProviderClaude` raises
``ImportError`` with a fix-up hint pointing at the optional extras.

Default model ids (overridable):

* generate / stream_chat — ``claude-sonnet-4-5-20250929``
* embed — Anthropic does not ship a first-party embedding API; this
  adapter raises ``NotImplementedError`` from :meth:`embed` so callers
  fall back to the configured ``EmbeddingProvider`` (E-15).
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from .llm import LlmProviderError


_DEFAULT_GENERATE_MODEL = "claude-sonnet-4-5-20250929"


class LlmProviderClaude:
	"""Anthropic Claude adapter.

	Uses the official ``anthropic`` SDK. ``max_tokens`` / ``temperature``
	are passed straight through; ``system`` populates the system prompt
	at the API level (not concatenated with the user prompt).

	Adapters MUST tolerate the SDK being absent at import time — that
	keeps the library installable in environments that opt out of
	Anthropic. Construction is therefore where we surface the missing
	dependency, not import time.
	"""

	def __init__(
		self,
		*,
		api_key: str | None = None,
		model: str = _DEFAULT_GENERATE_MODEL,
		client: Any | None = None,
	) -> None:
		assert model, "model must be a non-empty string"
		if client is None:
			try:
				from anthropic import AsyncAnthropic  # type: ignore[import-not-found]
			except ModuleNotFoundError as exc:
				raise ImportError(
					"LlmProviderClaude requires the 'anthropic' SDK. "
					"Install with `pip install anthropic` or use the "
					"flowforge-jtbd[claude] extra."
				) from exc
			client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
		self._client = client
		self._model = model

	async def generate(
		self,
		prompt: str,
		*,
		max_tokens: int = 4000,
		temperature: float = 0.2,
		system: str | None = None,
	) -> str:
		assert prompt, "prompt must be non-empty"
		assert max_tokens >= 1, "max_tokens must be ≥ 1"
		try:
			response = await self._client.messages.create(
				model=self._model,
				max_tokens=max_tokens,
				temperature=temperature,
				system=system or "",
				messages=[{"role": "user", "content": prompt}],
			)
		except Exception as exc:  # noqa: BLE001
			raise LlmProviderError(
				f"anthropic.messages.create failed: {exc}",
			) from exc
		return _join_text_blocks(response)

	async def embed(self, text: str) -> list[float]:
		raise NotImplementedError(
			"Claude does not ship a first-party embedding API. "
			"Configure an EmbeddingProvider (E-15) for vector use cases.",
		)

	async def stream_chat(
		self,
		messages: list[dict[str, str]],
		*,
		max_tokens: int = 4000,
	) -> AsyncIterator[str]:
		assert messages, "messages must contain at least one entry"
		try:
			stream_ctx = self._client.messages.stream(
				model=self._model,
				max_tokens=max_tokens,
				messages=messages,
			)
		except Exception as exc:  # noqa: BLE001
			raise LlmProviderError(
				f"anthropic.messages.stream failed to start: {exc}",
			) from exc
		# The SDK's stream context yields events; we relay text deltas.
		async with stream_ctx as stream:
			try:
				async for event in stream:
					delta = _extract_delta(event)
					if delta:
						yield delta
			except Exception as exc:  # noqa: BLE001
				raise LlmProviderError(
					f"anthropic stream interrupted: {exc}",
				) from exc


def _join_text_blocks(response: Any) -> str:
	"""Concatenate the text content blocks of a Messages response.

	The SDK returns ``response.content`` as a list of ``TextBlock`` /
	``ToolUseBlock`` etc. We only care about text for E-14 (NL→JTBD
	draft text); tool-use blocks would surface in a richer agent flow.
	"""
	pieces: list[str] = []
	content = getattr(response, "content", None) or []
	for block in content:
		text = getattr(block, "text", None)
		if isinstance(text, str):
			pieces.append(text)
		elif isinstance(block, dict) and isinstance(block.get("text"), str):
			pieces.append(block["text"])
	return "".join(pieces)


def _extract_delta(event: Any) -> str | None:
	"""Pull the text delta off one SDK stream event.

	The SDK's event vocabulary varies slightly across versions; this
	helper handles both the duck-typed object form (``event.delta.text``)
	and the dict form some mocks use (``event['delta']['text']``).
	"""
	delta = getattr(event, "delta", None)
	if delta is not None:
		text = getattr(delta, "text", None)
		if isinstance(text, str):
			return text
	if isinstance(event, dict):
		delta_dict = event.get("delta") or {}
		if isinstance(delta_dict, dict):
			text = delta_dict.get("text")
			if isinstance(text, str):
				return text
	return None


__all__ = ["LlmProviderClaude"]
