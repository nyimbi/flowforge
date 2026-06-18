"""PostgreSQL-backed TaskTrackerPort.

Inserts a row into ``workflow_tasks`` for every operational task
creation request. Hosts wire this via::

    from flowforge_sqlalchemy.task_tracker import PostgresTaskTracker
    flowforge.config.tasks = PostgresTaskTracker(session_factory)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WorkflowTask
from flowforge._uuid7 import uuid7str


class PostgresTaskTracker:
	"""Concrete :class:`flowforge.ports.tasks.TaskTrackerPort` backed by Postgres.

	Args:
		session_factory: Async callable that returns an ``AsyncSession``.
		tenant_id: Tenant to stamp on every task row.
	"""

	def __init__(
		self,
		session_factory: Callable[[], AsyncSession],
		*,
		tenant_id: str = "default",
	) -> None:
		self._session_factory = session_factory
		self._tenant_id = tenant_id

	async def create_task(self, kind: str, ref: str, note: str) -> str:
		task_id = uuid7str()
		async with self._session_factory() as session:
			task = WorkflowTask(
				id=task_id,
				tenant_id=self._tenant_id,
				kind=kind,
				ref=ref,
				note=note,
				status="pending",
			)
			session.add(task)
			await session.commit()
		return task_id

	async def resolve_task(self, task_id: str) -> None:
		"""Mark a task resolved (no-op if not found)."""
		async with self._session_factory() as session:
			await session.execute(
				update(WorkflowTask)
				.where(WorkflowTask.id == task_id)
				.values(status="resolved", resolved_at=datetime.now(timezone.utc))
			)
			await session.commit()
