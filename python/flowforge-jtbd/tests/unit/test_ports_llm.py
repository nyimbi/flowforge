"""LlmProvider Protocol structural conformance + error type."""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from flowforge_jtbd.ports import LlmProvider, LlmProviderError


class _FakeLlm:
	"""Minimal duck-typed implementation."""

	async def generate(
		self,
		prompt: str,
		*,
		max_tokens: int = 4000,
		temperature: float = 0.2,
		system: str | None = None,
	) -> str:
		return "ok"

	async def embed(self, text: str) -> list[float]:
		return [0.0]

	async def stream_chat(
		self,
		messages: list[dict[str, str]],
		*,
		max_tokens: int = 4000,
	) -> AsyncIterator[str]:
		yield "a"
		yield "b"


def test_protocol_is_runtime_checkable() -> None:
	assert isinstance(_FakeLlm(), LlmProvider)


def test_missing_method_fails_protocol_check() -> None:
	class _Partial:
		async def generate(self, prompt: str, *, max_tokens: int = 4000,
						   temperature: float = 0.2, system: str | None = None) -> str:
			return ""
		# embed and stream_chat missing.

	assert not isinstance(_Partial(), LlmProvider)


def test_error_is_runtime_error() -> None:
	assert issubclass(LlmProviderError, RuntimeError)
	with pytest.raises(LlmProviderError):
		raise LlmProviderError("boom")


async def test_fake_llm_generate_async() -> None:
	fake = _FakeLlm()
	out = await fake.generate("hello")
	assert out == "ok"


async def test_fake_llm_stream_chat_yields() -> None:
	fake = _FakeLlm()
	chunks = [chunk async for chunk in fake.stream_chat([{"role": "user", "content": "hi"}])]
	assert chunks == ["a", "b"]
