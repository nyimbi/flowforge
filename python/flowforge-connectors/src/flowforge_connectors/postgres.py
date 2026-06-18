"""PostgreSQL query connector for workflow steps that need DB reads."""

from __future__ import annotations

import logging
from typing import Any

from .base import ConnectorBase, ConnectorResult

_log = logging.getLogger(__name__)


class PostgresQueryConnector(ConnectorBase):
	"""Execute a parameterised read-only query and return rows.

	Args:
		dsn: Postgres DSN (``postgresql+asyncpg://...``).
	"""

	connector_id = "postgres_query"

	def __init__(self, dsn: str) -> None:
		if not dsn:
			raise ValueError("PostgresQueryConnector requires a DSN")
		self._dsn = dsn

	async def execute(self, payload: dict[str, Any]) -> ConnectorResult:
		sql = payload.get("sql", "")
		params = payload.get("params", {})
		if not sql:
			return ConnectorResult(ok=False, error="PostgresQueryConnector: 'sql' required in payload")
		try:
			from sqlalchemy.ext.asyncio import create_async_engine
			from sqlalchemy import text
			engine = create_async_engine(self._dsn, echo=False)
			async with engine.connect() as conn:
				result = await conn.execute(text(sql), params)
				rows = [dict(row._mapping) for row in result.fetchall()]
			await engine.dispose()
			return ConnectorResult(ok=True, data={"rows": rows, "count": len(rows)})
		except Exception as exc:
			_log.error("PostgresQueryConnector.execute failed: %s", exc)
			return ConnectorResult(ok=False, error=str(exc))
