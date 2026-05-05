"""Channel adapter implementations for flowforge-notify-multichannel.

Each adapter implements the ChannelAdapter Protocol:
    async def deliver(recipient: str, subject: str, body: str, metadata: dict) -> DeliveryResult

Adapters are intentionally thin — they translate (subject, body) to
the wire format and return a DeliveryResult.  All credentials are
read from environment variables at construction time so tests can
patch them without monkeypatching module globals.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryResult:
	"""Outcome of a single delivery attempt."""

	ok: bool
	provider_id: str | None = None
	error: str | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ChannelAdapter(Protocol):
	"""Minimal contract every channel adapter must satisfy."""

	channel: str

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		"""Deliver a pre-rendered (subject, body) to recipient."""
		...


# ---------------------------------------------------------------------------
# In-app (DB-backed, fake for tests)
# ---------------------------------------------------------------------------


@dataclass
class InAppRecord:
	recipient: str
	subject: str
	body: str
	metadata: dict[str, Any]
	ts: float = field(default_factory=time.time)
	read: bool = False


class FakeInAppAdapter:
	"""In-memory in-app notification store.  Suitable for tests and dev."""

	channel = "in_app"

	def __init__(self) -> None:
		self._inbox: list[InAppRecord] = []

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		record = InAppRecord(recipient=recipient, subject=subject, body=body, metadata=metadata)
		self._inbox.append(record)
		return DeliveryResult(ok=True, provider_id=f"inapp-{len(self._inbox)}")

	def inbox_for(self, recipient: str) -> list[InAppRecord]:
		return [r for r in self._inbox if r.recipient == recipient]

	def mark_read(self, recipient: str) -> int:
		count = 0
		for r in self._inbox:
			if r.recipient == recipient and not r.read:
				r.read = True
				count += 1
		return count


# ---------------------------------------------------------------------------
# Email — SMTP
# ---------------------------------------------------------------------------


class EmailAdapter:
	"""SMTP email adapter using aiosmtplib.

	Env vars:
	    SMTP_HOST        (default: localhost)
	    SMTP_PORT        (default: 587)
	    SMTP_USER
	    SMTP_PASSWORD
	    SMTP_FROM        (default: noreply@example.com)
	    SMTP_START_TLS   (default: true)
	"""

	channel = "email"

	def __init__(
		self,
		host: str | None = None,
		port: int | None = None,
		user: str | None = None,
		password: str | None = None,
		from_addr: str | None = None,
		start_tls: bool | None = None,
	) -> None:
		self._host = host or os.environ.get("SMTP_HOST", "localhost")
		self._port = port or int(os.environ.get("SMTP_PORT", "587"))
		self._user = user or os.environ.get("SMTP_USER", "")
		self._password = password or os.environ.get("SMTP_PASSWORD", "")
		self._from = from_addr or os.environ.get("SMTP_FROM", "noreply@example.com")
		env_tls = os.environ.get("SMTP_START_TLS", "true").lower() not in ("0", "false", "no")
		self._start_tls = start_tls if start_tls is not None else env_tls

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import aiosmtplib

		msg = MIMEMultipart("alternative")
		msg["Subject"] = subject
		msg["From"] = self._from
		msg["To"] = recipient
		msg.attach(MIMEText(body, "plain", "utf-8"))
		html = metadata.get("body_html")
		if html:
			msg.attach(MIMEText(html, "html", "utf-8"))

		try:
			await aiosmtplib.send(
				msg,
				hostname=self._host,
				port=self._port,
				username=self._user or None,
				password=self._password or None,
				start_tls=self._start_tls,
			)
			return DeliveryResult(ok=True)
		except Exception as exc:  # noqa: BLE001
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Email — SES (via httpx + AWS SigV4 stub)
# ---------------------------------------------------------------------------


class SESEmailAdapter:
	"""Amazon SES email adapter.

	Uses the SES v2 SendEmail REST endpoint. Credentials read from:
	    AWS_ACCESS_KEY_ID
	    AWS_SECRET_ACCESS_KEY
	    AWS_REGION           (default: us-east-1)
	    SES_FROM_ADDRESS

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "email"

	def __init__(
		self,
		access_key: str | None = None,
		secret_key: str | None = None,
		region: str | None = None,
		from_addr: str | None = None,
		_http_client: Any = None,
	) -> None:
		self._access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID", "")
		self._secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
		self._region = region or os.environ.get("AWS_REGION", "us-east-1")
		self._from = from_addr or os.environ.get("SES_FROM_ADDRESS", "noreply@example.com")
		self._http_client = _http_client

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import httpx

		url = f"https://email.{self._region}.amazonaws.com/v2/email/outbound-emails"
		payload = {
			"FromEmailAddress": self._from,
			"Destination": {"ToAddresses": [recipient]},
			"Content": {
				"Simple": {
					"Subject": {"Data": subject, "Charset": "UTF-8"},
					"Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
				}
			},
		}
		headers = {"Content-Type": "application/json"}
		# Simplified auth — real use should sign with SigV4.
		if self._access_key:
			headers["X-Amz-Access-Key-Id"] = self._access_key

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(url, json=payload, headers=headers)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(url, json=payload, headers=headers)

			if resp.status_code in (200, 201, 202):
				data = resp.json() if resp.content else {}
				return DeliveryResult(ok=True, provider_id=data.get("MessageId"))
			return DeliveryResult(ok=False, error=f"SES HTTP {resp.status_code}: {resp.text[:256]}")
		except Exception as exc:  # noqa: BLE001
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# SMS — Twilio
# ---------------------------------------------------------------------------


class SMSAdapter:
	"""Twilio SMS adapter.

	Env vars:
	    TWILIO_ACCOUNT_SID
	    TWILIO_AUTH_TOKEN
	    TWILIO_FROM_NUMBER   (E.164 format)

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "sms"

	_URL_TEMPLATE = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

	def __init__(
		self,
		account_sid: str | None = None,
		auth_token: str | None = None,
		from_number: str | None = None,
		_http_client: Any = None,
	) -> None:
		self._sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID", "")
		self._token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN", "")
		self._from = from_number or os.environ.get("TWILIO_FROM_NUMBER", "")
		self._http_client = _http_client

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import httpx

		if not self._sid or not self._token or not self._from:
			return DeliveryResult(
				ok=False,
				error="Twilio credentials not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER)",
			)

		url = self._URL_TEMPLATE.format(sid=self._sid)
		sms_body = body or subject

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(
					url,
					auth=(self._sid, self._token),
					data={"From": self._from, "To": recipient, "Body": sms_body},
				)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(
						url,
						auth=(self._sid, self._token),
						data={"From": self._from, "To": recipient, "Body": sms_body},
					)

			if resp.status_code == 201:
				msg_sid = resp.json().get("sid")
				return DeliveryResult(ok=True, provider_id=msg_sid)
			return DeliveryResult(ok=False, error=f"Twilio HTTP {resp.status_code}: {resp.text[:256]}")
		except Exception as exc:  # noqa: BLE001
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Push — FCM
# ---------------------------------------------------------------------------


class FCMPushAdapter:
	"""Firebase Cloud Messaging v1 REST push adapter.

	Env vars:
	    FCM_PROJECT_ID
	    FCM_ACCESS_TOKEN   (short-lived OAuth2 bearer)

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "push"

	_FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"

	def __init__(
		self,
		project_id: str | None = None,
		access_token: str | None = None,
		_http_client: Any = None,
	) -> None:
		self._project = project_id or os.environ.get("FCM_PROJECT_ID", "")
		self._token = access_token or os.environ.get("FCM_ACCESS_TOKEN", "")
		self._http_client = _http_client

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import httpx

		if not self._project or not self._token:
			return DeliveryResult(ok=False, error="FCM not configured (FCM_PROJECT_ID / FCM_ACCESS_TOKEN)")

		url = self._FCM_URL.format(project=self._project)
		payload = {
			"message": {
				"token": recipient,
				"notification": {"title": subject, "body": body or subject},
				"data": {k: str(v) for k, v in metadata.items() if isinstance(k, str)},
			}
		}

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(
					url,
					json=payload,
					headers={"Authorization": f"Bearer {self._token}"},
				)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(
						url,
						json=payload,
						headers={"Authorization": f"Bearer {self._token}"},
					)

			if resp.status_code == 200:
				return DeliveryResult(ok=True, provider_id=resp.json().get("name"))
			return DeliveryResult(ok=False, error=f"FCM HTTP {resp.status_code}: {resp.text[:256]}")
		except Exception as exc:  # noqa: BLE001
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Webhook — HMAC-signed POST
# ---------------------------------------------------------------------------


class WebhookAdapter:
	"""HMAC-signed HTTP POST webhook adapter.

	The recipient field is the webhook URL. Each delivery signs the JSON
	payload with HMAC-SHA256 using ``secret``.  The signature is placed
	in the ``X-Flowforge-Signature`` header as ``sha256=<hex>``.

	Env vars:
	    WEBHOOK_HMAC_SECRET   (default: dev-secret)

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "webhook"

	def __init__(
		self,
		secret: str | None = None,
		_http_client: Any = None,
	) -> None:
		self._secret = (secret or os.environ.get("WEBHOOK_HMAC_SECRET", "dev-secret")).encode()
		self._http_client = _http_client

	def _sign(self, payload: bytes) -> str:
		return "sha256=" + hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import httpx

		envelope = {"subject": subject, "body": body, "metadata": metadata}
		raw = json.dumps(envelope, separators=(",", ":")).encode()
		sig = self._sign(raw)

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(
					recipient,
					content=raw,
					headers={"Content-Type": "application/json", "X-Flowforge-Signature": sig},
				)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(
						recipient,
						content=raw,
						headers={"Content-Type": "application/json", "X-Flowforge-Signature": sig},
					)

			if resp.status_code < 300:
				return DeliveryResult(ok=True)
			return DeliveryResult(ok=False, error=f"Webhook HTTP {resp.status_code}: {resp.text[:256]}")
		except Exception as exc:  # noqa: BLE001
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Slack — incoming webhook
# ---------------------------------------------------------------------------


class SlackAdapter:
	"""Slack incoming webhook adapter.

	The ``recipient`` field is the webhook URL (resolved before calling deliver).
	Alternatively, ``metadata["webhook_url"]`` is used if set.

	Env vars:
	    SLACK_WEBHOOK_URL   (optional fallback)

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "slack"

	def __init__(
		self,
		webhook_url: str | None = None,
		_http_client: Any = None,
	) -> None:
		self._default_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
		self._http_client = _http_client

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import httpx

		url = metadata.get("webhook_url") or recipient or self._default_url
		if not url:
			return DeliveryResult(ok=False, error="slack.webhook_url not configured")

		payload = {"text": f"*{subject}*\n{body}"}

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(url, json=payload)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(url, json=payload)

			if resp.status_code == 200 and resp.text == "ok":
				return DeliveryResult(ok=True)
			return DeliveryResult(ok=False, error=f"Slack HTTP {resp.status_code}: {resp.text[:256]}")
		except Exception as exc:  # noqa: BLE001
			return DeliveryResult(ok=False, error=str(exc))
