"""E-54 — notify transports HMAC + exception hardening.

Audit findings (audit-fix-plan §4.2/§4.3 NM-01..03, §7 E-54):

- NM-01 (P1): all HMAC verify paths use ``hmac.compare_digest``.
- NM-02 (P2): each transport catches its transport-specific exception
  types (httpx / aiosmtplib); other exception types propagate so an
  unrelated bug does not get silently logged as a delivery failure.
- NM-03 (P2): the timezone fallback in
  ``MultichannelRouter.render`` chains the original ``ZoneInfo`` error
  via ``__cause__`` so a tracing consumer can see the original tz
  resolution failure.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
from typing import Any

import pytest


def _drive(coro: Any) -> Any:
	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		return loop.run_until_complete(coro)
	finally:
		loop.close()


# ---------------------------------------------------------------------------
# NM-01 — webhook verify uses hmac.compare_digest
# ---------------------------------------------------------------------------


def test_NM_01_verify_webhook_signature_uses_compare_digest_in_source() -> None:
	"""The verifier source uses ``hmac.compare_digest`` (not ``==``)."""

	from flowforge_notify_multichannel import transports

	src = inspect.getsource(transports)
	assert "hmac.compare_digest" in src, (
		"flowforge_notify_multichannel.transports must call hmac.compare_digest "
		"on signature verification (NM-01)."
	)


def test_NM_01_verify_webhook_signature_accepts_valid_signature() -> None:
	"""The verifier returns True for a signature minted by the same secret."""

	from flowforge_notify_multichannel.transports import (
		WebhookAdapter,
		verify_webhook_signature,
	)

	adapter = WebhookAdapter(secret="s3cret")
	payload = b'{"a":1,"b":"x"}'
	sig = adapter._sign(payload)

	assert verify_webhook_signature(payload, sig, "s3cret") is True


def test_NM_01_verify_webhook_signature_rejects_tampered_signature() -> None:
	"""Any single-byte change in the signature is rejected."""

	from flowforge_notify_multichannel.transports import (
		WebhookAdapter,
		verify_webhook_signature,
	)

	adapter = WebhookAdapter(secret="s3cret")
	payload = b"hello"
	sig = adapter._sign(payload)
	tampered = sig[:-1] + ("0" if sig[-1] != "0" else "1")
	assert verify_webhook_signature(payload, tampered, "s3cret") is False


def test_NM_01_verify_webhook_signature_rejects_wrong_secret() -> None:
	"""A signature minted with a different secret is rejected."""

	from flowforge_notify_multichannel.transports import (
		WebhookAdapter,
		verify_webhook_signature,
	)

	mint = WebhookAdapter(secret="s3cret")
	payload = b"abc"
	sig = mint._sign(payload)
	assert verify_webhook_signature(payload, sig, "different") is False


def test_NM_01_verify_handles_malformed_signature_safely() -> None:
	"""Malformed signature shapes return False instead of raising."""

	from flowforge_notify_multichannel.transports import verify_webhook_signature

	for bad in ("", "not-a-sig", "sha256=", "sha1=abc", "sha256=zzz", None):
		assert verify_webhook_signature(b"x", bad, "s") is False  # type: ignore[arg-type]


def test_NM_01_compare_digest_avoids_timing_leak() -> None:
	"""Sanity: the verifier uses compare_digest (so hmac == hmac on bytes).

	Direct path comparison cannot easily test the timing channel, so we
	just verify the contract: equal-length unequal sigs always return
	False (no early-exit on first differing byte)."""

	from flowforge_notify_multichannel.transports import verify_webhook_signature

	good = "sha256=" + hmac.new(b"s", b"x", hashlib.sha256).hexdigest()
	# All-zero hex of the same length.
	bad = "sha256=" + ("0" * 64)
	assert verify_webhook_signature(b"x", good, "s") is True
	assert verify_webhook_signature(b"x", bad, "s") is False


# ---------------------------------------------------------------------------
# NM-02 — transport-specific exception types
# ---------------------------------------------------------------------------


class _FakeHttpResponse:
	def __init__(self, status_code: int, text: str = "", json_body: Any = None) -> None:
		self.status_code = status_code
		self.text = text
		self.content = text.encode() if text else b""
		self._json = json_body or {}

	def json(self) -> Any:
		return self._json


class _StubHttpClient:
	def __init__(self, exc: BaseException | None = None, response: Any = None) -> None:
		self._exc = exc
		self._response = response

	async def post(self, *args: Any, **kwargs: Any) -> Any:
		if self._exc is not None:
			raise self._exc
		return self._response


def test_NM_02_ses_swallows_httpx_request_error_only() -> None:
	"""SES adapter catches ``httpx.RequestError`` (or its subclasses)
	and returns ``DeliveryResult(ok=False)``; unrelated exceptions
	propagate up the stack."""

	import httpx

	from flowforge_notify_multichannel.transports import SESEmailAdapter

	# httpx.RequestError → graceful DeliveryResult(ok=False)
	adapter = SESEmailAdapter(
		access_key="k",
		secret_key="s",
		region="us-east-1",
		from_addr="x@e.com",
		_http_client=_StubHttpClient(exc=httpx.ConnectTimeout("network down")),
	)
	r = _drive(adapter.deliver("to@e.com", "s", "b", {}))
	assert r.ok is False
	assert "network down" in (r.error or "")

	# Unrelated exception → propagate.
	adapter_kaboom = SESEmailAdapter(
		access_key="k",
		secret_key="s",
		region="us-east-1",
		from_addr="x@e.com",
		_http_client=_StubHttpClient(exc=ZeroDivisionError("synthetic")),
	)
	with pytest.raises(ZeroDivisionError):
		_drive(adapter_kaboom.deliver("to@e.com", "s", "b", {}))


def test_NM_02_twilio_swallows_httpx_request_error_only() -> None:
	import httpx

	from flowforge_notify_multichannel.transports import SMSAdapter

	adapter = SMSAdapter(
		account_sid="AC123",
		auth_token="t",
		from_number="+15555550000",
		_http_client=_StubHttpClient(exc=httpx.NetworkError("oops")),
	)
	r = _drive(adapter.deliver("+15555551234", "s", "b", {}))
	assert r.ok is False

	adapter_kaboom = SMSAdapter(
		account_sid="AC123",
		auth_token="t",
		from_number="+15555550000",
		_http_client=_StubHttpClient(exc=KeyError("synthetic")),
	)
	with pytest.raises(KeyError):
		_drive(adapter_kaboom.deliver("+15555551234", "s", "b", {}))


def test_NM_02_fcm_swallows_httpx_request_error_only() -> None:
	import httpx

	from flowforge_notify_multichannel.transports import FCMPushAdapter

	adapter = FCMPushAdapter(
		project_id="p",
		access_token="t",
		_http_client=_StubHttpClient(exc=httpx.ReadTimeout("slow")),
	)
	r = _drive(adapter.deliver("dev-token", "s", "b", {}))
	assert r.ok is False

	adapter_kaboom = FCMPushAdapter(
		project_id="p",
		access_token="t",
		_http_client=_StubHttpClient(exc=AttributeError("synthetic")),
	)
	with pytest.raises(AttributeError):
		_drive(adapter_kaboom.deliver("dev-token", "s", "b", {}))


def test_NM_02_webhook_swallows_httpx_request_error_only() -> None:
	import httpx

	from flowforge_notify_multichannel.transports import WebhookAdapter

	adapter = WebhookAdapter(
		secret="s",
		_http_client=_StubHttpClient(exc=httpx.ConnectError("refused")),
	)
	r = _drive(adapter.deliver("https://example", "s", "b", {}))
	assert r.ok is False

	adapter_kaboom = WebhookAdapter(
		secret="s",
		_http_client=_StubHttpClient(exc=RuntimeError("synthetic")),
	)
	with pytest.raises(RuntimeError):
		_drive(adapter_kaboom.deliver("https://example", "s", "b", {}))


def test_NM_02_slack_swallows_httpx_request_error_only() -> None:
	import httpx

	from flowforge_notify_multichannel.transports import SlackAdapter

	adapter = SlackAdapter(
		webhook_url="https://hooks.slack.com/x",
		_http_client=_StubHttpClient(exc=httpx.ConnectError("refused")),
	)
	r = _drive(adapter.deliver("https://hooks.slack.com/x", "s", "b", {}))
	assert r.ok is False

	adapter_kaboom = SlackAdapter(
		webhook_url="https://hooks.slack.com/x",
		_http_client=_StubHttpClient(exc=ValueError("synthetic")),
	)
	with pytest.raises(ValueError):
		_drive(adapter_kaboom.deliver("https://hooks.slack.com/x", "s", "b", {}))


# ---------------------------------------------------------------------------
# NM-03 — timezone fallback chains __cause__
# ---------------------------------------------------------------------------


def test_NM_03_timezone_fallback_chains_cause_in_metadata() -> None:
	"""When a recipient preference points at an unknown timezone, the
	notifier chains the original ``ZoneInfoNotFoundError`` (or whatever
	caused the lookup to fail) via ``__cause__`` on a wrapper warning
	captured in ``notifier.last_tz_fallback`` so observability can see
	the real failure."""

	from flowforge.ports.types import NotificationSpec
	from flowforge_notify_multichannel.router import MultiChannelNotifier

	notifier = MultiChannelNotifier()
	spec = NotificationSpec(
		template_id="t1",
		locale="en",
		subject_template="hi",
		body_template="b",
		channels=("in_app",),
	)
	_drive(notifier.register_template(spec))

	# Render with a bogus timezone — must NOT raise; must fall back to
	# UTC; must record the cause for observability.
	subject, body = _drive(notifier.render("t1", "en", {"_timezone": "Mars/Phobos"}))
	assert subject == "hi" and body == "b"

	last = notifier.last_tz_fallback
	assert last is not None
	assert last["requested"] == "Mars/Phobos"
	assert last["fallback"] == "UTC"
	# __cause__ wired through.
	assert last["cause"] is not None
	# The cause is a real exception (ZoneInfoNotFoundError or similar).
	assert isinstance(last["cause"], Exception)
