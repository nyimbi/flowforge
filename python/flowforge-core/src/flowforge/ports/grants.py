"""AccessGrantPort — temporary delegation grants (e.g. SpiceDB tuples)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class AccessGrantPort(Protocol):
	"""Optional grant fanout — engine no-ops if absent."""

	async def grant(self, relation: str, until: datetime | None = None) -> None:
		"""Insert grant tuple *relation* (subject#perm@resource) until *until*."""

	async def revoke(self, relation: str) -> None:
		"""Remove grant tuple *relation* (idempotent)."""
