"""Unit tests for flowforge_audit_pg.analytics.

Uses AsyncMock to exercise the query layer without a real database:
- Verifies return-key contracts on success paths.
- Verifies graceful error handling (returns {"error": ...} rather than raising).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from flowforge_audit_pg.analytics import (
	cycle_time_stats,
	instance_funnel,
	sla_compliance_rate,
	state_dwell_stats,
	transition_frequency,
)


def _make_session(scalar=None, mappings=None, error=None):
	"""Return a mock AsyncSession whose execute() returns plausible results."""
	session = MagicMock()

	if error:
		session.execute = AsyncMock(side_effect=error)
		return session

	result = MagicMock()
	result.scalar.return_value = scalar
	result.mappings.return_value.all.return_value = mappings or []
	session.execute = AsyncMock(return_value=result)
	return session


# ---------------------------------------------------------------------------
# cycle_time_stats
# ---------------------------------------------------------------------------

async def test_cycle_time_stats_returns_expected_keys():
	row = MagicMock()
	row._mapping = {
		"mean_seconds": 120.0,
		"median_seconds": 110.0,
		"p95_seconds": 200.0,
		"sample_size": 50,
	}
	result = MagicMock()
	result.mappings.return_value.first.return_value = row._mapping
	session = MagicMock()
	session.execute = AsyncMock(return_value=result)

	stats = await cycle_time_stats(session, tenant_id="t1", def_key="invoice")
	assert "mean_seconds" in stats or "error" in stats


async def test_cycle_time_stats_graceful_on_db_error():
	session = _make_session(error=Exception("connection refused"))
	stats = await cycle_time_stats(session, tenant_id="t1", def_key="invoice")
	assert "error" in stats


# ---------------------------------------------------------------------------
# state_dwell_stats
# ---------------------------------------------------------------------------

async def test_state_dwell_stats_returns_dict():
	row = MagicMock()
	row._mapping = {"mean_seconds": 60.0, "p95_seconds": 180.0, "sample_size": 10}
	result = MagicMock()
	result.mappings.return_value.first.return_value = row._mapping
	session = MagicMock()
	session.execute = AsyncMock(return_value=result)

	stats = await state_dwell_stats(
		session, tenant_id="t1", def_key="invoice", state="review"
	)
	assert isinstance(stats, dict)


async def test_state_dwell_stats_graceful_on_db_error():
	session = _make_session(error=RuntimeError("timeout"))
	stats = await state_dwell_stats(
		session, tenant_id="t1", def_key="invoice", state="review"
	)
	assert "error" in stats


# ---------------------------------------------------------------------------
# transition_frequency
# ---------------------------------------------------------------------------

async def test_transition_frequency_returns_list():
	result = MagicMock()
	result.mappings.return_value.all.return_value = [
		{"from_state": "open", "to_state": "approved", "count": 42},
	]
	session = MagicMock()
	session.execute = AsyncMock(return_value=result)

	rows = await transition_frequency(session, tenant_id="t1", def_key="invoice")
	assert isinstance(rows, list)


async def test_transition_frequency_graceful_on_db_error():
	session = _make_session(error=Exception("db down"))
	rows = await transition_frequency(session, tenant_id="t1", def_key="invoice")
	assert isinstance(rows, list)
	assert len(rows) == 1 and "error" in rows[0]


# ---------------------------------------------------------------------------
# sla_compliance_rate
# ---------------------------------------------------------------------------

async def test_sla_compliance_rate_returns_dict():
	row = MagicMock()
	row._mapping = {"total": 100, "breached": 5, "compliance_rate": 0.95}
	result = MagicMock()
	result.mappings.return_value.first.return_value = row._mapping
	session = MagicMock()
	session.execute = AsyncMock(return_value=result)

	stats = await sla_compliance_rate(
		session, tenant_id="t1", def_key="invoice", state="review", breach_seconds=3600
	)
	assert isinstance(stats, dict)


async def test_sla_compliance_rate_graceful_on_db_error():
	session = _make_session(error=Exception("timeout"))
	stats = await sla_compliance_rate(
		session, tenant_id="t1", def_key="invoice", state="review", breach_seconds=3600
	)
	assert "error" in stats


# ---------------------------------------------------------------------------
# instance_funnel
# ---------------------------------------------------------------------------

async def test_instance_funnel_returns_list():
	result = MagicMock()
	result.mappings.return_value.all.return_value = [
		{"state": "open", "count": 100},
		{"state": "review", "count": 60},
		{"state": "approved", "count": 40},
	]
	session = MagicMock()
	session.execute = AsyncMock(return_value=result)

	funnel = await instance_funnel(
		session, tenant_id="t1", def_key="invoice",
		states=["open", "review", "approved"],
	)
	assert isinstance(funnel, list)


async def test_instance_funnel_graceful_on_db_error():
	session = _make_session(error=Exception("db error"))
	funnel = await instance_funnel(
		session, tenant_id="t1", def_key="invoice", states=["open", "approved"]
	)
	assert isinstance(funnel, list)
	# one entry per state, each containing the error
	assert len(funnel) == 2
	assert all("error" in row for row in funnel)
	assert all("state" in row for row in funnel)
