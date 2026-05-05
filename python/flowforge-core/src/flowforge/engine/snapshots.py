"""Snapshot store.

The engine keeps an in-memory checkpoint of each instance every N events
(default 100, see ``flowforge.config.snapshot_interval``). Replay uses
the most recent snapshot + the events after it to reconstruct.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .fire import Instance


@runtime_checkable
class SnapshotStore(Protocol):
	async def get(self, instance_id: str) -> Instance | None: ...
	async def put(self, instance: Instance) -> None: ...


class InMemorySnapshotStore:
	"""Default snapshot store. Tests + simulator use this."""

	def __init__(self) -> None:
		self._rows: dict[str, dict[str, Any]] = {}

	async def get(self, instance_id: str) -> Instance | None:
		raw = self._rows.get(instance_id)
		if not raw:
			return None
		return Instance(**raw)

	async def put(self, instance: Instance) -> None:
		self._rows[instance.id] = {
			"id": instance.id,
			"def_key": instance.def_key,
			"def_version": instance.def_version,
			"state": instance.state,
			"context": dict(instance.context),
			"created_entities": list(instance.created_entities),
			"saga": list(instance.saga),
			"history": list(instance.history),
		}
