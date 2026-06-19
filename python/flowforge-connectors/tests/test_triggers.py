"""Tests for KafkaTrigger and SQSTrigger without real Kafka/SQS."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flowforge_connectors import KafkaTrigger, SQSTrigger
from flowforge_connectors.base import ConnectorResult


# ---------------------------------------------------------------------------
# KafkaTrigger — construction validation
# ---------------------------------------------------------------------------

def test_kafka_trigger_requires_topic():
	with pytest.raises(ValueError, match="topic"):
		KafkaTrigger(topic="", bootstrap_servers="localhost:9092")


def test_kafka_trigger_requires_bootstrap_servers():
	with pytest.raises(ValueError, match="bootstrap_servers"):
		KafkaTrigger(topic="events", bootstrap_servers="")


def test_kafka_trigger_defaults():
	t = KafkaTrigger(topic="my-topic", bootstrap_servers="localhost:9092")
	assert t._topic == "my-topic"
	assert t._group_id == "flowforge"
	assert t._max_records == 10
	assert t._auto_commit is True
	assert t._security_protocol == "PLAINTEXT"
	assert t._consumer is None


def test_kafka_trigger_custom_params():
	t = KafkaTrigger(
		topic="t",
		bootstrap_servers="broker:9093",
		group_id="my-group",
		auto_offset_reset="earliest",
		max_records=5,
		poll_timeout_ms=500,
		auto_commit=False,
		security_protocol="SASL_SSL",
		sasl_mechanism="PLAIN",
		sasl_username="user",
		sasl_password="pass",
	)
	assert t._group_id == "my-group"
	assert t._auto_offset_reset == "earliest"
	assert t._max_records == 5
	assert t._auto_commit is False
	assert t._sasl_mechanism == "PLAIN"
	assert t._sasl_username == "user"


def test_kafka_connector_id():
	assert KafkaTrigger.connector_id == "kafka_trigger"


async def test_kafka_trigger_execute_no_aiokafka():
	"""ImportError from missing aiokafka → ConnectorResult(ok=False)."""
	t = KafkaTrigger(topic="t", bootstrap_servers="localhost:9092")
	with patch.dict("sys.modules", {"aiokafka": None}):
		result = await t.execute({})
	assert isinstance(result, ConnectorResult)
	assert result.ok is False
	assert result.error is not None


async def test_kafka_trigger_execute_with_mock_consumer():
	"""Mock aiokafka consumer returns 2 messages."""
	msg1 = MagicMock()
	msg1.topic = "t"
	msg1.partition = 0
	msg1.offset = 1
	msg1.key = b"k1"
	msg1.value = {"event": "order_placed"}
	msg1.timestamp = 1700000000000

	msg2 = MagicMock()
	msg2.topic = "t"
	msg2.partition = 0
	msg2.offset = 2
	msg2.key = None
	msg2.value = {"event": "order_shipped"}
	msg2.timestamp = 1700000001000

	mock_consumer = AsyncMock()
	mock_consumer.getmany = AsyncMock(return_value={
		MagicMock(): [msg1, msg2]
	})

	t = KafkaTrigger(topic="t", bootstrap_servers="localhost:9092")
	t._consumer = mock_consumer

	result = await t.execute({})
	assert result.ok is True
	assert result.data["count"] == 2
	assert result.data["messages"][0]["key"] == "k1"
	assert result.data["messages"][1]["key"] is None


async def test_kafka_trigger_execute_empty_poll():
	mock_consumer = AsyncMock()
	mock_consumer.getmany = AsyncMock(return_value={})

	t = KafkaTrigger(topic="t", bootstrap_servers="x:9092")
	t._consumer = mock_consumer

	result = await t.execute({})
	assert result.ok is True
	assert result.data["count"] == 0
	assert result.data["messages"] == []


async def test_kafka_trigger_execute_consumer_exception():
	mock_consumer = AsyncMock()
	mock_consumer.getmany = AsyncMock(side_effect=RuntimeError("broker gone"))

	t = KafkaTrigger(topic="t", bootstrap_servers="x:9092")
	t._consumer = mock_consumer

	result = await t.execute({})
	assert result.ok is False
	assert "broker gone" in result.error


async def test_kafka_trigger_verify_webhook():
	t = KafkaTrigger(topic="t", bootstrap_servers="x:9092")
	assert await t.verify_webhook(b"body", {}) is True


async def test_kafka_trigger_close_stops_consumer():
	mock_consumer = AsyncMock()
	mock_consumer.stop = AsyncMock()
	t = KafkaTrigger(topic="t", bootstrap_servers="x:9092")
	t._consumer = mock_consumer
	await t.close()
	mock_consumer.stop.assert_awaited_once()
	assert t._consumer is None


async def test_kafka_trigger_close_noop_if_no_consumer():
	t = KafkaTrigger(topic="t", bootstrap_servers="x:9092")
	await t.close()  # should not raise


# ---------------------------------------------------------------------------
# SQSTrigger — construction validation
# ---------------------------------------------------------------------------

def test_sqs_trigger_requires_queue_url():
	with pytest.raises(ValueError, match="queue_url"):
		SQSTrigger(queue_url="")


def test_sqs_trigger_max_messages_bounds():
	with pytest.raises(ValueError, match="max_messages"):
		SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q", max_messages=0)
	with pytest.raises(ValueError, match="max_messages"):
		SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q", max_messages=11)


def test_sqs_trigger_valid_max_messages():
	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q", max_messages=1)
	assert t._max_messages == 1
	t2 = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q", max_messages=10)
	assert t2._max_messages == 10


def test_sqs_trigger_defaults():
	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q")
	assert t._region == "us-east-1"
	assert t._max_messages == 10
	assert t._wait_time_seconds == 5
	assert t._visibility_timeout == 30
	assert t._client is None


def test_sqs_connector_id():
	assert SQSTrigger.connector_id == "sqs_trigger"


async def test_sqs_trigger_execute_with_mock_client():
	"""Mock boto3/aiobotocore returns 2 SQS messages."""
	mock_client = AsyncMock()
	mock_client.receive_message = AsyncMock(return_value={
		"Messages": [
			{
				"MessageId": "msg1",
				"ReceiptHandle": "rh1",
				"Body": '{"event": "order_placed"}',
				"Attributes": {},
			},
			{
				"MessageId": "msg2",
				"ReceiptHandle": "rh2",
				"Body": "plain string body",
				"Attributes": {"ApproximateReceiveCount": "1"},
			},
		]
	})

	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/1/q")
	t._client = mock_client
	t._use_sync = False

	result = await t.execute({})
	assert result.ok is True
	assert result.data["count"] == 2
	msgs = result.data["messages"]
	assert msgs[0]["message_id"] == "msg1"
	assert msgs[0]["body"] == {"event": "order_placed"}  # parsed JSON
	assert msgs[1]["body"] == "plain string body"  # raw string passthrough
	assert msgs[1]["receipt_handle"] == "rh2"


async def test_sqs_trigger_execute_empty_queue():
	mock_client = AsyncMock()
	mock_client.receive_message = AsyncMock(return_value={})

	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/1/q")
	t._client = mock_client
	t._use_sync = False

	result = await t.execute({})
	assert result.ok is True
	assert result.data["count"] == 0


async def test_sqs_trigger_execute_exception():
	mock_client = AsyncMock()
	mock_client.receive_message = AsyncMock(side_effect=ConnectionError("network down"))

	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/1/q")
	t._client = mock_client
	t._use_sync = False

	result = await t.execute({})
	assert result.ok is False
	assert "network down" in result.error


async def test_sqs_trigger_delete_message():
	mock_client = AsyncMock()
	mock_client.delete_message = AsyncMock(return_value={})

	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/1/q")
	t._client = mock_client
	t._use_sync = False

	result = await t.delete_message("receipt-handle-123")
	assert result.ok is True
	mock_client.delete_message.assert_awaited_once_with(
		QueueUrl="https://sqs.us-east-1.amazonaws.com/1/q",
		ReceiptHandle="receipt-handle-123",
	)


async def test_sqs_trigger_delete_message_exception():
	mock_client = AsyncMock()
	mock_client.delete_message = AsyncMock(side_effect=RuntimeError("auth failed"))

	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/1/q")
	t._client = mock_client
	t._use_sync = False

	result = await t.delete_message("rh")
	assert result.ok is False
	assert "auth failed" in result.error


async def test_sqs_trigger_verify_webhook():
	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q")
	assert await t.verify_webhook(b"body", {}) is True


async def test_sqs_trigger_no_aiobotocore_no_boto3():
	"""Both imports fail → ConnectorResult(ok=False)."""
	t = SQSTrigger(queue_url="https://sqs.us-east-1.amazonaws.com/x/q")
	with patch.dict("sys.modules", {"aiobotocore": None, "aiobotocore.session": None, "boto3": None}):
		result = await t.execute({})
	assert result.ok is False
