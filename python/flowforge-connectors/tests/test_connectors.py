"""Basic tests for flowforge-connectors."""

from __future__ import annotations

import dataclasses
import sys
from unittest.mock import MagicMock, patch

import pytest

from flowforge_connectors.base import ConnectorBase, ConnectorResult
from flowforge_connectors.github import GitHubWebhookVerifier
from flowforge_connectors.http import HTTPWebhookConnector
from flowforge_connectors.redis_conn import RedisConnector
from flowforge_connectors.s3 import S3Connector
from flowforge_connectors.slack import SlackConnector
from flowforge_connectors.stripe import StripeWebhookVerifier


# ---------------------------------------------------------------------------
# ConnectorResult
# ---------------------------------------------------------------------------

async def test_connector_result_is_frozen():
	r = ConnectorResult(ok=True, data={"x": 1})
	assert dataclasses.is_dataclass(r)
	with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
		r.ok = False  # type: ignore[misc]


async def test_connector_result_defaults():
	r = ConnectorResult(ok=False, error="boom")
	assert r.data == {}
	assert r.status_code is None
	assert r.error == "boom"


# ---------------------------------------------------------------------------
# HTTPWebhookConnector
# ---------------------------------------------------------------------------

async def test_http_connector_raises_on_empty_url():
	with pytest.raises(ValueError, match="URL"):
		HTTPWebhookConnector("")


async def test_http_connector_accepts_valid_url():
	c = HTTPWebhookConnector("https://example.com/hook")
	assert c.connector_id == "http_webhook"


# ---------------------------------------------------------------------------
# SlackConnector
# ---------------------------------------------------------------------------

async def test_slack_connector_raises_on_empty_url():
	with pytest.raises(ValueError, match="webhook_url"):
		SlackConnector("")


async def test_slack_connector_accepts_valid_url():
	c = SlackConnector("https://hooks.slack.com/services/T000/B000/xxxx")
	assert c.connector_id == "slack"


# ---------------------------------------------------------------------------
# StripeWebhookVerifier
# ---------------------------------------------------------------------------

async def test_stripe_verifier_raises_on_empty_secret():
	with pytest.raises(ValueError, match="webhook_secret"):
		StripeWebhookVerifier("")


async def test_stripe_verify_webhook_missing_signature():
	v = StripeWebhookVerifier("whsec_test")
	result = await v.verify_webhook(b'{"type":"test"}', {})
	assert result is False


async def test_stripe_verify_webhook_empty_signature_header():
	v = StripeWebhookVerifier("whsec_test")
	result = await v.verify_webhook(b'{"type":"test"}', {"Stripe-Signature": ""})
	assert result is False


# ---------------------------------------------------------------------------
# GitHubWebhookVerifier
# ---------------------------------------------------------------------------

async def test_github_verifier_raises_on_empty_secret():
	with pytest.raises(ValueError, match="secret"):
		GitHubWebhookVerifier("")


async def test_github_verify_webhook_missing_signature():
	v = GitHubWebhookVerifier("mysecret")
	result = await v.verify_webhook(b'{"action":"opened"}', {})
	assert result is False


async def test_github_verify_webhook_wrong_prefix():
	v = GitHubWebhookVerifier("mysecret")
	result = await v.verify_webhook(b'{"action":"opened"}', {"X-Hub-Signature-256": "sha1=deadbeef"})
	assert result is False


# ---------------------------------------------------------------------------
# RedisConnector — ImportError path
# ---------------------------------------------------------------------------

async def test_redis_connector_returns_error_when_not_installed():
	c = RedisConnector("redis://localhost:6379/0")
	# Temporarily hide the redis module
	with patch.dict(sys.modules, {"redis": None, "redis.asyncio": None}):
		result = await c.execute({"op": "get", "key": "foo"})
	assert result.ok is False
	assert "not installed" in (result.error or "")


async def test_redis_connector_unknown_op():
	"""Without a real Redis server the ImportError fires first, but we can
	verify the unknown-op branch by monkeypatching the import."""
	import types

	fake_redis = types.ModuleType("redis")
	fake_asyncio = types.ModuleType("redis.asyncio")

	# Build a minimal async client mock that supports unknown op
	class FakeClient:
		async def get(self, key): return None
		async def aclose(self): pass

	fake_asyncio.from_url = lambda *a, **kw: FakeClient()
	fake_redis.asyncio = fake_asyncio

	with patch.dict(sys.modules, {"redis": fake_redis, "redis.asyncio": fake_asyncio}):
		c = RedisConnector()
		result = await c.execute({"op": "noop", "key": "k"})

	assert result.ok is False
	assert "unknown op" in (result.error or "")


# ---------------------------------------------------------------------------
# S3Connector — missing bucket+key and no presigned_url
# ---------------------------------------------------------------------------

async def test_s3_connector_error_without_required_fields():
	c = S3Connector()
	result = await c.execute({"content": b"hello"})
	assert result.ok is False
	assert "bucket" in (result.error or "") or "presigned_url" in (result.error or "")


async def test_s3_connector_accepts_constructor_defaults():
	c = S3Connector(region="eu-west-1")
	assert c.connector_id == "s3"
