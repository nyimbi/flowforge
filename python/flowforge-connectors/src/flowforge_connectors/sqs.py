"""AWS SQS trigger connector.

Polls an SQS queue and returns messages per ``execute()`` call.
Heavy dependency (``aiobotocore`` or ``boto3``) is lazy-imported.

Usage::

    from flowforge_connectors.sqs import SQSTrigger

    trigger = SQSTrigger(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/my-queue",
        region="us-east-1",
    )
    result = await trigger.execute({})
    for msg in result.data.get("messages", []):
        body = msg["body"]  # parsed JSON or raw string
        receipt = msg["receipt_handle"]  # pass to delete_message()
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class SQSTrigger(ConnectorBase):
	"""Poll an AWS SQS queue for incoming workflow trigger messages.

	Each ``execute()`` call issues a ``ReceiveMessage`` call returning
	up to *max_messages* (1–10).  Messages are **not** automatically
	deleted — callers must invoke :meth:`delete_message` after processing
	to prevent re-delivery.

	Credentials are resolved via the standard boto3 credential chain
	(env vars, ~/.aws/credentials, IAM role).
	"""

	connector_id = "sqs_trigger"

	def __init__(
		self,
		queue_url: str,
		*,
		region: str = "us-east-1",
		max_messages: int = 10,
		wait_time_seconds: int = 5,
		visibility_timeout: int = 30,
		aws_access_key_id: str | None = None,
		aws_secret_access_key: str | None = None,
		aws_session_token: str | None = None,
		endpoint_url: str | None = None,
	) -> None:
		if not queue_url:
			raise ValueError("queue_url must not be empty")
		if not 1 <= max_messages <= 10:
			raise ValueError("max_messages must be between 1 and 10 (SQS limit)")
		self._queue_url = queue_url
		self._region = region
		self._max_messages = max_messages
		self._wait_time_seconds = wait_time_seconds
		self._visibility_timeout = visibility_timeout
		self._aws_access_key_id = aws_access_key_id
		self._aws_secret_access_key = aws_secret_access_key
		self._aws_session_token = aws_session_token
		self._endpoint_url = endpoint_url
		self._client: Any = None
		self._session: Any = None

	async def _get_client(self) -> Any:
		"""Lazy-init aiobotocore SQS client."""
		if self._client is not None:
			return self._client
		try:
			import aiobotocore.session as aio_session  # type: ignore[import]
		except ImportError:
			try:
				# Fallback: boto3 wrapped in asyncio.to_thread
				import boto3  # type: ignore[import]
				self._client = boto3.client(
					"sqs",
					region_name=self._region,
					aws_access_key_id=self._aws_access_key_id,
					aws_secret_access_key=self._aws_secret_access_key,
					aws_session_token=self._aws_session_token,
					endpoint_url=self._endpoint_url,
				)
				self._use_sync = True
				return self._client
			except ImportError as exc:
				raise ImportError(
					"aiobotocore or boto3 is required for SQSTrigger. "
					"Install with: pip install aiobotocore"
				) from exc

		self._session = aio_session.get_session()
		self._use_sync = False
		ctx = self._session.create_client(
			"sqs",
			region_name=self._region,
			aws_access_key_id=self._aws_access_key_id,
			aws_secret_access_key=self._aws_secret_access_key,
			aws_session_token=self._aws_session_token,
			endpoint_url=self._endpoint_url,
		)
		self._client_ctx = ctx
		self._client = await ctx.__aenter__()
		return self._client

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		"""Receive up to *max_messages* from the SQS queue.

		Returns ``data={"messages": [...]}`` where each message has
		``message_id``, ``receipt_handle``, ``body``, ``attributes``.
		"""
		try:
			import asyncio
			client = await self._get_client()
			kwargs = {
				"QueueUrl": self._queue_url,
				"MaxNumberOfMessages": self._max_messages,
				"WaitTimeSeconds": self._wait_time_seconds,
				"VisibilityTimeout": self._visibility_timeout,
				"AttributeNames": ["All"],
			}
			if getattr(self, "_use_sync", False):
				response = await asyncio.to_thread(client.receive_message, **kwargs)
			else:
				response = await client.receive_message(**kwargs)

			raw_msgs = response.get("Messages", [])
			messages = []
			for m in raw_msgs:
				body_str = m.get("Body", "")
				try:
					body = json.loads(body_str)
				except (json.JSONDecodeError, TypeError):
					body = body_str
				messages.append({
					"message_id": m.get("MessageId"),
					"receipt_handle": m.get("ReceiptHandle"),
					"body": body,
					"attributes": m.get("Attributes", {}),
				})
			return ConnectorResult(
				ok=True,
				data={"messages": messages, "count": len(messages)},
				status_code=200,
			)
		except Exception as exc:
			_log.error("SQSTrigger.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))

	async def delete_message(self, receipt_handle: str) -> ConnectorResult:
		"""Delete a processed message to prevent re-delivery."""
		try:
			import asyncio
			client = await self._get_client()
			kwargs = {"QueueUrl": self._queue_url, "ReceiptHandle": receipt_handle}
			if getattr(self, "_use_sync", False):
				await asyncio.to_thread(client.delete_message, **kwargs)
			else:
				await client.delete_message(**kwargs)
			return ConnectorResult(ok=True, data={"deleted": True})
		except Exception as exc:
			_log.error("SQSTrigger.delete_message failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))

	async def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
		"""SQS messages are not HTTP webhooks — always returns True."""
		return True

	async def close(self) -> None:
		"""Release the aiobotocore client context."""
		if hasattr(self, "_client_ctx") and self._client_ctx is not None:
			try:
				await self._client_ctx.__aexit__(None, None, None)
			except Exception:
				pass
		self._client = None


__all__ = ["SQSTrigger"]
