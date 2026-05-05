"""Tests for MultiChannelNotifier (router.py).

Uses FakeInAppAdapter as the real adapter and stub adapters for
channels that need HTTP — no network calls, no credentials.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from flowforge.ports.types import NotificationSpec
from flowforge_notify_multichannel.router import MultiChannelNotifier, RecipientPreferences
from flowforge_notify_multichannel.transports import (
	DeliveryResult,
	FakeInAppAdapter,
)


# ---------------------------------------------------------------------------
# Stub adapters
# ---------------------------------------------------------------------------


class StubAdapter:
	"""Captures deliver calls; returns configurable result."""

	def __init__(self, channel: str, ok: bool = True) -> None:
		self.channel = channel
		self._ok = ok
		self.calls: list[dict[str, Any]] = []

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		self.calls.append({"recipient": recipient, "subject": subject, "body": body, "metadata": metadata})
		return DeliveryResult(ok=self._ok)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def spec_en() -> NotificationSpec:
	return NotificationSpec(
		template_id="welcome",
		channels=("email", "in_app"),
		subject_template="Welcome, {{ name }}!",
		body_template="Hello {{ name }}, your code is {{ code }}.",
		locale="en",
	)


@pytest.fixture()
def spec_fr() -> NotificationSpec:
	return NotificationSpec(
		template_id="welcome",
		channels=("email",),
		subject_template="Bienvenue, {{ name }} !",
		body_template="Bonjour {{ name }}, votre code est {{ code }}.",
		locale="fr",
	)


@pytest.fixture()
def notifier() -> MultiChannelNotifier:
	in_app = FakeInAppAdapter()
	email_stub = StubAdapter("email")
	sms_stub = StubAdapter("sms")
	return MultiChannelNotifier(adapters=[in_app, email_stub, sms_stub])


# ---------------------------------------------------------------------------
# register_template + render
# ---------------------------------------------------------------------------


class TestRegisterAndRender:
	async def test_register_and_render_en(self, spec_en: NotificationSpec) -> None:
		n = MultiChannelNotifier()
		await n.register_template(spec_en)
		subject, body = await n.render("welcome", "en", {"name": "Alice", "code": "1234"})
		assert subject == "Welcome, Alice!"
		assert "Alice" in body
		assert "1234" in body

	async def test_register_idempotent(self, spec_en: NotificationSpec) -> None:
		n = MultiChannelNotifier()
		await n.register_template(spec_en)
		await n.register_template(spec_en)  # second registration should not raise
		subject, _ = await n.render("welcome", "en", {"name": "Bob", "code": "0"})
		assert "Bob" in subject

	async def test_locale_fallback_to_en(self, spec_en: NotificationSpec) -> None:
		n = MultiChannelNotifier()
		await n.register_template(spec_en)
		# Request "de" — not registered; should fall back to "en"
		subject, _ = await n.render("welcome", "de", {"name": "Hans", "code": "99"})
		assert "Hans" in subject

	async def test_explicit_locale_fr(self, spec_en: NotificationSpec, spec_fr: NotificationSpec) -> None:
		n = MultiChannelNotifier()
		await n.register_template(spec_en)
		await n.register_template(spec_fr)
		subject, body = await n.render("welcome", "fr", {"name": "Pierre", "code": "42"})
		assert "Bienvenue" in subject
		assert "Bonjour" in body

	async def test_render_unknown_template_raises(self) -> None:
		n = MultiChannelNotifier()
		with pytest.raises(KeyError, match="not registered"):
			await n.render("nonexistent", "en", {})

	async def test_render_jinja_escaping(self, spec_en: NotificationSpec) -> None:
		# Jinja2 sandbox should render {{ name }} safely even with unusual values
		n = MultiChannelNotifier()
		await n.register_template(spec_en)
		subject, _ = await n.render("welcome", "en", {"name": "<script>alert(1)</script>", "code": "x"})
		# No crash — sandboxed env should handle this
		assert "<script>" in subject  # autoescape=False, but no crash

	async def test_render_timezone_in_ctx(self, spec_en: NotificationSpec) -> None:
		n = MultiChannelNotifier()
		await n.register_template(spec_en)
		# _timezone key is consumed internally; should not break rendering
		_, body = await n.render("welcome", "en", {"name": "TZ", "code": "1", "_timezone": "America/New_York"})
		assert "TZ" in body


# ---------------------------------------------------------------------------
# send — channel dispatch
# ---------------------------------------------------------------------------


class TestSend:
	async def test_send_routes_to_correct_adapter(self, notifier: MultiChannelNotifier, spec_en: NotificationSpec) -> None:
		await notifier.register_template(spec_en)
		rendered = await notifier.render("welcome", "en", {"name": "Alice", "code": "0"})
		sent = await notifier.send("in_app", "alice", rendered)
		assert sent is True

		# Verify in_app received the delivery
		in_app: FakeInAppAdapter = notifier._adapters["in_app"]  # type: ignore[assignment]
		assert len(in_app.inbox_for("alice")) == 1

	async def test_send_unknown_channel_raises(self, notifier: MultiChannelNotifier, spec_en: NotificationSpec) -> None:
		await notifier.register_template(spec_en)
		rendered = await notifier.render("welcome", "en", {"name": "A", "code": "0"})
		with pytest.raises(ValueError, match="No adapter registered"):
			await notifier.send("fax", "alice", rendered)

	async def test_send_all_six_channels(self, spec_en: NotificationSpec) -> None:
		adapters = [
			StubAdapter("in_app"),
			StubAdapter("email"),
			StubAdapter("sms"),
			StubAdapter("push"),
			StubAdapter("webhook"),
			StubAdapter("slack"),
		]
		n = MultiChannelNotifier(adapters=adapters)
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "X", "code": "0"})

		for ch in ("in_app", "email", "sms", "push", "webhook", "slack"):
			result = await n.send(ch, "user@test.com", rendered)
			assert result is True

		for adapter in adapters:
			assert len(adapter.calls) == 1  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
	async def test_dedupe_skips_second_send(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub])
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "A", "code": "0"})

		sent1 = await n.send("email", "a@b.com", rendered, dedupe_key="key-abc")
		sent2 = await n.send("email", "a@b.com", rendered, dedupe_key="key-abc")

		assert sent1 is True
		assert sent2 is False
		assert len(stub.calls) == 1

	async def test_dedupe_different_recipients(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub])
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "A", "code": "0"})

		sent1 = await n.send("email", "alice@b.com", rendered, dedupe_key="key-abc")
		sent2 = await n.send("email", "bob@b.com", rendered, dedupe_key="key-abc")

		assert sent1 is True
		assert sent2 is True  # different recipient — not a dupe

	async def test_clear_dedupe(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub])
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "A", "code": "0"})

		await n.send("email", "a@b.com", rendered, dedupe_key="k")
		n.clear_dedupe()
		sent2 = await n.send("email", "a@b.com", rendered, dedupe_key="k")
		assert sent2 is True
		assert len(stub.calls) == 2


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------


class TestThrottling:
	async def test_throttle_blocks_rapid_resend(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub], throttle_seconds=60)
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "A", "code": "0"})

		sent1 = await n.send("email", "a@b.com", rendered, template_id="welcome")
		sent2 = await n.send("email", "a@b.com", rendered, template_id="welcome")

		assert sent1 is True
		assert sent2 is False
		assert len(stub.calls) == 1

	async def test_throttle_allows_after_clear(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub], throttle_seconds=60)
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "A", "code": "0"})

		await n.send("email", "a@b.com", rendered, template_id="welcome")
		n.clear_throttle()
		sent2 = await n.send("email", "a@b.com", rendered, template_id="welcome")
		assert sent2 is True
		assert len(stub.calls) == 2

	async def test_throttle_zero_disables(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub], throttle_seconds=0)
		await n.register_template(spec_en)
		rendered = await n.render("welcome", "en", {"name": "A", "code": "0"})

		for _ in range(5):
			await n.send("email", "a@b.com", rendered, template_id="welcome")

		assert len(stub.calls) == 5

	async def test_throttle_different_templates(self, spec_en: NotificationSpec) -> None:
		spec2 = NotificationSpec(
			template_id="reset",
			channels=("email",),
			subject_template="Reset",
			body_template="Reset body",
			locale="en",
		)
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub], throttle_seconds=60)
		await n.register_template(spec_en)
		await n.register_template(spec2)
		ren1 = await n.render("welcome", "en", {"name": "A", "code": "0"})
		ren2 = await n.render("reset", "en", {"name": "A", "code": "0"})

		s1 = await n.send("email", "a@b.com", ren1, template_id="welcome")
		s2 = await n.send("email", "a@b.com", ren2, template_id="reset")

		assert s1 is True
		assert s2 is True  # different template_id — not throttled


# ---------------------------------------------------------------------------
# Fanout + recipient preferences
# ---------------------------------------------------------------------------


class TestFanout:
	async def test_fanout_to_all_adapters_when_no_prefs(self, spec_en: NotificationSpec) -> None:
		email_stub = StubAdapter("email")
		sms_stub = StubAdapter("sms")
		n = MultiChannelNotifier(adapters=[email_stub, sms_stub])
		await n.register_template(spec_en)

		results = await n.fanout("user@test.com", "welcome", "en", {"name": "X", "code": "1"})

		assert results.get("email") is True
		assert results.get("sms") is True
		assert len(email_stub.calls) == 1
		assert len(sms_stub.calls) == 1

	async def test_fanout_respects_channel_prefs(self, spec_en: NotificationSpec) -> None:
		email_stub = StubAdapter("email")
		sms_stub = StubAdapter("sms")
		n = MultiChannelNotifier(adapters=[email_stub, sms_stub])
		await n.register_template(spec_en)

		n.register_preferences("vip@test.com", RecipientPreferences(channels=["email"]))
		results = await n.fanout("vip@test.com", "welcome", "en", {"name": "VIP", "code": "9"})

		assert results.get("email") is True
		assert "sms" not in results
		assert len(email_stub.calls) == 1
		assert len(sms_stub.calls) == 0

	async def test_fanout_skips_unknown_channel(self, spec_en: NotificationSpec) -> None:
		email_stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[email_stub])
		await n.register_template(spec_en)

		n.register_preferences("u", RecipientPreferences(channels=["email", "fax"]))
		results = await n.fanout("u", "welcome", "en", {"name": "U", "code": "0"})
		assert "fax" not in results  # no adapter for fax

	async def test_fanout_with_timezone(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub])
		await n.register_template(spec_en)

		n.register_preferences("u", RecipientPreferences(channels=["email"], timezone="Asia/Tokyo"))
		results = await n.fanout("u", "welcome", "en", {"name": "Taro", "code": "7"})
		assert results.get("email") is True

	async def test_fanout_dedup_key(self, spec_en: NotificationSpec) -> None:
		stub = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[stub])
		await n.register_template(spec_en)

		r1 = await n.fanout("u@x.com", "welcome", "en", {"name": "A", "code": "0"}, dedupe_key="dk1")
		r2 = await n.fanout("u@x.com", "welcome", "en", {"name": "A", "code": "0"}, dedupe_key="dk1")

		assert r1.get("email") is True
		assert r2.get("email") is False  # deduped


# ---------------------------------------------------------------------------
# Adapter management helpers
# ---------------------------------------------------------------------------


class TestAdapterManagement:
	def test_register_adapter_overrides(self) -> None:
		s1 = StubAdapter("email")
		s2 = StubAdapter("email")
		n = MultiChannelNotifier(adapters=[s1])
		n.register_adapter(s2)
		assert n._adapters["email"] is s2

	def test_dedupe_fingerprint_stable(self) -> None:
		n = MultiChannelNotifier()
		fp1 = n.dedupe_fingerprint("tpl", {"a": "1", "b": "2"})
		fp2 = n.dedupe_fingerprint("tpl", {"b": "2", "a": "1"})
		assert fp1 == fp2  # sorted keys -> deterministic

	def test_dedupe_fingerprint_different_inputs(self) -> None:
		n = MultiChannelNotifier()
		fp1 = n.dedupe_fingerprint("tpl", {"a": "1"})
		fp2 = n.dedupe_fingerprint("tpl", {"a": "2"})
		assert fp1 != fp2
