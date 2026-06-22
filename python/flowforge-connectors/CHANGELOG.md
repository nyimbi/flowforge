# Changelog

## 0.1.0

- Added the incubating connector SDK with `ConnectorBase` and `ConnectorResult`.
- Added starter outbound connectors for HTTP webhooks, Slack, SMTP, Twilio,
  HubSpot, Postgres, Redis, and S3.
- Added inbound/trigger helpers for Stripe webhooks, GitHub webhooks, Kafka, and
  SQS.
- Added unit tests for construction validation, optional dependency fallbacks,
  webhook verification failures, and trigger polling behavior.
