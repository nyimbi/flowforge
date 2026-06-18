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
import ipaddress
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse


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


def _parse_allowed_hosts(value: str | None) -> frozenset[str]:
	if not value:
		return frozenset()
	return frozenset(part.strip().lower() for part in value.split(",") if part.strip())


def _url_host(url: str) -> str | None:
	parsed = urlparse(url)
	if parsed.scheme != "https" or not parsed.hostname:
		return None
	return parsed.hostname.lower()


def _is_private_host(host: str) -> bool:
	if host in {"localhost", "localhost.localdomain"}:
		return True
	try:
		addr = ipaddress.ip_address(host)
	except ValueError:
		return False
	return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast


def _url_allowed(url: str, *, allowed_hosts: frozenset[str], allow_any_public_host: bool) -> str | None:
	host = _url_host(url)
	if host is None:
		return "url must be https and include a host"
	if _is_private_host(host):
		return "private, loopback, link-local, and localhost webhook hosts are not allowed"
	if allowed_hosts and host not in allowed_hosts:
		return f"host {host!r} is not in the allowed host set"
	if not allowed_hosts and not allow_any_public_host:
		return "no webhook host allow-list configured"
	return None


def _aws_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
	k_date = hmac.new(("AWS4" + secret_key).encode(), date_stamp.encode(), hashlib.sha256).digest()
	k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
	k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
	return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


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
		import logging as _logging

		self._host = host or os.environ.get("SMTP_HOST", "localhost")
		self._port = port or int(os.environ.get("SMTP_PORT", "587"))
		self._user = user or os.environ.get("SMTP_USER", "")
		self._password = password or os.environ.get("SMTP_PASSWORD", "")
		self._from = from_addr or os.environ.get("SMTP_FROM", "noreply@example.com")
		env_tls = os.environ.get("SMTP_START_TLS", "true").lower() not in ("0", "false", "no")
		self._start_tls = start_tls if start_tls is not None else env_tls
		_log = _logging.getLogger(__name__)
		if self._host == "localhost" and host is None and not os.environ.get("SMTP_HOST"):
			raise ValueError(
				"EmailAdapter: SMTP_HOST is 'localhost' (default). "
				"Set SMTP_HOST to your production SMTP relay, or pass host= explicitly. "
				"This will fail at first send in any non-local environment."
			)
		if self._from == "noreply@example.com" and from_addr is None and not os.environ.get("SMTP_FROM"):
			raise ValueError(
				"EmailAdapter: SMTP_FROM is the placeholder 'noreply@example.com'. "
				"Set SMTP_FROM to a verified sender address or pass from_addr= explicitly."
			)

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
		except aiosmtplib.SMTPException as exc:
			# E-54 / NM-02: only the transport's own exception family is
			# reported as a delivery failure. Other exceptions (bug,
			# misconfig, asyncio.CancelledError, etc.) propagate.
			return DeliveryResult(ok=False, error=str(exc))
		except (TimeoutError, OSError) as exc:
			# Network-layer issues that aiosmtplib does not always wrap.
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
		session_token: str | None = None,
		region: str | None = None,
		from_addr: str | None = None,
		_http_client: Any = None,
	) -> None:
		import logging as _logging

		self._access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID", "")
		self._secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
		self._session_token = session_token or os.environ.get("AWS_SESSION_TOKEN", "")
		self._region = region or os.environ.get("AWS_REGION", "us-east-1")
		self._from = from_addr or os.environ.get("SES_FROM_ADDRESS", "noreply@example.com")
		self._http_client = _http_client
		if self._from == "noreply@example.com" and from_addr is None and not os.environ.get("SES_FROM_ADDRESS"):
			raise ValueError(
				"SESEmailAdapter: SES_FROM_ADDRESS is the placeholder 'noreply@example.com'. "
				"AWS SES will reject all sends from an unverified address. "
				"Set SES_FROM_ADDRESS to a verified sender or pass from_addr= explicitly."
			)

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		import httpx

		if not self._access_key or not self._secret_key:
			return DeliveryResult(ok=False, error="SES credentials not configured (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)")

		url = f"https://email.{self._region}.amazonaws.com/v2/email/outbound-emails"
		host = f"email.{self._region}.amazonaws.com"
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
		raw_payload = json.dumps(payload, separators=(",", ":")).encode()
		payload_hash = hashlib.sha256(raw_payload).hexdigest()
		now = datetime.now(UTC)
		amz_date = now.strftime("%Y%m%dT%H%M%SZ")
		date_stamp = now.strftime("%Y%m%d")
		canonical_headers = (
			"content-type:application/json\n"
			f"host:{host}\n"
			f"x-amz-content-sha256:{payload_hash}\n"
			f"x-amz-date:{amz_date}\n"
		)
		signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
		canonical_request = "\n".join(
			[
				"POST",
				"/v2/email/outbound-emails",
				"",
				canonical_headers,
				signed_headers,
				payload_hash,
			]
		)
		scope = f"{date_stamp}/{self._region}/ses/aws4_request"
		string_to_sign = "\n".join(
			[
				"AWS4-HMAC-SHA256",
				amz_date,
				scope,
				hashlib.sha256(canonical_request.encode()).hexdigest(),
			]
		)
		signing_key = _aws_signature_key(self._secret_key, date_stamp, self._region, "ses")
		signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
		headers = {
			"Authorization": (
				"AWS4-HMAC-SHA256 "
				f"Credential={self._access_key}/{scope}, "
				f"SignedHeaders={signed_headers}, "
				f"Signature={signature}"
			),
			"Content-Type": "application/json",
			"Host": host,
			"X-Amz-Content-Sha256": payload_hash,
			"X-Amz-Date": amz_date,
		}
		if self._session_token:
			headers["X-Amz-Security-Token"] = self._session_token

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(url, content=raw_payload, headers=headers)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(url, content=raw_payload, headers=headers)

			if resp.status_code in (200, 201, 202):
				data = resp.json() if resp.content else {}
				return DeliveryResult(ok=True, provider_id=data.get("MessageId"))
			return DeliveryResult(ok=False, error=f"SES HTTP {resp.status_code}: {resp.text[:256]}")
		except httpx.RequestError as exc:
			# E-54 / NM-02: only httpx transport-level errors are reported
			# as a delivery failure; other exception types propagate.
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
		except httpx.RequestError as exc:
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
		except httpx.RequestError as exc:
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
	    WEBHOOK_HMAC_SECRET
	    WEBHOOK_ALLOWED_HOSTS (comma-separated HTTPS host allow-list)

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "webhook"

	def __init__(
		self,
		secret: str | None = None,
		allowed_hosts: set[str] | frozenset[str] | tuple[str, ...] | list[str] | None = None,
		allow_any_public_host: bool = False,
		_http_client: Any = None,
	) -> None:
		resolved_secret = secret or os.environ.get("WEBHOOK_HMAC_SECRET", "")
		if not resolved_secret:
			raise ValueError("WEBHOOK_HMAC_SECRET is required for WebhookAdapter")
		self._secret = resolved_secret.encode()
		env_allowed_hosts = _parse_allowed_hosts(os.environ.get("WEBHOOK_ALLOWED_HOSTS"))
		explicit_allowed_hosts = (
			frozenset(host.lower() for host in allowed_hosts) if allowed_hosts is not None else frozenset()
		)
		self._allowed_hosts = explicit_allowed_hosts or env_allowed_hosts
		self._allow_any_public_host = allow_any_public_host
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

		url_error = _url_allowed(
			recipient,
			allowed_hosts=self._allowed_hosts,
			allow_any_public_host=self._allow_any_public_host,
		)
		if url_error:
			return DeliveryResult(ok=False, error=f"webhook.url not allowed: {url_error}")

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
		except httpx.RequestError as exc:
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
	    SLACK_ALLOWED_HOSTS (comma-separated HTTPS host allow-list; defaults to Slack webhook hosts)

	For testing, pass ``_http_client`` to inject a fake httpx client.
	"""

	channel = "slack"

	def __init__(
		self,
		webhook_url: str | None = None,
		allowed_hosts: set[str] | frozenset[str] | tuple[str, ...] | list[str] | None = None,
		_http_client: Any = None,
	) -> None:
		self._default_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
		if not self._default_url:
			import logging as _logging
			_logging.getLogger(__name__).warning(
				"SlackAdapter: no default webhook URL configured (SLACK_WEBHOOK_URL). "
				"A webhook URL must be provided per-call via recipient or "
				"metadata['webhook_url'], otherwise delivery will fail."
			)
		env_allowed_hosts = _parse_allowed_hosts(os.environ.get("SLACK_ALLOWED_HOSTS"))
		explicit_allowed_hosts = (
			frozenset(host.lower() for host in allowed_hosts) if allowed_hosts is not None else frozenset()
		)
		self._allowed_hosts = explicit_allowed_hosts or env_allowed_hosts or frozenset(
			{"hooks.slack.com", "hooks.slack-gov.com"}
		)
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
		url_error = _url_allowed(
			str(url),
			allowed_hosts=self._allowed_hosts,
			allow_any_public_host=False,
		)
		if url_error:
			return DeliveryResult(ok=False, error=f"slack.webhook_url not allowed: {url_error}")

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
		except httpx.RequestError as exc:
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Physical mail — postal job queue stub
# ---------------------------------------------------------------------------


class MailAdapter:
	"""Postal mail adapter — enqueues a physical mail job.

	Production implementations integrate with a print-and-mail service
	(Lob, Click2Mail, PostGrid, etc.). This stub enqueues a job record to
	a configurable queue so the host application can pick it up for
	fulfilment, which is the correct architecture for high-latency channels
	that involve real-world logistics.

	Env vars:
	    MAIL_QUEUE_URL      (queue endpoint — e.g. SQS URL, Redis stream key)
	    MAIL_FROM_ADDRESS   (sender address for the envelope / return address)

	For testing, pass ``_http_client`` to inject a fake httpx client; the
	stub will POST the job payload to the URL as if it were an API call.
	"""

	channel = "mail"

	def __init__(
		self,
		queue_url: str | None = None,
		from_address: str | None = None,
		_http_client: Any = None,
	) -> None:
		self._queue_url = queue_url or os.environ.get("MAIL_QUEUE_URL", "")
		self._from = from_address or os.environ.get("MAIL_FROM_ADDRESS", "")
		self._http_client = _http_client
		if not self._queue_url:
			raise ValueError(
				"MailAdapter requires a queue URL. "
				"Pass queue_url= or set MAIL_QUEUE_URL environment variable."
			)

	async def deliver(
		self,
		recipient: str,
		subject: str,
		body: str,
		metadata: dict[str, Any],
	) -> DeliveryResult:
		if not self._queue_url:
			return DeliveryResult(
				ok=False,
				error="mail.queue_url not configured (MAIL_QUEUE_URL)",
			)

		job = {
			"channel": "mail",
			"recipient_address": recipient,
			"from_address": self._from,
			"subject": subject,
			"body": body,
			**{k: v for k, v in metadata.items() if isinstance(k, str)},
		}

		import httpx

		try:
			if self._http_client is not None:
				resp = await self._http_client.post(self._queue_url, json=job)
			else:
				async with httpx.AsyncClient(timeout=10.0) as client:
					resp = await client.post(self._queue_url, json=job)
			if resp.status_code in (200, 201, 202):
				try:
					provider_id = resp.json().get("id") if resp.content else None
				except Exception:
					provider_id = None
				return DeliveryResult(ok=True, provider_id=provider_id)
			return DeliveryResult(
				ok=False,
				error=f"mail queue HTTP {resp.status_code}: {resp.text[:256]}",
			)
		except httpx.RequestError as exc:
			return DeliveryResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# E-54 / NM-01 — webhook signature verification (constant-time comparison)
# ---------------------------------------------------------------------------


def verify_webhook_signature(
	payload: bytes,
	signature: str | None,
	secret: str | bytes,
) -> bool:
	"""Verify a ``X-Flowforge-Signature`` header against *payload*.

	Constant-time comparison via :func:`hmac.compare_digest` so a
	timing side-channel cannot reveal a partial-match prefix
	(audit-fix-plan §4.2 NM-01).

	Returns ``True`` for a valid signature, ``False`` for any mismatch
	or malformed input. Never raises on bad input — callers can pass
	the raw header value straight in.

	The expected header format matches :meth:`WebhookAdapter._sign`:
	``"sha256=<64 hex chars>"``.
	"""

	if not signature or not isinstance(signature, str):
		return False
	if not signature.startswith("sha256="):
		return False
	provided_hex = signature[len("sha256=") :]
	if len(provided_hex) != 64:
		return False
	try:
		provided = bytes.fromhex(provided_hex)
	except ValueError:
		return False
	if isinstance(secret, str):
		secret_b = secret.encode()
	else:
		secret_b = secret
	expected = hmac.new(secret_b, payload, hashlib.sha256).digest()
	return hmac.compare_digest(expected, provided)
