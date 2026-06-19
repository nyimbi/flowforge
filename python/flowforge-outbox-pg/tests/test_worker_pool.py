"""Tests for ActivityWorkerPool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flowforge_outbox_pg.pool import ActivityWorkerPool, PoolHealth
from flowforge_outbox_pg.registry import HandlerRegistry
from flowforge_outbox_pg.worker import DrainWorkerHealth


def _registry() -> HandlerRegistry:
	r = HandlerRegistry()
	return r


async def _noop_conn():
	return MagicMock()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_pool_defaults():
	pool = ActivityWorkerPool(conn_factory=_noop_conn, registry=_registry())
	assert pool._n_workers == 4
	assert pool._batch_size == 16
	assert pool._poll_interval == 1.0
	assert pool._table == "outbox"
	assert pool._max_retries == 5
	assert not pool._started


def test_pool_rejects_zero_workers():
	with pytest.raises(ValueError, match="n_workers"):
		ActivityWorkerPool(n_workers=0, conn_factory=_noop_conn, registry=_registry())


def test_pool_worker_count_property():
	pool = ActivityWorkerPool(n_workers=3, conn_factory=_noop_conn, registry=_registry())
	assert pool.worker_count == 3


# ---------------------------------------------------------------------------
# Health before start
# ---------------------------------------------------------------------------

def test_pool_health_before_start():
	pool = ActivityWorkerPool(n_workers=2, conn_factory=_noop_conn, registry=_registry())
	health = pool.health()
	assert isinstance(health, PoolHealth)
	assert health.n_workers == 2
	assert health.workers == []


# ---------------------------------------------------------------------------
# PoolHealth aggregation
# ---------------------------------------------------------------------------

def _mock_worker_health(dispatched=0, dead=0, reconnects=0, status="idle") -> DrainWorkerHealth:
	from flowforge_outbox_pg.worker import DrainResult
	return DrainWorkerHealth(
		status=status,
		last_run_at=None,
		last_error=None,
		reconnects=reconnects,
		run_errors=0,
		total_dispatched=dispatched,
		total_retried=0,
		total_dead=dead,
		total_no_handler=0,
		last_result=DrainResult(),
	)


def test_pool_health_aggregation():
	ph = PoolHealth(
		n_workers=2,
		workers=[
			_mock_worker_health(dispatched=10, dead=1, reconnects=2),
			_mock_worker_health(dispatched=20, dead=3, reconnects=0),
		],
	)
	assert ph.total_processed == 30
	assert ph.total_dead == 4
	assert ph.total_reconnects == 2
	assert ph.is_healthy is True


def test_pool_health_unhealthy_if_any_worker_unhealthy():
	ph = PoolHealth(
		n_workers=2,
		workers=[
			_mock_worker_health(status="idle"),
			_mock_worker_health(status="error"),
		],
	)
	assert ph.is_healthy is False


def test_pool_health_empty_workers():
	ph = PoolHealth(n_workers=0, workers=[])
	assert ph.total_processed == 0
	assert ph.total_dead == 0
	assert ph.total_reconnects == 0
	assert ph.is_healthy is True  # vacuously true


# ---------------------------------------------------------------------------
# run_once — mock DrainWorker
# ---------------------------------------------------------------------------

async def test_run_once_starts_workers_and_drains():
	conn = MagicMock()
	call_count = 0

	async def conn_factory():
		nonlocal call_count
		call_count += 1
		return conn

	pool = ActivityWorkerPool(n_workers=2, conn_factory=conn_factory, registry=_registry())

	mock_result = MagicMock()
	mock_result.processed = 5

	with patch("flowforge_outbox_pg.pool.DrainWorker") as MockWorker:
		instance = AsyncMock()
		instance.run_once = AsyncMock(return_value=mock_result)
		instance.health = MagicMock(return_value=_mock_worker_health(dispatched=5))
		MockWorker.return_value = instance

		total = await pool.run_once()

	assert total == 10  # 2 workers × 5 each
	assert call_count == 2  # one conn per worker


async def test_run_once_skips_start_if_already_started():
	pool = ActivityWorkerPool(n_workers=1, conn_factory=_noop_conn, registry=_registry())
	pool._started = True

	mock_result = MagicMock()
	mock_result.processed = 3
	mock_worker = AsyncMock()
	mock_worker.run_once = AsyncMock(return_value=mock_result)
	pool._workers = [mock_worker]

	total = await pool.run_once()
	assert total == 3


async def test_run_once_handles_worker_exception():
	pool = ActivityWorkerPool(n_workers=2, conn_factory=_noop_conn, registry=_registry())
	pool._started = True

	good_result = MagicMock()
	good_result.processed = 7

	good_worker = AsyncMock()
	good_worker.run_once = AsyncMock(return_value=good_result)

	bad_worker = AsyncMock()
	bad_worker.run_once = AsyncMock(side_effect=RuntimeError("db gone"))

	pool._workers = [good_worker, bad_worker]
	total = await pool.run_once()
	# Only counts good worker; bad one logged but not raised
	assert total == 7


# ---------------------------------------------------------------------------
# run() — integration smoke (stop immediately)
# ---------------------------------------------------------------------------

async def test_run_stops_on_event():
	stop = asyncio.Event()
	stop.set()  # already set — workers should exit immediately

	call_count = 0

	async def conn_factory():
		nonlocal call_count
		call_count += 1
		return MagicMock()

	pool = ActivityWorkerPool(n_workers=2, conn_factory=conn_factory, registry=_registry())

	async def fast_run_loop(*, stop_event=None, poll_interval=1.0):
		# Simulates a worker that checks stop immediately
		return

	with patch("flowforge_outbox_pg.pool.DrainWorker") as MockWorker:
		instance = MagicMock()
		instance.run_loop = AsyncMock(side_effect=fast_run_loop)
		instance.health = MagicMock(return_value=_mock_worker_health(status="idle"))
		MockWorker.return_value = instance

		await pool.run(stop_event=stop)

	assert call_count == 2  # 2 workers started
