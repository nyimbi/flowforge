# flowforge-notify-multichannel

Multichannel notification adapter for the flowforge framework. Implements `NotificationPort` with six channel adapters, Jinja2 template rendering, locale/timezone support, per-recipient preference routing, throttling, and deduplication.

## Channels

| Channel | Adapter class | Backing service |
|---------|--------------|-----------------|
| `in_app` | `FakeInAppAdapter` | In-memory store (dev/test) |
| `email` | `EmailAdapter` | SMTP via aiosmtplib |
| `email` | `SESEmailAdapter` | Amazon SES v2 REST |
| `sms` | `SMSAdapter` | Twilio REST |
| `push` | `FCMPushAdapter` | Firebase Cloud Messaging v1 |
| `webhook` | `WebhookAdapter` | HMAC-SHA256-signed POST |
| `slack` | `SlackAdapter` | Slack incoming webhook |

## Quick start

```python
from flowforge.ports.types import NotificationSpec
from flowforge_notify_multichannel import MultiChannelNotifier, FakeInAppAdapter, SMSAdapter

notifier = MultiChannelNotifier(
    adapters=[FakeInAppAdapter(), SMSAdapter()],
    throttle_seconds=300,
)

await notifier.register_template(NotificationSpec(
    template_id="otp",
    channels=("sms", "in_app"),
    subject_template="Your OTP",
    body_template="Your one-time code is {{ code }}.",
    locale="en",
))

subject, body = await notifier.render("otp", "en", {"code": "123456"})
await notifier.send("sms", "+15551234567", (subject, body), template_id="otp")
```

## Fanout with recipient preferences

```python
from flowforge_notify_multichannel.router import RecipientPreferences

notifier.register_preferences(
    "alice@example.com",
    RecipientPreferences(channels=["email", "in_app"], timezone="America/New_York"),
)

results = await notifier.fanout(
    "alice@example.com", "otp", "en", {"code": "999"},
    dedupe_key="otp-alice-20240101",
)
# results: {"email": True, "in_app": True}
```

## Environment variables

| Variable | Adapter | Default |
|----------|---------|---------|
| `SMTP_HOST` | `EmailAdapter` | `localhost` |
| `SMTP_PORT` | `EmailAdapter` | `587` |
| `SMTP_USER` | `EmailAdapter` | `` |
| `SMTP_PASSWORD` | `EmailAdapter` | `` |
| `SMTP_FROM` | `EmailAdapter` | `noreply@example.com` |
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

## Running tests

```sh
cd framework/python/flowforge-notify-multichannel
uv run pytest -v
```

All tests use faked HTTP clients — no live credentials needed.
