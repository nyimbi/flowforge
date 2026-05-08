# flowforge-notify-multichannel

Multichannel notification adapter for flowforge: six transport backends, Jinja2 templates, locale/timezone routing, throttling, and deduplication.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-notify-multichannel
```

## What it does

`MultiChannelNotifier` implements the flowforge `NotificationPort` contract. It holds a registry of channel adapters and a registry of `NotificationSpec` templates keyed by `(template_id, locale)`. Calling `render()` runs the subject and body strings through a sandboxed Jinja2 environment with timezone-aware context; calling `send()` dispatches the rendered output through the requested adapter. `fanout()` combines both steps and delivers across every channel in a recipient's preference list.

The package ships six adapters: `FakeInAppAdapter` (in-memory, for tests and dev), `EmailAdapter` (SMTP via `aiosmtplib`), `SESEmailAdapter` (Amazon SES v2 REST), `SMSAdapter` (Twilio REST), `FCMPushAdapter` (Firebase Cloud Messaging v1), `WebhookAdapter` (HMAC-SHA256-signed POST), and `SlackAdapter` (incoming webhook). All HTTP-based adapters accept an injected `_http_client` so tests require no live credentials.

The package does not provide persistent notification storage, read-receipts, or push token management. It does not implement webhook signature verification for inbound webhooks — use `verify_webhook_signature()` for that at the application layer.

## Quick start

```python
import asyncio
from flowforge.ports.types import NotificationSpec
from flowforge_notify_multichannel import MultiChannelNotifier, FakeInAppAdapter, SMSAdapter

notifier = MultiChannelNotifier(
	adapters=[FakeInAppAdapter(), SMSAdapter()],
	throttle_seconds=300,
)

asyncio.run(notifier.register_template(NotificationSpec(
	template_id="otp",
	channels=("sms", "in_app"),
	subject_template="Your OTP",
	body_template="Your one-time code is {{ code }}.",
	locale="en",
)))

async def demo():
	subject, body = await notifier.render("otp", "en", {"code": "123456"})
	await notifier.send("sms", "+15551234567", (subject, body), template_id="otp")

asyncio.run(demo())
```

## Fanout with recipient preferences

```python
from flowforge_notify_multichannel.router import RecipientPreferences

notifier.register_preferences(
	"alice@example.com",
	RecipientPreferences(channels=["email", "in_app"], timezone="America/New_York"),
)

async def fanout_demo():
	results = await notifier.fanout(
		"alice@example.com", "otp", "en", {"code": "999"},
		dedupe_key="otp-alice-20240101",
	)
	# results: {"email": True, "in_app": True}

asyncio.run(fanout_demo())
```

## Public API

- `MultiChannelNotifier` — main orchestrator; implements `NotificationPort`.
- `ChannelAdapter` — `Protocol` that each transport implements.
- `FakeInAppAdapter` — in-memory store; `inbox_for(recipient)` and `mark_read(recipient)` for test assertions.
- `EmailAdapter` — SMTP via `aiosmtplib`.
- `SESEmailAdapter` — Amazon SES v2 REST.
- `SMSAdapter` — Twilio REST.
- `FCMPushAdapter` — Firebase Cloud Messaging v1.
- `WebhookAdapter` — HMAC-SHA256-signed HTTP POST; signature format `sha256=<64 hex chars>`.
- `SlackAdapter` — Slack incoming webhook.
- `verify_webhook_signature(payload, signature, secret)` — constant-time HMAC verification for inbound webhook requests.
- `RecipientPreferences` — dataclass: `channels`, `timezone`, `metadata`.
- `DeliveryResult` — frozen dataclass: `ok`, `provider_id`, `error`.

## Configuration

| Variable | Adapter | Default |
|---|---|---|
| `SMTP_HOST` | `EmailAdapter` | `localhost` |
| `SMTP_PORT` | `EmailAdapter` | `587` |
| `SMTP_USER` | `EmailAdapter` | `` |
| `SMTP_PASSWORD` | `EmailAdapter` | `` |
| `SMTP_FROM` | `EmailAdapter` | `noreply@example.com` |
| `SMTP_START_TLS` | `EmailAdapter` | `true` |
| `AWS_ACCESS_KEY_ID` | `SESEmailAdapter` | `` |
| `AWS_SECRET_ACCESS_KEY` | `SESEmailAdapter` | `` |
| `AWS_REGION` | `SESEmailAdapter` | `us-east-1` |
| `SES_FROM_ADDRESS` | `SESEmailAdapter` | `noreply@example.com` |
| `TWILIO_ACCOUNT_SID` | `SMSAdapter` | `` |
| `TWILIO_AUTH_TOKEN` | `SMSAdapter` | `` |
| `TWILIO_FROM_NUMBER` | `SMSAdapter` | `` |
| `FCM_PROJECT_ID` | `FCMPushAdapter` | `` |
| `FCM_ACCESS_TOKEN` | `FCMPushAdapter` | `` |
| `WEBHOOK_HMAC_SECRET` | `WebhookAdapter` | `dev-secret` |
| `SLACK_WEBHOOK_URL` | `SlackAdapter` | `` |

## Audit-2026 hardening

- **NM-01** (E-54): `verify_webhook_signature()` uses `hmac.compare_digest` for constant-time comparison, preventing timing-based partial-match attacks on the `sha256=` prefix format.
- **NM-02** (E-54): Each adapter catches only its own transport's exception family (`aiosmtplib.SMTPException` + `OSError` for SMTP; `httpx.RequestError` for HTTP adapters). Other exceptions — including `asyncio.CancelledError` and bugs — propagate rather than being silently swallowed into a `DeliveryResult(ok=False)`.
- **NM-03** (E-54): Timezone lookup failures in `render()` fall back to UTC but preserve the originating exception on `notifier.last_tz_fallback["cause"]` so structured-logging consumers can surface the misconfigured zone name without losing the exception chain.

## Compatibility

- Python 3.11+
- `jinja2`
- `aiosmtplib` (for `EmailAdapter`)
- `httpx` (for `SESEmailAdapter`, `SMSAdapter`, `FCMPushAdapter`, `WebhookAdapter`, `SlackAdapter`)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-jtbd`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-jtbd) — notification specs are generated from JTBD bundles
- [`flowforge-cli`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-cli) — `flowforge jtbd-generate` emits `notifications.py` from a JTBD bundle
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
