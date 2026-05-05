"""Tests for channel adapters in flowforge_notify_multichannel.transports.

All external HTTP calls are faked via a simple async stub — no real
network, no credentials required.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from flowforge_notify_multichannel.transports import (
	DeliveryResult,
	EmailAdapter,
	FCMPushAdapter,
	FakeInAppAdapter,
	SESEmailAdapter,
	SlackAdapter,
	SMSAdapter,
	WebhookAdapter,
)


# ---------------------------------------------------------------------------
# Minimal fake httpx response
# ---------------------------------------------------------------------------


@dataclass
class FakeResponse:
	status_code: int
	_text: str = "ok"
	_json: Any = None

	@property
	def text(self) -> str:
		return self._text

	@property
	def content(self) -> bytes:
		return self._text.encode()

	def json(self) -> Any:
		return self._json if self._json is not None else {}


class FakeHTTPClient:
	"""Minimal async httpx client stub."""

	def __init__(self, response: FakeResponse) -> None:
		self._response = response
		self.calls: list[dict[str, Any]] = []

	async def post(self, url: str, **kwargs: Any) -> FakeResponse:
		self.calls.append({"url": url, **kwargs})
		return self._response


# ---------------------------------------------------------------------------
# FakeInAppAdapter
# ---------------------------------------------------------------------------


class TestFakeInAppAdapter:
	async def test_deliver_stores_record(self) -> None:
		adapter = FakeInAppAdapter()
		result = await adapter.deliver("user@x.com", "Hello", "World", {})
		assert result.ok
		assert result.provider_id == "inapp-1"

	async def test_inbox_for_recipient(self) -> None:
		adapter = FakeInAppAdapter()
		await adapter.deliver("alice", "Hi", "Body", {"k": "v"})
		await adapter.deliver("bob", "Hey", "Boo", {})
		inbox = adapter.inbox_for("alice")
		assert len(inbox) == 1
		assert inbox[0].subject == "Hi"

	async def test_mark_read(self) -> None:
		adapter = FakeInAppAdapter()
		await adapter.deliver("alice", "Hi", "B", {})
		await adapter.deliver("alice", "Hi2", "B2", {})
		count = adapter.mark_read("alice")
		assert count == 2
		assert all(r.read for r in adapter.inbox_for("alice"))

	async def test_mark_read_idempotent(self) -> None:
		adapter = FakeInAppAdapter()
		await adapter.deliver("alice", "Hi", "B", {})
		adapter.mark_read("alice")
		count2 = adapter.mark_read("alice")
		assert count2 == 0

	def test_channel_name(self) -> None:
		assert FakeInAppAdapter.channel == "in_app"


# ---------------------------------------------------------------------------
# EmailAdapter (SMTP stub — we stub aiosmtplib.send)
# ---------------------------------------------------------------------------


class TestEmailAdapter:
	async def test_deliver_calls_smtp(self, monkeypatch: pytest.MonkeyPatch) -> None:
		sent: list[Any] = []

		async def fake_send(msg: Any, **kwargs: Any) -> None:
			sent.append((msg, kwargs))

		monkeypatch.setattr("aiosmtplib.send", fake_send)

		adapter = EmailAdapter(
			host="localhost",
			port=1025,
			user="",
			password="",
			from_addr="from@test.com",
			start_tls=False,
		)
		result = await adapter.deliver("to@test.com", "Subject", "Body text", {})
		assert result.ok
		assert len(sent) == 1

	async def test_deliver_returns_error_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
		async def fail_send(*a: Any, **kw: Any) -> None:
			raise ConnectionRefusedError("no smtp")

		monkeypatch.setattr("aiosmtplib.send", fail_send)

		adapter = EmailAdapter(host="localhost", port=9999, start_tls=False)
		result = await adapter.deliver("to@test.com", "S", "B", {})
		assert not result.ok
		assert "no smtp" in (result.error or "")

	def test_channel_name(self) -> None:
		assert EmailAdapter.channel == "email"


# ---------------------------------------------------------------------------
# SESEmailAdapter
# ---------------------------------------------------------------------------


class TestSESEmailAdapter:
	async def test_deliver_success(self) -> None:
		fake = FakeHTTPClient(FakeResponse(200, _json={"MessageId": "ses-123"}))
		adapter = SESEmailAdapter(
			access_key="AKID",
			secret_key="SECRET",
			region="us-east-1",
			from_addr="from@ses.test",
			_http_client=fake,
		)
		result = await adapter.deliver("to@ses.test", "Hello SES", "Body", {})
		assert result.ok
		assert result.provider_id == "ses-123"
		assert len(fake.calls) == 1

	async def test_deliver_http_error(self) -> None:
		fake = FakeHTTPClient(FakeResponse(500, "Internal Error"))
		adapter = SESEmailAdapter(_http_client=fake)
		result = await adapter.deliver("to@ses.test", "S", "B", {})
		assert not result.ok
		assert "500" in (result.error or "")

	def test_channel_name(self) -> None:
		assert SESEmailAdapter.channel == "email"


# ---------------------------------------------------------------------------
# SMSAdapter (Twilio)
# ---------------------------------------------------------------------------


class TestSMSAdapter:
	async def test_deliver_success(self) -> None:
		fake = FakeHTTPClient(FakeResponse(201, _json={"sid": "SM123"}))
		adapter = SMSAdapter(
			account_sid="AC123",
			auth_token="tok",
			from_number="+15005550006",
			_http_client=fake,
		)
		result = await adapter.deliver("+15551234567", "Alert", "Your code is 1234", {})
		assert result.ok
		assert result.provider_id == "SM123"

	async def test_deliver_missing_credentials(self) -> None:
		adapter = SMSAdapter(account_sid="", auth_token="", from_number="")
		result = await adapter.deliver("+1555", "S", "B", {})
		assert not result.ok
		assert "TWILIO_ACCOUNT_SID" in (result.error or "")

	async def test_deliver_http_error(self) -> None:
		fake = FakeHTTPClient(FakeResponse(400, "Bad request"))
		adapter = SMSAdapter(account_sid="AC1", auth_token="t", from_number="+1", _http_client=fake)
		result = await adapter.deliver("+15551234567", "S", "B", {})
		assert not result.ok

	def test_channel_name(self) -> None:
		assert SMSAdapter.channel == "sms"


# ---------------------------------------------------------------------------
# FCMPushAdapter
# ---------------------------------------------------------------------------


class TestFCMPushAdapter:
	async def test_deliver_success(self) -> None:
		fake = FakeHTTPClient(FakeResponse(200, _json={"name": "projects/p/messages/1"}))
		adapter = FCMPushAdapter(project_id="myproject", access_token="tok", _http_client=fake)
		result = await adapter.deliver("device-token-xyz", "Push title", "Push body", {"key": "val"})
		assert result.ok
		assert "myproject" in fake.calls[0]["url"]

	async def test_deliver_missing_config(self) -> None:
		adapter = FCMPushAdapter(project_id="", access_token="")
		result = await adapter.deliver("token", "S", "B", {})
		assert not result.ok
		assert "FCM_PROJECT_ID" in (result.error or "")

	async def test_deliver_http_error(self) -> None:
		fake = FakeHTTPClient(FakeResponse(401, "Unauthorized"))
		adapter = FCMPushAdapter(project_id="p", access_token="bad", _http_client=fake)
		result = await adapter.deliver("tok", "S", "B", {})
		assert not result.ok

	def test_channel_name(self) -> None:
		assert FCMPushAdapter.channel == "push"


# ---------------------------------------------------------------------------
# WebhookAdapter (HMAC-signed POST)
# ---------------------------------------------------------------------------


class TestWebhookAdapter:
	async def test_deliver_signs_payload(self) -> None:
		fake = FakeHTTPClient(FakeResponse(200, "ok"))
		adapter = WebhookAdapter(secret="test-secret", _http_client=fake)
		result = await adapter.deliver(
			"https://hook.example.com/recv",
			"Event",
			"Something happened",
			{"ref": "abc"},
		)
		assert result.ok

		call = fake.calls[0]
		sig_header = call["headers"]["X-Flowforge-Signature"]
		assert sig_header.startswith("sha256=")

		# Verify the signature matches
		raw = call["content"]
		expected = "sha256=" + hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
		assert sig_header == expected

	async def test_deliver_payload_is_valid_json(self) -> None:
		fake = FakeHTTPClient(FakeResponse(200, "ok"))
		adapter = WebhookAdapter(secret="s", _http_client=fake)
		await adapter.deliver("https://h.com/", "Subj", "Bod", {"x": 1})
		raw = fake.calls[0]["content"]
		data = json.loads(raw)
		assert data["subject"] == "Subj"
		assert data["body"] == "Bod"

	async def test_deliver_http_error(self) -> None:
		fake = FakeHTTPClient(FakeResponse(500, "err"))
		adapter = WebhookAdapter(secret="s", _http_client=fake)
		result = await adapter.deliver("https://h.com/", "S", "B", {})
		assert not result.ok

	def test_channel_name(self) -> None:
		assert WebhookAdapter.channel == "webhook"


# ---------------------------------------------------------------------------
# SlackAdapter
# ---------------------------------------------------------------------------


class TestSlackAdapter:
	async def test_deliver_success(self) -> None:
		fake = FakeHTTPClient(FakeResponse(200, "ok"))
		adapter = SlackAdapter(_http_client=fake)
		result = await adapter.deliver("https://hooks.slack.com/x", "Alert", "Details here", {})
		assert result.ok
		assert fake.calls[0]["json"]["text"].startswith("*Alert*")

	async def test_deliver_uses_metadata_webhook_url(self) -> None:
		fake = FakeHTTPClient(FakeResponse(200, "ok"))
		adapter = SlackAdapter(_http_client=fake)
		result = await adapter.deliver(
			"",  # empty recipient — should fall back to metadata
			"Alert",
			"Details",
			{"webhook_url": "https://hooks.slack.com/meta"},
		)
		assert result.ok
		assert fake.calls[0]["url"] == "https://hooks.slack.com/meta"

	async def test_deliver_no_url_returns_error(self) -> None:
		adapter = SlackAdapter(webhook_url="", _http_client=None)
		result = await adapter.deliver("", "S", "B", {})
		assert not result.ok
		assert "webhook_url" in (result.error or "")

	async def test_deliver_http_non_ok(self) -> None:
		fake = FakeHTTPClient(FakeResponse(400, "bad_payload"))
		adapter = SlackAdapter(_http_client=fake)
		result = await adapter.deliver("https://h.com/", "S", "B", {})
		assert not result.ok

	def test_channel_name(self) -> None:
		assert SlackAdapter.channel == "slack"
