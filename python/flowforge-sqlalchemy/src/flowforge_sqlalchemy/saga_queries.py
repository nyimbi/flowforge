"""Read/write helpers for the saga ledger table.

The flowforge engine ships an in-memory
:class:`flowforge.engine.saga.SagaLedger`; this module provides the
durable counterpart. Hosts call :meth:`SagaQueries.append`,
:meth:`SagaQueries.list_for_instance`, and :meth:`SagaQueries.mark` from
their compensation worker.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import WorkflowInstance, WorkflowSagaStep


class SagaConflict(RuntimeError):
	"""Raised when a concurrent saga append collides on ``idx``."""

	def __init__(self, instance_id: str, *, idx: int) -> None:
		self.instance_id = instance_id
		self.idx = idx
		super().__init__(f"saga append conflict for {instance_id}: idx {idx} already exists")


class SagaTenantMismatch(RuntimeError):
	"""Raised when an instance id is not owned by this query helper's tenant."""

	def __init__(self, instance_id: str, *, tenant_id: str) -> None:
		self.instance_id = instance_id
		self.tenant_id = tenant_id
		super().__init__(f"instance {instance_id} is not owned by tenant {tenant_id}")


class SagaQueries:
	"""Async read/write helpers for ``workflow_saga_steps``."""

	def __init__(
		self,
		session_factory: async_sessionmaker[AsyncSession],
		*,
		tenant_id: str = "default",
	) -> None:
		assert session_factory is not None, "session_factory is required"
		self._sf = session_factory
		self._tenant_id = tenant_id

	async def append(
		self,
		instance_id: str,
		*,
		kind: str,
		args: dict[str, Any] | None = None,
		status: str = "pending",
	) -> str:
		"""Append a new saga step. Returns the step's row id.

		``idx`` is auto-assigned to the next monotonic position for the
		given ``instance_id``.
		"""
		assert instance_id and kind, "instance_id and kind are required"
		async with self._sf() as session:
			await self._assert_instance_owned(session, instance_id)
			next_idx = (
				await session.scalar(
					select(func.max(WorkflowSagaStep.idx)).where(
						WorkflowSagaStep.tenant_id == self._tenant_id,
						WorkflowSagaStep.instance_id == instance_id,
					)
				)
			)
			next_idx = (next_idx + 1) if next_idx is not None else 0
			row_id = str(uuid.uuid4())
			session.add(
				WorkflowSagaStep(
					id=row_id,
					tenant_id=self._tenant_id,
					instance_id=instance_id,
					idx=next_idx,
					kind=kind,
					args=dict(args or {}),
					status=status,
				)
			)
			try:
				await session.commit()
			except IntegrityError as exc:
				await session.rollback()
				raise SagaConflict(instance_id, idx=next_idx) from exc
			return row_id

	async def list_for_instance(self, instance_id: str) -> list[WorkflowSagaStep]:
		"""All saga rows for *instance_id* ordered by ``idx`` ascending."""
		async with self._sf() as session:
			rows = (
				await session.scalars(
					select(WorkflowSagaStep)
					.where(
						WorkflowSagaStep.tenant_id == self._tenant_id,
						WorkflowSagaStep.instance_id == instance_id,
					)
					.order_by(WorkflowSagaStep.idx.asc())
				)
			).all()
			return list(rows)

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
			raise SagaTenantMismatch(instance_id, tenant_id=self._tenant_id)

	async def mark(self, instance_id: str, idx: int, status: str) -> bool:
		"""Update the ``status`` of one row. Returns ``True`` on hit."""
		assert status in ("pending", "done", "compensated", "failed"), (
			f"invalid saga status: {status!r}"
		)
		async with self._sf() as session:
			row = await session.scalar(
				select(WorkflowSagaStep).where(
					WorkflowSagaStep.tenant_id == self._tenant_id,
					WorkflowSagaStep.instance_id == instance_id,
					WorkflowSagaStep.idx == idx,
				)
			)
			if row is None:
				return False
			row.status = status
			await session.commit()
			return True

	async def list_pending_for_compensation(
		self, instance_id: str
	) -> list[WorkflowSagaStep]:
		"""Pending rows in reverse order — what the compensation worker iterates.

		Saga compensation runs LIFO: the most recently appended ``pending``
		step compensates first.
		"""
		async with self._sf() as session:
			rows = (
				await session.scalars(
					select(WorkflowSagaStep)
					.where(
						WorkflowSagaStep.tenant_id == self._tenant_id,
						WorkflowSagaStep.instance_id == instance_id,
						WorkflowSagaStep.status == "pending",
					)
					.order_by(WorkflowSagaStep.idx.desc())
				)
			).all()
			return list(rows)
