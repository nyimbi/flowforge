"""flowforge-notify-multichannel — multichannel notification adapter.

Implements NotificationPort with:
- in_app   : DB-backed (in-memory fake for tests)
- email    : SMTP / SES
- sms      : Twilio
- push     : FCM
- webhook  : HMAC-signed POST
- slack    : Incoming webhook

Template rendering uses Jinja2 with locale + timezone support.
Throttling and deduplication are enforced per (recipient, template_id).
"""

from .router import MultiChannelNotifier
from .transports import (
    ChannelAdapter,
    EmailAdapter,
    FCMPushAdapter,
    FakeInAppAdapter,
    SESEmailAdapter,
    SlackAdapter,
    SMSAdapter,
    WebhookAdapter,
)

__all__ = [
    "MultiChannelNotifier",
    "ChannelAdapter",
    "EmailAdapter",
    "FCMPushAdapter",
    "FakeInAppAdapter",
    "SESEmailAdapter",
    "SlackAdapter",
    "SMSAdapter",
    "WebhookAdapter",
]
