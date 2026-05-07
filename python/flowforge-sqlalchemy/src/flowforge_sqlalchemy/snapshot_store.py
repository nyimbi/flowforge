"""SQLAlchemy-backed :class:`flowforge.engine.snapshots.SnapshotStore`.

The engine treats the snapshot store as opaque key/value storage keyed
by ``instance_id``. We persist a JSON dump of the
:class:`flowforge.engine.fire.Instance` dataclass and reconstruct on
read. The latest snapshot per instance is kept (``UNIQUE(instance_id)``
on the table); older states are recoverable from the
``workflow_events`` log if needed.
"""

from __future__ import annotations

from typing import Any, cast

from flowforge._uuid7 import uuid7str
from flowforge.engine.fire import Instance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import WorkflowInstanceSnapshot


class SqlAlchemySnapshotStore:
	"""Async SnapshotStore backed by ``workflow_instance_snapshots``.

	Parameters
	----------
	session_factory:
		An :func:`sqlalchemy.ext.asyncio.async_sessionmaker` (or compatible
		zero-arg async-session factory). The store opens its own
		short-lived session per call so it can be used from any caller.
	tenant_id:
		Tenant scope for newly written rows. Reads do not filter by tenant
		(the engine has already resolved the instance) — host-level RLS
		via :class:`PgRlsBinder` provides isolation in production.
	"""

	def __init__(
		self,
		session_factory: async_sessionmaker[AsyncSession],
		*,
		tenant_id: str = "default",
	) -> None:
		assert session_factory is not None, "session_factory is required"
		self._sf = session_factory
		self._tenant_id = tenant_id

	async def get(self, instance_id: str) -> Instance | None:
		"""Return the latest snapshot for *instance_id* or ``None``."""
		assert instance_id, "instance_id must be non-empty"
		async with self._sf() as session:
			row = await session.scalar(
				select(WorkflowInstanceSnapshot).where(
					WorkflowInstanceSnapshot.instance_id == instance_id
				)
			)
			if row is None:
				return None
			body = cast(dict[str, Any], row.body or {})
			return _instance_from_body(row, body)

	async def put(self, instance: Instance) -> None:
		"""Insert or overwrite the snapshot for *instance*."""
		assert instance.id, "instance.id must be non-empty"
		body = _body_from_instance(instance)
		async with self._sf() as session:
			existing = await session.scalar(
				select(WorkflowInstanceSnapshot).where(
					WorkflowInstanceSnapshot.instance_id == instance.id
				)
			)
			if existing is None:
				session.add(
					WorkflowInstanceSnapshot(
						# E-39 / SA-01: time-ordered ids match the engine's
						# uuid7str() convention and pair well with the
						# B-tree index on (tenant_id, instance_id).
						id=uuid7str(),
						tenant_id=self._tenant_id,
						instance_id=instance.id,
						def_key=instance.def_key,
						def_version=instance.def_version,
						state=instance.state,
						body=body,
						seq=len(instance.history),
					)
				)
			else:
				existing.def_key = instance.def_key
				existing.def_version = instance.def_version
				existing.state = instance.state
				existing.body = body
				existing.seq = len(instance.history)
			await session.commit()


def _body_from_instance(instance: Instance) -> dict[str, Any]:
	"""Serialise an :class:`Instance` to JSON-safe ``dict``."""
	return {
		"id": instance.id,
		"def_key": instance.def_key,
		"def_version": instance.def_version,
		"state": instance.state,
		"context": dict(instance.context),
		"created_entities": [list(t) for t in instance.created_entities],
		"saga": list(instance.saga),
		"history": list(instance.history),
	}


def _instance_from_body(row: WorkflowInstanceSnapshot, body: dict[str, Any]) -> Instance:
	"""Hydrate an :class:`Instance` from a snapshot row + body dict."""
	created_entities_raw = body.get("created_entities") or []
	# Stored as ``[entity_kind, row_dict]`` pairs; rebuild tuple shape.
	created_entities: list[tuple[str, dict[str, Any]]] = []
	for pair in created_entities_raw:
		if isinstance(pair, (list, tuple)) and len(pair) == 2:
			kind, payload = pair[0], pair[1]
			created_entities.append((str(kind), dict(payload or {})))
	return Instance(
		id=str(body.get("id") or row.instance_id),
		def_key=str(body.get("def_key") or row.def_key),
		def_version=str(body.get("def_version") or row.def_version),
		state=str(body.get("state") or row.state),
		context=dict(body.get("context") or {}),
		created_entities=created_entities,
		saga=list(body.get("saga") or []),
		history=list(body.get("history") or []),
	)
