# flowforge-connectors

Connector SDK and starter connector implementations for Flowforge workflow hosts.

This package is currently incubating in the workspace at `0.1.0`. It is included
in workspace checks, but it is not part of the 16-package PyPI release gate
described in the root project documentation.

## Included Connectors

- `HTTPWebhookConnector`
- `SlackConnector`
- `SMTPConnector`
- `TwilioSMSConnector`
- `StripeWebhookVerifier`
- `GitHubWebhookVerifier`
- `HubSpotConnector`
- `PostgresQueryConnector`
- `RedisConnector`
- `S3Connector`
- `KafkaTrigger`
- `SQSTrigger`

All connectors subclass `ConnectorBase` and return `ConnectorResult` instead of
raising operational failures.

## Minimal Usage

```python
from flowforge_connectors import HTTPWebhookConnector

connector = HTTPWebhookConnector("https://example.com/hook")
result = await connector.execute({"event": "workflow.completed"})

if not result.ok:
    # Persist or route result.error through the host's retry policy.
    ...
```

Webhook verifiers implement `verify_webhook(body, headers)` and return a boolean
signature verdict.

## Development

```bash
uv run pytest python/flowforge-connectors/tests
```
