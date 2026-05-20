"""SQLAlchemy-backed :class:`flowforge.engine.snapshots.SnapshotStore`.

The engine treats the snapshot store as opaque key/value storage keyed
by ``instance_id``. We persist a JSON dump of the
:class:`flowforge.engine.fire.Instance` dataclass and reconstruct on
read. The latest snapshot per tenant-scoped instance is kept; older
states are recoverable from the ``workflow_events`` log if needed.
Reads and updates are tenant-scoped; row-level security remains a
second layer rather than the only isolation boundary.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, cast

from flowforge._uuid7 import uuid7str
from flowforge.engine.fire import FireResult, Instance, fire as engine_fire
from flowforge.ports.types import Principal
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import OutboxMessage, WorkflowEvent, WorkflowInstance, WorkflowInstanceSnapshot


class SnapshotConflict(RuntimeError):
	"""Raised when a compare-and-swap snapshot write sees a stale version."""

	def __init__(
		self,
		instance_id: str,
		*,
		expected_seq: int,
		actual_seq: int | None,
	) -> None:
		self.instance_id = instance_id
		self.expected_seq = expected_seq
		self.actual_seq = actual_seq
		actual = "missing" if actual_seq is None else str(actual_seq)
		super().__init__(
			f"snapshot conflict for {instance_id}: expected seq {expected_seq}, "
			f"found {actual}"
		)


class SnapshotTenantMismatch(RuntimeError):
	"""Raised when an instance id is not owned by this store's tenant."""

	def __init__(self, instance_id: str, *, tenant_id: str) -> None:
		self.instance_id = instance_id
		self.tenant_id = tenant_id
		super().__init__(f"instance {instance_id} is not owned by tenant {tenant_id}")


class SqlAlchemySnapshotStore:
	"""Async SnapshotStore backed by ``workflow_instance_snapshots``.

	Parameters
	----------
	session_factory:
		An :func:`sqlalchemy.ext.asyncio.async_sessionmaker` (or compatible
		zero-arg async-session factory). The store opens its own
		short-lived session per call so it can be used from any caller.
	tenant_id:
		Tenant scope for reads and writes. Host-level RLS via
		:class:`PgRlsBinder` remains defence in depth, but this adapter does
		not treat ``instance_id`` alone as an authority token.
	"""

	def __init__(
		self,
		session_factory: async_sessionmaker[AsyncSession],
		*,
		tenant_id: str = "default",
		audit_sink: Any | None = None,
	) -> None:
		assert session_factory is not None, "session_factory is required"
		self._sf = session_factory
		self._tenant_id = tenant_id
		self._audit_sink = audit_sink

	async def get(self, instance_id: str) -> Instance | None:
		"""Return the latest snapshot for *instance_id* or ``None``."""
		assert instance_id, "instance_id must be non-empty"
		async with self._sf() as session:
			row = await session.scalar(
				select(WorkflowInstanceSnapshot).where(
					WorkflowInstanceSnapshot.tenant_id == self._tenant_id,
					WorkflowInstanceSnapshot.instance_id == instance_id,
				)
			)
			if row is None:
				return None
			body = cast(dict[str, Any], row.body or {})
			return _instance_from_body(row, body)

	async def get_for_tenant(
		self,
		instance_id: str,
		*,
		tenant_id: str,
	) -> Instance | None:
		"""Return the tenant-owned snapshot used by HTTP runtime adapters."""
		assert instance_id, "instance_id must be non-empty"
		if tenant_id != self._tenant_id:
			return None
		return await self.get(instance_id)

	async def create_instance(
		self,
		instance: Instance,
		*,
		workflow_def: Any,
		tenant_id: str | None = None,
	) -> None:
		"""Create the durable runtime instance row and initial snapshot."""
		assert instance.id, "instance.id must be non-empty"
		effective_tenant = self._write_tenant(instance.id, tenant_id=tenant_id)
		now = datetime.now(timezone.utc)
		body = _body_from_instance(instance)
		seq = len(instance.history)

		async with self._sf() as session:
			session.add(
				WorkflowInstance(
					id=instance.id,
					tenant_id=effective_tenant,
					def_key=instance.def_key,
					def_version=instance.def_version,
					subject_kind=str(workflow_def.subject_kind),
					state=instance.state,
					terminal=_is_terminal_state(workflow_def, instance.state),
					context=dict(instance.context),
					created_at=now,
					updated_at=now,
				)
			)
			session.add(
				WorkflowInstanceSnapshot(
					id=uuid7str(),
					tenant_id=effective_tenant,
					instance_id=instance.id,
					def_key=instance.def_key,
					def_version=instance.def_version,
					state=instance.state,
					body=body,
					seq=seq,
				)
			)
			try:
				await session.commit()
			except IntegrityError as exc:
				await session.rollback()
				raise SnapshotConflict(
					instance.id,
					expected_seq=0,
					actual_seq=await self._current_seq(
						instance.id,
						tenant_id=effective_tenant,
					),
				) from exc

	async def put(self, instance: Instance, *, tenant_id: str | None = None) -> None:
		"""Insert or overwrite the snapshot for *instance*."""
		assert instance.id, "instance.id must be non-empty"
		effective_tenant = self._write_tenant(instance.id, tenant_id=tenant_id)
		body = _body_from_instance(instance)
		seq = len(instance.history)
		async with self._sf() as session:
			await self._assert_instance_owned(session, instance.id)
			existing = await session.scalar(
				select(WorkflowInstanceSnapshot).where(
					WorkflowInstanceSnapshot.tenant_id == effective_tenant,
					WorkflowInstanceSnapshot.instance_id == instance.id,
				)
			)
			if existing is None:
				session.add(
					WorkflowInstanceSnapshot(
						# E-39 / SA-01: time-ordered ids match the engine's
						# uuid7str() convention and pair well with the
						# B-tree index on (tenant_id, instance_id).
						id=uuid7str(),
						tenant_id=effective_tenant,
						instance_id=instance.id,
						def_key=instance.def_key,
						def_version=instance.def_version,
						state=instance.state,
						body=body,
						seq=seq,
					)
				)
			else:
				existing.def_key = instance.def_key
				existing.def_version = instance.def_version
				existing.state = instance.state
				existing.body = body
				existing.seq = seq
			await session.commit()

	async def compare_and_put(self, instance: Instance, *, expected_seq: int) -> None:
		"""Persist *instance* only when the stored ``seq`` matches.

		``seq`` is the durable optimistic-lock version for the latest
		snapshot. It mirrors ``len(instance.history)``. Hosts can read a
		snapshot, fire one event, then call this method with the pre-fire
		sequence; another process that advanced the same
		``(tenant_id, instance_id)`` first causes :class:`SnapshotConflict`
		instead of last-writer-wins data loss.
		"""
		assert instance.id, "instance.id must be non-empty"
		assert expected_seq >= 0, "expected_seq must be non-negative"
		body = _body_from_instance(instance)
		new_seq = len(instance.history)

		async with self._sf() as session:
			await self._assert_instance_owned(session, instance.id)
			result = await session.execute(
				update(WorkflowInstanceSnapshot)
				.where(
					WorkflowInstanceSnapshot.tenant_id == self._tenant_id,
					WorkflowInstanceSnapshot.instance_id == instance.id,
					WorkflowInstanceSnapshot.seq == expected_seq,
				)
				.values(
					def_key=instance.def_key,
					def_version=instance.def_version,
					state=instance.state,
					body=body,
					seq=new_seq,
				)
			)
			if getattr(result, "rowcount", 0) == 1:
				await session.commit()
				return

			current = await session.scalar(
				select(WorkflowInstanceSnapshot.seq).where(
					WorkflowInstanceSnapshot.tenant_id == self._tenant_id,
					WorkflowInstanceSnapshot.instance_id == instance.id,
				)
			)
			if current is None and expected_seq == 0:
				session.add(
					WorkflowInstanceSnapshot(
						id=uuid7str(),
						tenant_id=self._tenant_id,
						instance_id=instance.id,
						def_key=instance.def_key,
						def_version=instance.def_version,
						state=instance.state,
						body=body,
						seq=new_seq,
					)
				)
				try:
					await session.commit()
				except IntegrityError as exc:
					await session.rollback()
					raise SnapshotConflict(
						instance.id,
						expected_seq=expected_seq,
						actual_seq=await self._current_seq(instance.id),
					) from exc
				return

			await session.rollback()
			raise SnapshotConflict(
				instance.id,
				expected_seq=expected_seq,
				actual_seq=current,
			)

	async def fire_and_commit(
		self,
		*,
		wd: Any,
		instance: Instance,
		event: str,
		payload: dict[str, Any] | None = None,
		principal: Principal | None = None,
		tenant_id: str | None = None,
		jtbd_id: str | None = None,
		jtbd_version: str | None = None,
	) -> FireResult:
		"""Fire an event and persist all durable side effects atomically.

		This is the critical-system path for SQLAlchemy-backed hosts. The
		core engine plans/mutates with ``dispatch_ports=False`` so no audit
		or outbox side effect escapes before storage succeeds. One database
		transaction then writes:

		* the optimistic-lock snapshot update,
		* the current ``workflow_instances`` state,
		* one ``workflow_events`` row,
		* audit rows through ``audit_sink.record_in_connection`` when an
		  audit sink was supplied, and
		* pending durable outbox rows for a post-commit drain worker.
		"""
		effective_tenant = tenant_id or self._tenant_id
		if effective_tenant != self._tenant_id:
			raise SnapshotTenantMismatch(instance.id, tenant_id=self._tenant_id)

		pre_fire_snapshot = copy.deepcopy(instance)
		expected_seq = len(pre_fire_snapshot.history)
		result = await engine_fire(
			wd,
			instance,
			event,
			payload=payload,
			principal=principal,
			tenant_id=self._tenant_id,
			jtbd_id=jtbd_id,
			jtbd_version=jtbd_version,
			dispatch_ports=False,
		)
		if result.matched_transition_id is None:
			return result

		try:
			async with self._sf() as session:
				async with session.begin():
					await self._assert_instance_owned(session, instance.id)
					await self._compare_and_put_in_session(
						session,
						instance,
						expected_seq=expected_seq,
					)
					await self._update_instance_row(session, result)
					session.add(
						WorkflowEvent(
							id=uuid7str(),
							tenant_id=self._tenant_id,
							instance_id=instance.id,
							seq=len(instance.history),
							event=event,
							from_state=_transition_payload(result).get("from_state"),
							to_state=result.new_state,
							transition_id=result.matched_transition_id,
							actor_user_id=principal.user_id if principal else None,
							payload=dict(payload or {}),
						)
					)
					if self._audit_sink is not None:
						record_in_connection = getattr(
							self._audit_sink,
							"record_in_connection",
							None,
						)
						if record_in_connection is None:
							raise TypeError(
								"audit_sink must expose record_in_connection(conn, event) "
								"for transactional fire commits"
							)
						conn = await session.connection()
						for audit_event in result.audit_events:
							await record_in_connection(conn, audit_event)
					for envelope in result.outbox_envelopes:
						session.add(
							OutboxMessage(
								id=uuid7str(),
								kind=envelope.kind,
								tenant_id=envelope.tenant_id,
								body=dict(envelope.body or {}),
								status="pending",
								retries=0,
								created_at=datetime.now(timezone.utc),
								correlation_id=envelope.correlation_id,
								dedupe_key=envelope.dedupe_key,
							)
						)
		except SnapshotConflict:
			instance.__dict__.update(pre_fire_snapshot.__dict__)
			raise
		except IntegrityError as exc:
			instance.__dict__.update(pre_fire_snapshot.__dict__)
			raise SnapshotConflict(
				instance.id,
				expected_seq=expected_seq,
				actual_seq=await self._current_seq(instance.id),
			) from exc
		except Exception:
			instance.__dict__.update(pre_fire_snapshot.__dict__)
			raise

		return result

	async def _assert_instance_owned(
		self, session: AsyncSession, instance_id: str
	) -> None:
		owned = await session.scalar(
			select(WorkflowInstance.id).where(
				WorkflowInstance.tenant_id == self._tenant_id,
				WorkflowInstance.id == instance_id,
			)
		)
		if owned is None:
			raise SnapshotTenantMismatch(instance_id, tenant_id=self._tenant_id)

	async def _compare_and_put_in_session(
		self,
		session: AsyncSession,
		instance: Instance,
		*,
		expected_seq: int,
	) -> None:
		body = _body_from_instance(instance)
		new_seq = len(instance.history)
		result = await session.execute(
			update(WorkflowInstanceSnapshot)
			.where(
				WorkflowInstanceSnapshot.tenant_id == self._tenant_id,
				WorkflowInstanceSnapshot.instance_id == instance.id,
				WorkflowInstanceSnapshot.seq == expected_seq,
			)
			.values(
				def_key=instance.def_key,
				def_version=instance.def_version,
				state=instance.state,
				body=body,
				seq=new_seq,
			)
		)
		if getattr(result, "rowcount", 0) == 1:
			return

		current = await session.scalar(
			select(WorkflowInstanceSnapshot.seq).where(
				WorkflowInstanceSnapshot.tenant_id == self._tenant_id,
				WorkflowInstanceSnapshot.instance_id == instance.id,
			)
		)
		if current is None and expected_seq == 0:
			session.add(
				WorkflowInstanceSnapshot(
					id=uuid7str(),
					tenant_id=self._tenant_id,
					instance_id=instance.id,
					def_key=instance.def_key,
					def_version=instance.def_version,
					state=instance.state,
					body=body,
					seq=new_seq,
				)
			)
			return

		raise SnapshotConflict(
			instance.id,
			expected_seq=expected_seq,
			actual_seq=current,
		)

	async def _update_instance_row(
		self,
		session: AsyncSession,
		result: FireResult,
	) -> None:
		await session.execute(
			update(WorkflowInstance)
			.where(
				WorkflowInstance.tenant_id == self._tenant_id,
				WorkflowInstance.id == result.instance.id,
			)
			.values(
				state=result.instance.state,
				terminal=result.terminal,
				context=dict(result.instance.context),
				updated_at=datetime.now(timezone.utc),
			)
		)

	async def _current_seq(
		self,
		instance_id: str,
		*,
		tenant_id: str | None = None,
	) -> int | None:
		"""Return the current seq for conflict diagnostics."""
		effective_tenant = tenant_id or self._tenant_id
		async with self._sf() as session:
			return await session.scalar(
				select(WorkflowInstanceSnapshot.seq).where(
					WorkflowInstanceSnapshot.tenant_id == effective_tenant,
					WorkflowInstanceSnapshot.instance_id == instance_id,
				)
			)

	def _write_tenant(self, instance_id: str, *, tenant_id: str | None) -> str:
		"""Validate a caller-supplied tenant for mutating operations."""
		if tenant_id is None or tenant_id == self._tenant_id:
			return self._tenant_id
		raise SnapshotTenantMismatch(instance_id, tenant_id=self._tenant_id)


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


def _is_terminal_state(workflow_def: Any, state: str) -> bool:
	"""Return whether *state* is terminal in a WorkflowDef-like object."""
	for candidate in getattr(workflow_def, "states", ()):
		if getattr(candidate, "name", None) == state:
			return str(getattr(candidate, "kind", "")).startswith("terminal")
	return False


def _transition_payload(result: FireResult) -> dict[str, Any]:
	"""Return the transition audit payload when present."""
	if not result.audit_events:
		return {}
	payload = result.audit_events[0].payload
	return dict(payload or {}) if isinstance(payload, dict) else {}


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
