"""LlmProviderClaude — adapter behaviour against a fake anthropic SDK.

Real Anthropic SDK calls are not exercised here. The tests inject a
fake ``client`` whose ``messages.create`` / ``messages.stream`` mirror
the real SDK shape closely enough to drive the adapter. The
``ImportError`` path (SDK absent) is also covered.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from flowforge_jtbd.ports import LlmProviderError
from flowforge_jtbd.ports.llm_claude import LlmProviderClaude


@dataclass
class _TextBlock:
	text: str


@dataclass
class _Response:
	content: list[Any]


class _FakeMessages:
	"""Stand-in for ``anthropic.AsyncAnthropic().messages``."""

	def __init__(self) -> None:
		self.last_call: dict[str, Any] = {}
		self.fail_create_with: Exception | None = None
		self.create_response: _Response = _Response(
			content=[_TextBlock(text="hello world")],
		)
		self.stream_chunks: list[Any] = [
			{"delta": {"text": "alpha "}},
			{"delta": {"text": "beta"}},
		]
		self.fail_stream_with: Exception | None = None
		self.fail_mid_stream_with: Exception | None = None

	async def create(self, **kwargs: Any) -> _Response:
		self.last_call = kwargs
		if self.fail_create_with is not None:
			raise self.fail_create_with
		return self.create_response

	def stream(self, **kwargs: Any):
		self.last_call = kwargs
		if self.fail_stream_with is not None:
			raise self.fail_stream_with

		fail_mid = self.fail_mid_stream_with
		chunks = list(self.stream_chunks)

		@asynccontextmanager
		async def _ctx():
			async def _iter():
				for chunk in chunks:
					yield chunk
				if fail_mid is not None:
					raise fail_mid

			yield _iter()

		return _ctx()


class _FakeClient:
	def __init__(self) -> None:
		self.messages = _FakeMessages()


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


async def test_generate_returns_concatenated_text() -> None:
	client = _FakeClient()
	provider = LlmProviderClaude(client=client)
	out = await provider.generate("draft a JTBD", max_tokens=200, temperature=0.0)
	assert out == "hello world"
	# adapter forwards parameters.
	assert client.messages.last_call["max_tokens"] == 200
	assert client.messages.last_call["temperature"] == 0.0


async def test_generate_concatenates_multiple_blocks() -> None:
	client = _FakeClient()
	client.messages.create_response = _Response(
		content=[_TextBlock(text="part1 "), _TextBlock(text="part2")],
	)
	provider = LlmProviderClaude(client=client)
	assert await provider.generate("x") == "part1 part2"


async def test_generate_handles_dict_text_blocks() -> None:
	client = _FakeClient()
	client.messages.create_response = _Response(
		content=[{"text": "from dict"}],
	)
	provider = LlmProviderClaude(client=client)
	assert await provider.generate("x") == "from dict"


async def test_generate_passes_system_prompt() -> None:
	client = _FakeClient()
	provider = LlmProviderClaude(client=client)
	await provider.generate("user prompt", system="be brief")
	assert client.messages.last_call["system"] == "be brief"


async def test_generate_wraps_sdk_failure_in_provider_error() -> None:
	client = _FakeClient()
	client.messages.fail_create_with = RuntimeError("rate-limited")
	provider = LlmProviderClaude(client=client)
	with pytest.raises(LlmProviderError) as info:
		await provider.generate("x")
	assert "rate-limited" in str(info.value)


# ---------------------------------------------------------------------------
# embed (unsupported)
# ---------------------------------------------------------------------------


async def test_embed_raises_not_implemented() -> None:
	provider = LlmProviderClaude(client=_FakeClient())
	with pytest.raises(NotImplementedError):
		await provider.embed("text")


# ---------------------------------------------------------------------------
# stream_chat
# ---------------------------------------------------------------------------


async def test_stream_chat_yields_each_delta() -> None:
	client = _FakeClient()
	provider = LlmProviderClaude(client=client)
	chunks: list[str] = []
	async for token in provider.stream_chat([{"role": "user", "content": "hi"}]):
		chunks.append(token)
	assert chunks == ["alpha ", "beta"]


async def test_stream_chat_wraps_start_failure() -> None:
	client = _FakeClient()
	client.messages.fail_stream_with = RuntimeError("auth failed")
	provider = LlmProviderClaude(client=client)
	with pytest.raises(LlmProviderError):
		async for _ in provider.stream_chat([{"role": "user", "content": "hi"}]):
			pass


async def test_stream_chat_wraps_mid_stream_failure() -> None:
	client = _FakeClient()
	client.messages.fail_mid_stream_with = RuntimeError("disconnect")
	provider = LlmProviderClaude(client=client)
	collected: list[str] = []
	with pytest.raises(LlmProviderError):
		async for token in provider.stream_chat([{"role": "user", "content": "hi"}]):
			collected.append(token)
	# Caller still sees the partial chunks emitted before the failure.
	assert collected == ["alpha ", "beta"]


# ---------------------------------------------------------------------------
# SDK absent
# ---------------------------------------------------------------------------


def test_constructor_without_sdk_raises_import_error(monkeypatch) -> None:
	"""When the anthropic SDK is not installed, construction without a client
	raises ImportError with a remediation hint."""
	# Block the import even if it's installed.
	monkeypatch.setitem(sys.modules, "anthropic", None)
	with pytest.raises(ImportError) as info:
		LlmProviderClaude()
	assert "anthropic" in str(info.value)
