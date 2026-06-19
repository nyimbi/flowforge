"""Kafka trigger connector.

Polls a Kafka topic and returns one message per ``execute()`` call.
Heavy dependency (``aiokafka``) is lazy-imported — the package only
requires ``flowforge + httpx``.

Usage::

    from flowforge_connectors.kafka import KafkaTrigger

    trigger = KafkaTrigger(
        topic="workflow-events",
        bootstrap_servers="localhost:9092",
        group_id="flowforge-worker",
    )
    result = await trigger.execute({})
    if result.ok:
        message = result.data["message"]
        # fire engine event from message["event"]
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class KafkaTrigger(ConnectorBase):
	"""Poll a Kafka topic for incoming workflow trigger messages.

	Each ``execute()`` call polls for up to *max_records* messages,
	returning them in ``data["messages"]``.  Set *auto_commit=True* to
	commit offsets automatically after each poll.

	The underlying Kafka consumer is created lazily on the first
	``execute()`` call and reused across calls.  Call ``close()``
	explicitly when shutting down to release resources.
	"""

	connector_id = "kafka_trigger"

	def __init__(
		self,
		topic: str,
		bootstrap_servers: str,
		*,
		group_id: str = "flowforge",
		auto_offset_reset: str = "latest",
		max_records: int = 10,
		poll_timeout_ms: int = 1000,
		auto_commit: bool = True,
		security_protocol: str = "PLAINTEXT",
		sasl_mechanism: str | None = None,
		sasl_username: str | None = None,
		sasl_password: str | None = None,
	) -> None:
		if not topic:
			raise ValueError("topic must not be empty")
		if not bootstrap_servers:
			raise ValueError("bootstrap_servers must not be empty")
		self._topic = topic
		self._bootstrap_servers = bootstrap_servers
		self._group_id = group_id
		self._auto_offset_reset = auto_offset_reset
		self._max_records = max_records
		self._poll_timeout_ms = poll_timeout_ms
		self._auto_commit = auto_commit
		self._security_protocol = security_protocol
		self._sasl_mechanism = sasl_mechanism
		self._sasl_username = sasl_username
		self._sasl_password = sasl_password
		self._consumer: Any = None

	async def _get_consumer(self) -> Any:
		"""Lazy-init the aiokafka consumer."""
		if self._consumer is not None:
			return self._consumer
		try:
			from aiokafka import AIOKafkaConsumer  # type: ignore[import]
		except ImportError as exc:
			raise ImportError(
				"aiokafka is required for KafkaTrigger. "
				"Install it with: pip install aiokafka"
			) from exc

		kwargs: dict[str, Any] = {
			"bootstrap_servers": self._bootstrap_servers,
			"group_id": self._group_id,
			"auto_offset_reset": self._auto_offset_reset,
			"enable_auto_commit": self._auto_commit,
			"value_deserializer": lambda v: json.loads(v.decode("utf-8")),
			"security_protocol": self._security_protocol,
		}
		if self._sasl_mechanism:
			kwargs["sasl_mechanism"] = self._sasl_mechanism
		if self._sasl_username:
			kwargs["sasl_plain_username"] = self._sasl_username
		if self._sasl_password:
			kwargs["sasl_plain_password"] = self._sasl_password

		consumer = AIOKafkaConsumer(self._topic, **kwargs)
		await consumer.start()
		self._consumer = consumer
		_log.info("KafkaTrigger: consumer started for topic=%r group=%r", self._topic, self._group_id)
		return consumer

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		"""Poll the Kafka topic for up to *max_records* messages.

		Returns ``data={"messages": [...]}`` where each message is a
		dict with ``offset``, ``partition``, ``key``, ``value``.
		"""
		try:
			consumer = await self._get_consumer()
			records = await consumer.getmany(
				timeout_ms=self._poll_timeout_ms,
				max_records=self._max_records,
			)
			messages = []
			for tp, msgs in records.items():
				for msg in msgs:
					messages.append({
						"topic": msg.topic,
						"partition": msg.partition,
						"offset": msg.offset,
						"key": msg.key.decode("utf-8") if msg.key else None,
						"value": msg.value,
						"timestamp": msg.timestamp,
					})
			return ConnectorResult(
				ok=True,
				data={"messages": messages, "count": len(messages)},
				status_code=200,
			)
		except Exception as exc:
			_log.error("KafkaTrigger.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))

	async def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
		"""Kafka messages are not HTTP webhooks — always returns True."""
		return True

	async def commit(self) -> None:
		"""Manually commit the current consumer offset."""
		if self._consumer is not None and not self._auto_commit:
			await self._consumer.commit()

	async def close(self) -> None:
		"""Stop the underlying Kafka consumer and release resources."""
		if self._consumer is not None:
			await self._consumer.stop()
			self._consumer = None
			_log.info("KafkaTrigger: consumer stopped for topic=%r", self._topic)


__all__ = ["KafkaTrigger"]
