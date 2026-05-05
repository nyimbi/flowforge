"""In-memory registries used by the adapter.

Two adapter-local registries:

* :class:`WorkflowDefRegistry` — maps ``def_key`` (and optional version)
  to a parsed :class:`flowforge.dsl.WorkflowDef`. Hosts register their
  workflows on startup.
* :class:`InstanceStore` — wraps :class:`flowforge.engine.InMemorySnapshotStore`
  and adds an instance->def_key index so the runtime router can resolve
  the right def when handling ``POST /instances/{id}/events`` without
  re-walking the registry.

Both registries are process-local; in the UMS host they are intended to
be replaced by SQL-backed adapters in :mod:`flowforge_sqlalchemy`.
"""

from __future__ import annotations

from typing import Any

from flowforge.dsl import WorkflowDef
from flowforge.engine import InMemorySnapshotStore, Instance


class WorkflowDefRegistry:
	"""In-memory ``{def_key: {version: WorkflowDef}}`` lookup."""

	def __init__(self) -> None:
		self._by_key: dict[str, dict[str, WorkflowDef]] = {}

	def register(self, wd: WorkflowDef) -> None:
		"""Register *wd*; later registrations under same (key, version) overwrite."""

		self._by_key.setdefault(wd.key, {})[wd.version] = wd

	def get(self, key: str, version: str | None = None) -> WorkflowDef:
		"""Return the WorkflowDef for *key*; latest version if not specified."""

		bucket = self._by_key.get(key)
		if not bucket:
			raise KeyError(f"unknown workflow def: {key!r}")
		if version is not None:
			wd = bucket.get(version)
			if wd is None:
				raise KeyError(f"unknown version {version!r} for {key!r}")
			return wd
		# Latest version by string sort — semver-ish definitions sort correctly
		# enough for this in-memory adapter; UMS-side adapter does proper semver.
		latest = sorted(bucket.keys())[-1]
		return bucket[latest]

	def list(self) -> list[dict[str, Any]]:
		"""Return a JSON-friendly summary used by the designer router."""

		out: list[dict[str, Any]] = []
		for key, versions in sorted(self._by_key.items()):
			for ver, wd in sorted(versions.items()):
				out.append(
					{
						"key": key,
						"version": ver,
						"subject_kind": wd.subject_kind,
						"initial_state": wd.initial_state,
						"states": [s.name for s in wd.states],
					}
				)
		return out

	def clear(self) -> None:
		self._by_key.clear()


class InstanceStore:
	"""Snapshot store + per-instance metadata used by the runtime router."""

	def __init__(self) -> None:
		self._snapshots = InMemorySnapshotStore()
		self._meta: dict[str, dict[str, str]] = {}

	@property
	def snapshots(self) -> InMemorySnapshotStore:
		return self._snapshots

	async def put(self, instance: Instance) -> None:
		await self._snapshots.put(instance)
		self._meta[instance.id] = {
			"def_key": instance.def_key,
			"def_version": instance.def_version,
		}

	async def get(self, instance_id: str) -> Instance | None:
		return await self._snapshots.get(instance_id)

	def def_for(self, instance_id: str) -> tuple[str, str] | None:
		row = self._meta.get(instance_id)
		if row is None:
			return None
		return row["def_key"], row["def_version"]

	def clear(self) -> None:
		self._snapshots = InMemorySnapshotStore()
		self._meta.clear()


# Module-level singletons. Tests reset them via :func:`reset_state`.
_registry = WorkflowDefRegistry()
_instance_store = InstanceStore()


def get_registry() -> WorkflowDefRegistry:
	"""Return the module-level singleton :class:`WorkflowDefRegistry`."""

	return _registry


def get_instance_store() -> InstanceStore:
	"""Return the module-level singleton :class:`InstanceStore`."""

	return _instance_store


def reset_state() -> None:
	"""Reset both module-level singletons. Use in test fixtures."""

	_registry.clear()
	_instance_store.clear()


__all__ = [
	"InstanceStore",
	"WorkflowDefRegistry",
	"get_instance_store",
	"get_registry",
	"reset_state",
]
