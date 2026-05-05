# flowforge-notify-multichannel changelog

## 0.1.0 — U12 delivery

Initial implementation.

- `MultiChannelNotifier` — `NotificationPort` impl with Jinja2 sandboxed rendering, locale fallback, timezone injection via `_timezone` ctx key
- Six channel adapters: `FakeInAppAdapter` (in-memory DB), `EmailAdapter` (SMTP/aiosmtplib), `SESEmailAdapter` (AWS SES v2), `SMSAdapter` (Twilio), `FCMPushAdapter` (FCM v1), `WebhookAdapter` (HMAC-SHA256 POST), `SlackAdapter` (incoming webhook)
- Per-recipient preference routing via `RecipientPreferences` (channels + timezone)
- Throttle window: configurable `throttle_seconds` per (recipient, template_id)
- Deduplication: per (recipient, dedupe_key) set; `clear_dedupe()` for test resets
- `dedupe_fingerprint()` helper for deterministic key generation from template + ctx
- All HTTP adapters accept `_http_client` injection for hermetic test isolation
- Full pytest suite with all adapters faked; no live credentials required
