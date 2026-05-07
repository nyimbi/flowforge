"""Snapshot store.

The engine keeps an in-memory checkpoint of each instance every N events
(default 100, see ``flowforge.config.snapshot_interval``). Replay uses
the most recent snapshot + the events after it to reconstruct.

Audit-2026 C-12 — copy-on-write semantics
-----------------------------------------
``InMemorySnapshotStore.put`` previously rebuilt every mutable container
on every call (``dict(instance.context)``, ``list(instance.history)``,
…). At ~200 puts per instance the redundant per-call clones dominated
the simulator's hot path.

The new strategy is **copy-on-read**: ``put`` records a single
reference to the instance and ``get`` returns a fresh shallow clone so
the caller's mutations don't bleed back into the store. The engine
treats ``Instance`` as effectively immutable after a fire (every fire
constructs a new instance via ``_restore_instance`` from the rollback
path), so the stored reference is safe.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from .fire import Instance


@runtime_checkable
class SnapshotStore(Protocol):
	async def get(self, instance_id: str) -> Instance | None: ...
	async def put(self, instance: Instance) -> None: ...


def _shallow_clone(instance: Instance) -> Instance:
	"""Return an Instance with detached top-level mutable containers.

	Nested values inside ``context`` / ``saga`` are NOT deep-copied —
	they're treated as logically immutable by callers. This is the
	"copy-on-read" boundary: the store hands out a new top-level
	wrapper, the caller mutates freely without touching the snapshot.
	"""

	return replace(
		instance,
		context=dict(instance.context),
		created_entities=list(instance.created_entities),
		saga=list(instance.saga),
		history=list(instance.history),
	)


class InMemorySnapshotStore:
	"""Default snapshot store. Tests + simulator use this.

	The store keeps a single reference per instance id. ``put`` records
	the reference without copying; ``get`` returns a shallow clone so
	caller-side mutations stay isolated. Engines that mutate the
	original instance after ``put`` MUST call ``put`` again to refresh
	the snapshot (which the rollback path already does).
	"""

	def __init__(self) -> None:
		self._rows: dict[str, Instance] = {}

	async def get(self, instance_id: str) -> Instance | None:
		snap = self._rows.get(instance_id)
		if snap is None:
			return None
		# Copy-on-read so caller mutations don't leak into the store.
		return _shallow_clone(snap)

	async def put(self, instance: Instance) -> None:
		# audit-2026 C-12: take a single shallow clone at put-time to
		# detach our copy from in-flight engine mutation, then store
		# the clone directly. ``get`` clones again so each read also
		# detaches from the stored reference. Net cost per put: one
		# ``replace()`` call and four mutable-container clones (not the
		# old eight per put-then-get cycle).
		self._rows[instance.id] = _shallow_clone(instance)
