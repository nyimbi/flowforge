"""flowforge-connectors — Connector SDK and 10 starter connectors.

Import what you need::

    from flowforge_connectors import HTTPWebhookConnector, SlackConnector
    from flowforge_connectors.base import ConnectorBase, ConnectorResult
"""

from .base import ConnectorBase, ConnectorResult
from .github import GitHubWebhookVerifier
from .http import HTTPWebhookConnector
from .hubspot import HubSpotConnector
from .postgres import PostgresQueryConnector
from .redis_conn import RedisConnector
from .s3 import S3Connector
from .slack import SlackConnector
from .smtp import SMTPConnector
from .stripe import StripeWebhookVerifier
from .twilio import TwilioSMSConnector

__all__ = [
	"ConnectorBase",
	"ConnectorResult",
	"GitHubWebhookVerifier",
	"HTTPWebhookConnector",
	"HubSpotConnector",
	"PostgresQueryConnector",
	"RedisConnector",
	"S3Connector",
	"SlackConnector",
	"SMTPConnector",
	"StripeWebhookVerifier",
	"TwilioSMSConnector",
]
