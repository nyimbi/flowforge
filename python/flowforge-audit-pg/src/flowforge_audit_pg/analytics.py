"""Process analytics query layer.

Functions in this module query the audit log and workflow instance tables
to produce process metrics: cycle time, state dwell time, transition
frequency, SLA compliance rate, and instance funnel.

All functions accept a SQLAlchemy ``AsyncSession`` and a ``tenant_id``
scope. They return plain dicts / lists for easy JSON serialisation — no
Pydantic dependencies in this module.

Usage::

    from flowforge_audit_pg.analytics import (
        cycle_time_stats,
        state_dwell_stats,
        transition_frequency,
        sla_compliance_rate,
        instance_funnel,
    )

    stats = await cycle_time_stats(session, tenant_id="acme", def_key="invoice_approval")
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)


async def cycle_time_stats(
	session: AsyncSession,
	tenant_id: str,
	def_key: str,
	*,
	since: datetime | None = None,
	limit: int = 1000,
) -> dict[str, Any]:
	"""Return mean/median/p95 cycle time (seconds) for completed instances.

	'Cycle time' = time from first event to terminal event for instances
	that have reached a terminal state.
	"""
	since_clause = "AND e.created_at >= :since" if since else ""
	sql = text(f"""
		WITH first_last AS (
			SELECT
				e.subject_id,
				MIN(e.created_at) AS started_at,
				MAX(e.created_at) AS ended_at
			FROM audit_events e
			WHERE e.tenant_id = :tenant_id
			  AND e.kind LIKE :def_key_prefix
			  {since_clause}
			GROUP BY e.subject_id
		),
		durations AS (
			SELECT
				EXTRACT(EPOCH FROM (fl.ended_at - fl.started_at))::bigint AS duration_seconds
			FROM first_last fl
			JOIN workflow_instances wi
			  ON wi.id = fl.subject_id AND wi.tenant_id = :tenant_id
			WHERE wi.state LIKE 'terminal_%'
			LIMIT :lim
		)
		SELECT
			COUNT(*) AS instance_count,
			AVG(duration_seconds)::bigint AS mean_seconds,
			PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds)::bigint AS median_seconds,
			PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_seconds)::bigint AS p95_seconds,
			MIN(duration_seconds) AS min_seconds,
			MAX(duration_seconds) AS max_seconds
		FROM durations
	""")
	params: dict[str, Any] = {
		"tenant_id": tenant_id,
		"def_key_prefix": f"wf.{def_key}.%",
		"lim": limit,
	}
	if since:
		params["since"] = since
	try:
		result = await session.execute(sql, params)
		row = result.fetchone()
		if row is None:
			return {"instance_count": 0}
		return {
			"instance_count": row.instance_count or 0,
			"mean_seconds": row.mean_seconds,
			"median_seconds": row.median_seconds,
			"p95_seconds": row.p95_seconds,
			"min_seconds": row.min_seconds,
			"max_seconds": row.max_seconds,
		}
	except Exception as exc:
		_log.error("cycle_time_stats failed: %s", exc)
		return {"error": str(exc)}


async def state_dwell_stats(
	session: AsyncSession,
	tenant_id: str,
	def_key: str,
	state: str,
	*,
	since: datetime | None = None,
	limit: int = 5000,
) -> dict[str, Any]:
	"""Return mean/p95 dwell time in *state* (seconds).

	Computed from consecutive ``transitioned`` audit events:
	dwell = time from entering *state* to leaving *state*.
	"""
	since_clause = "AND entered.created_at >= :since" if since else ""
	sql = text(f"""
		WITH entered AS (
			SELECT subject_id, created_at AS entered_at
			FROM audit_events
			WHERE tenant_id = :tenant_id
			  AND kind = :transitioned_kind
			  AND payload->>'to_state' = :state
			  {since_clause}
		),
		left_state AS (
			SELECT subject_id, MIN(created_at) AS left_at
			FROM audit_events
			WHERE tenant_id = :tenant_id
			  AND kind = :transitioned_kind
			  AND payload->>'from_state' = :state
			GROUP BY subject_id
		),
		dwells AS (
			SELECT EXTRACT(EPOCH FROM (ls.left_at - en.entered_at))::bigint AS dwell_s
			FROM entered en
			JOIN left_state ls ON ls.subject_id = en.subject_id AND ls.left_at > en.entered_at
			LIMIT :lim
		)
		SELECT
			COUNT(*) AS instance_count,
			AVG(dwell_s)::bigint AS mean_seconds,
			PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY dwell_s)::bigint AS p95_seconds
		FROM dwells
	""")
	params: dict[str, Any] = {
		"tenant_id": tenant_id,
		"transitioned_kind": f"wf.{def_key}.transitioned",
		"state": state,
		"lim": limit,
	}
	if since:
		params["since"] = since
	try:
		result = await session.execute(sql, params)
		row = result.fetchone()
		if row is None:
			return {"instance_count": 0, "state": state}
		return {
			"state": state,
			"instance_count": row.instance_count or 0,
			"mean_seconds": row.mean_seconds,
			"p95_seconds": row.p95_seconds,
		}
	except Exception as exc:
		_log.error("state_dwell_stats failed: %s", exc)
		return {"state": state, "error": str(exc)}


async def transition_frequency(
	session: AsyncSession,
	tenant_id: str,
	def_key: str,
	*,
	since: datetime | None = None,
	limit: int = 50,
) -> list[dict[str, Any]]:
	"""Return transition counts grouped by (from_state, to_state, event)."""
	since_clause = "AND created_at >= :since" if since else ""
	sql = text(f"""
		SELECT
			payload->>'from_state' AS from_state,
			payload->>'to_state' AS to_state,
			payload->>'event' AS event,
			COUNT(*) AS count
		FROM audit_events
		WHERE tenant_id = :tenant_id
		  AND kind = :transitioned_kind
		  {since_clause}
		GROUP BY 1, 2, 3
		ORDER BY count DESC
		LIMIT :lim
	""")
	params: dict[str, Any] = {
		"tenant_id": tenant_id,
		"transitioned_kind": f"wf.{def_key}.transitioned",
		"lim": limit,
	}
	if since:
		params["since"] = since
	try:
		result = await session.execute(sql, params)
		return [
			{
				"from_state": row.from_state,
				"to_state": row.to_state,
				"event": row.event,
				"count": row.count,
			}
			for row in result.fetchall()
		]
	except Exception as exc:
		_log.error("transition_frequency failed: %s", exc)
		return [{"error": str(exc)}]


async def sla_compliance_rate(
	session: AsyncSession,
	tenant_id: str,
	def_key: str,
	state: str,
	breach_seconds: int,
	*,
	since: datetime | None = None,
) -> dict[str, Any]:
	"""Return the SLA compliance rate (fraction that did NOT breach)."""
	since_clause = "AND entered.created_at >= :since" if since else ""
	sql = text(f"""
		WITH entered AS (
			SELECT subject_id, created_at AS entered_at
			FROM audit_events
			WHERE tenant_id = :tenant_id
			  AND kind = :transitioned_kind
			  AND payload->>'to_state' = :state
			  {since_clause}
		),
		left_state AS (
			SELECT subject_id, MIN(created_at) AS left_at
			FROM audit_events
			WHERE tenant_id = :tenant_id
			  AND kind = :transitioned_kind
			  AND payload->>'from_state' = :state
			GROUP BY subject_id
		),
		dwells AS (
			SELECT
				EXTRACT(EPOCH FROM (ls.left_at - en.entered_at))::bigint AS dwell_s
			FROM entered en
			JOIN left_state ls ON ls.subject_id = en.subject_id AND ls.left_at > en.entered_at
		)
		SELECT
			COUNT(*) AS total,
			SUM(CASE WHEN dwell_s <= :breach_s THEN 1 ELSE 0 END) AS compliant
		FROM dwells
	""")
	params: dict[str, Any] = {
		"tenant_id": tenant_id,
		"transitioned_kind": f"wf.{def_key}.transitioned",
		"state": state,
		"breach_s": breach_seconds,
	}
	if since:
		params["since"] = since
	try:
		result = await session.execute(sql, params)
		row = result.fetchone()
		if row is None or not row.total:
			return {"state": state, "total": 0, "compliant": 0, "compliance_rate": None}
		rate = round(row.compliant / row.total, 4) if row.total else None
		return {
			"state": state,
			"breach_seconds": breach_seconds,
			"total": row.total,
			"compliant": row.compliant,
			"breached": row.total - row.compliant,
			"compliance_rate": rate,
		}
	except Exception as exc:
		_log.error("sla_compliance_rate failed: %s", exc)
		return {"state": state, "error": str(exc)}


async def instance_funnel(
	session: AsyncSession,
	tenant_id: str,
	def_key: str,
	states: list[str],
	*,
	since: datetime | None = None,
) -> list[dict[str, Any]]:
	"""Return count of instances that ever reached each state in *states*.

	Used to build a funnel chart: what fraction of instances reached each
	stage of the workflow.
	"""
	since_clause = "AND created_at >= :since" if since else ""
	rows = []
	for state in states:
		sql = text(f"""
			SELECT COUNT(DISTINCT subject_id) AS count
			FROM audit_events
			WHERE tenant_id = :tenant_id
			  AND kind = :transitioned_kind
			  AND payload->>'to_state' = :state
			  {since_clause}
		""")
		params: dict[str, Any] = {
			"tenant_id": tenant_id,
			"transitioned_kind": f"wf.{def_key}.transitioned",
			"state": state,
		}
		if since:
			params["since"] = since
		try:
			result = await session.execute(sql, params)
			row_result = result.fetchone()
			rows.append({"state": state, "count": row_result.count if row_result else 0})
		except Exception as exc:
			_log.error("instance_funnel failed for state %r: %s", state, exc)
			rows.append({"state": state, "error": str(exc)})
	return rows
