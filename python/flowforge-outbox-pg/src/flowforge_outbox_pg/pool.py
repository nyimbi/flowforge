"""Activity worker pool — run N DrainWorker instances concurrently.

Production deployments typically run a single ``DrainWorker``, but
high-throughput tenants benefit from multiple concurrent workers each
holding a separate database connection and claiming non-overlapping
batches via ``FOR UPDATE SKIP LOCKED``.

Usage::

    from flowforge_outbox_pg.pool import ActivityWorkerPool
    from flowforge_outbox_pg.worker import DrainWorker
    from flowforge_outbox_pg.registry import HandlerRegistry

    registry = HandlerRegistry()
    # ... register handlers ...

    async def conn_factory():
        return await asyncpg.connect(DATABASE_URL)

    pool = ActivityWorkerPool(
        n_workers=4,
        conn_factory=conn_factory,
        registry=registry,
        batch_size=16,
    )

    stop = asyncio.Event()
    await pool.run(stop_event=stop)

Each worker gets its own connection.  When ``stop_event`` is set all
workers finish their current batch and return gracefully.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .worker import DrainWorker, DrainWorkerHealth
from .registry import HandlerRegistry

_log = logging.getLogger(__name__)


@dataclass
class PoolHealth:
	"""Aggregate health across all workers in the pool."""

	n_workers: int
	workers: list[DrainWorkerHealth] = field(default_factory=list)

	@property
	def total_processed(self) -> int:
		return sum(w.total_dispatched for w in self.workers)

	@property
	def total_dead(self) -> int:
		return sum(w.total_dead for w in self.workers)

	@property
	def total_reconnects(self) -> int:
		return sum(w.reconnects for w in self.workers)

	@property
	def is_healthy(self) -> bool:
		return all(w.status != "error" for w in self.workers)


class ActivityWorkerPool:
	"""Concurrent outbox drain pool.

	Parameters
	----------
	n_workers:
		Number of parallel ``DrainWorker`` instances. Each holds its own
		database connection. Defaults to 4.
	conn_factory:
		Async callable that returns a new database connection for each
		worker. Called once per worker at startup.
	registry:
		Shared ``HandlerRegistry`` — all workers dispatch to the same
		handlers.
	backend:
		Forwarded to ``DrainWorker``.
	batch_size:
		Per-worker batch size. Effective throughput ≈ ``n_workers × batch_size``
		per drain cycle.
	poll_interval:
		Seconds each worker sleeps between drain cycles when the queue
		is empty.
	table:
		Outbox table name.
	max_retries:
		Forwarded to ``DrainWorker``.
	"""

	def __init__(
		self,
		n_workers: int = 4,
		*,
		conn_factory: Callable[[], Awaitable[Any]],
		registry: HandlerRegistry,
		backend: str = "default",
		batch_size: int = 16,
		poll_interval: float = 1.0,
		table: str = "outbox",
		max_retries: int = 5,
		dlq_after_seconds: int = 3600,
		lock_window_seconds: int = 60,
	) -> None:
		if n_workers < 1:
			raise ValueError(f"n_workers must be ≥ 1, got {n_workers}")
		self._n_workers = n_workers
		self._conn_factory = conn_factory
		self._registry = registry
		self._backend = backend
		self._batch_size = batch_size
		self._poll_interval = poll_interval
		self._table = table
		self._max_retries = max_retries
		self._dlq_after_seconds = dlq_after_seconds
		self._lock_window_seconds = lock_window_seconds
		self._workers: list[DrainWorker] = []
		self._started = False

	async def _start_workers(self) -> None:
		"""Create worker instances with fresh connections."""
		self._workers = []
		for i in range(self._n_workers):
			conn = await self._conn_factory()
			worker = DrainWorker(
				conn=conn,
				registry=self._registry,
				backend=self._backend,
				batch_size=self._batch_size,
				max_retries=self._max_retries,
				dlq_after_seconds=self._dlq_after_seconds,
				lock_window_seconds=self._lock_window_seconds,
				table=self._table,
				reconnect_factory=self._conn_factory,
			)
			self._workers.append(worker)
			_log.debug("ActivityWorkerPool: created worker %d/%d", i + 1, self._n_workers)
		self._started = True

	async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
		"""Start all workers and run until *stop_event* is set.

		If *stop_event* is ``None`` the pool runs until cancelled.
		All workers are started concurrently in an ``asyncio.TaskGroup``.
		Any worker that raises an exception causes the entire group to
		cancel (standard ``TaskGroup`` semantics).
		"""
		await self._start_workers()
		_log.info(
			"ActivityWorkerPool: starting %d workers (batch_size=%d poll_interval=%.1fs)",
			self._n_workers, self._batch_size, self._poll_interval,
		)

		async def _run_worker(worker: DrainWorker, worker_id: int) -> None:
			_log.debug("ActivityWorkerPool: worker %d starting", worker_id)
			await worker.run_loop(
				stop_event=stop_event,
				poll_interval=self._poll_interval,
			)
			_log.debug("ActivityWorkerPool: worker %d stopped", worker_id)

		async with asyncio.TaskGroup() as tg:
			for i, worker in enumerate(self._workers):
				tg.create_task(_run_worker(worker, i))

		_log.info("ActivityWorkerPool: all %d workers stopped", self._n_workers)

	async def run_once(self) -> int:
		"""Run a single drain cycle across all workers concurrently.

		Returns the total number of messages processed across all workers.
		Useful for testing and one-shot processing.
		"""
		if not self._started:
			await self._start_workers()

		tasks = [asyncio.create_task(w.run_once()) for w in self._workers]
		results = await asyncio.gather(*tasks, return_exceptions=True)
		total = 0
		for r in results:
			if isinstance(r, Exception):
				_log.error("ActivityWorkerPool: worker error in run_once: %s", r)
			elif hasattr(r, "processed"):
				total += r.processed
		return total

	def health(self) -> PoolHealth:
		"""Return aggregated health for all workers."""
		return PoolHealth(
			n_workers=self._n_workers,
			workers=[w.health() for w in self._workers],
		)

	@property
	def worker_count(self) -> int:
		return self._n_workers


__all__ = ["ActivityWorkerPool", "PoolHealth"]
