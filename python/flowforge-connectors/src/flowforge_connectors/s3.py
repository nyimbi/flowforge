"""AWS S3 put-object connector (presigned or direct)."""

from __future__ import annotations

import logging
from typing import Any

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class S3Connector(ConnectorBase):
	"""Upload a document to S3 using aiobotocore or a presigned URL.

	This connector accepts either:
	- ``presigned_url`` + ``content`` — PUT to a presigned URL via httpx (no AWS SDK needed).
	- ``bucket`` + ``key`` + ``content`` — direct SDK PUT (requires aiobotocore).
	"""

	connector_id = "s3"

	def __init__(
		self,
		*,
		aws_access_key_id: str = "",
		aws_secret_access_key: str = "",
		region: str = "us-east-1",
	) -> None:
		self._key_id = aws_access_key_id
		self._secret_key = aws_secret_access_key
		self._region = region

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		presigned_url = payload.get("presigned_url")
		content = payload.get("content", b"")
		if isinstance(content, str):
			content = content.encode()

		if presigned_url:
			return await self._put_presigned(presigned_url, content, payload.get("content_type", "application/octet-stream"))

		bucket = payload.get("bucket", "")
		key = payload.get("key", "")
		if not bucket or not key:
			return ConnectorResult(ok=False, error="S3: provide presigned_url or (bucket + key) in payload")

		try:
			import aiobotocore.session  # type: ignore[import]
			session = aiobotocore.session.get_session()
			async with session.create_client(
				"s3",
				region_name=self._region,
				aws_access_key_id=self._key_id or None,
				aws_secret_access_key=self._secret_key or None,
			) as client:
				await client.put_object(Bucket=bucket, Key=key, Body=content)
			return ConnectorResult(ok=True, data={"bucket": bucket, "key": key})
		except ImportError:
			return ConnectorResult(ok=False, error="aiobotocore not installed; use presigned_url instead")
		except Exception as exc:
			_log.error("S3Connector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))

	async def _put_presigned(self, url: str, content: bytes, content_type: str) -> ConnectorResult:
		import httpx
		try:
			async with httpx.AsyncClient(timeout=60.0) as client:
				r = await client.put(url, content=content, headers={"Content-Type": content_type})
			if r.is_success:
				return ConnectorResult(ok=True, data={"status_code": r.status_code})
			return ConnectorResult(ok=False, error=f"S3 presigned PUT {r.status_code}", status_code=r.status_code)
		except Exception as exc:
			_log.error("S3Connector._put_presigned failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
