"""SLA breach detector and escalation runner.

Production hosts run :func:`check_sla_breaches` periodically (e.g.
every 60 seconds from a cron or APScheduler job).  It receives a list
of candidate ``(instance, wd)`` pairs from the host's persistence layer
and fires a synthetic ``sla_breach`` event on any instance whose active
state has an overdue SLA.

Usage::

    from flowforge.engine.sla_scheduler import check_sla_breaches, is_sla_breached

    breached = await check_sla_breaches(candidates, now=datetime.now(timezone.utc))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..dsl.workflow_def import WorkflowDef
from ..engine.fire import fire, FireResult, Instance
from .timers import elapsed_seconds

_log = logging.getLogger(__name__)


@dataclass
class SlaCandidate:
	"""An instance to check for SLA breach."""

	instance: Instance
	wd: WorkflowDef
	state_entered_at: datetime


@dataclass
class SlaBreachResult:
	"""Result of an SLA check for one instance."""

	instance_id: str
	state: str
	breach_seconds: int
	elapsed: int
	fired: bool
	fire_result: FireResult | None = None
	error: str | None = None


def is_sla_breached(
	candidate: SlaCandidate,
	now: datetime | None = None,
) -> tuple[bool, int]:
	"""Return ``(breached, elapsed_seconds)`` for *candidate*.

	A state is breached when it has an SLA with ``breach_seconds > 0`` and
	the elapsed time since ``state_entered_at`` exceeds that threshold.
	"""
	now = now or datetime.now(timezone.utc)
	state_def = next(
		(s for s in candidate.wd.states if s.name == candidate.instance.state), None
	)
	if state_def is None or state_def.sla is None:
		return False, 0
	breach_s = state_def.sla.breach_seconds
	if not breach_s or breach_s <= 0:
		return False, 0
	elapsed = elapsed_seconds(candidate.state_entered_at, now)
	return elapsed >= breach_s, elapsed


async def check_sla_breaches(
	candidates: list[SlaCandidate],
	*,
	now: datetime | None = None,
	tenant_id: str = "default",
	principal: Any = None,
	dispatch_ports: bool = True,
) -> list[SlaBreachResult]:
	"""Check candidates for SLA breach and fire ``sla_breach`` events.

	Returns one :class:`SlaBreachResult` per breached instance. Non-breached
	candidates are silently skipped.

	Args:
		candidates: Instances to evaluate. The host queries its persistence
		            layer for instances in SLA-bearing states.
		now: Timestamp to use for elapsed calculation. Defaults to UTC now.
		tenant_id: Tenant scope for the synthetic fire() calls.
		principal: Principal for audit attribution. ``None`` → system.
		dispatch_ports: Forwarded to :func:`fire`.
	"""
	now = now or datetime.now(timezone.utc)
	results: list[SlaBreachResult] = []

	for candidate in candidates:
		breached, elapsed = is_sla_breached(candidate, now=now)
		if not breached:
			continue

		state_def = next(
			(s for s in candidate.wd.states if s.name == candidate.instance.state), None
		)
		assert state_def is not None and state_def.sla is not None
		breach_s = state_def.sla.breach_seconds
		assert breach_s is not None

		try:
			result = await fire(
				candidate.wd,
				candidate.instance,
				"sla_breach",
				payload={"elapsed_seconds": elapsed, "breach_seconds": breach_s},
				tenant_id=tenant_id,
				principal=principal,
				dispatch_ports=dispatch_ports,
			)
			_log.info(
				"SLA breach fired on instance %r (state=%r elapsed=%ds breach=%ds)",
				candidate.instance.id, candidate.instance.state, elapsed, breach_s,
			)
			results.append(SlaBreachResult(
				instance_id=candidate.instance.id,
				state=candidate.instance.state,
				breach_seconds=breach_s,
				elapsed=elapsed,
				fired=True,
				fire_result=result,
			))
		except Exception as exc:
			_log.error(
				"SLA breach fire failed for instance %r: %s",
				candidate.instance.id, exc, exc_info=True,
			)
			results.append(SlaBreachResult(
				instance_id=candidate.instance.id,
				state=candidate.instance.state,
				breach_seconds=breach_s,
				elapsed=elapsed,
				fired=False,
				error=str(exc),
			))

	return results
