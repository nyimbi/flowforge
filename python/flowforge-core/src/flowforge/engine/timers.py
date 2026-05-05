"""Pause-aware timers.

A timer is a tuple ``(instance_id, event, fire_at)``. The simulator uses
:func:`elapsed_seconds` to compute SLA percentages; production hosts wire
this to the existing scheduler infrastructure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def elapsed_seconds(started_at: datetime, now: datetime | None = None) -> int:
	now = now or datetime.now(timezone.utc)
	return int((now - started_at).total_seconds())


def sla_percent(started_at: datetime, breach_seconds: int, now: datetime | None = None) -> int:
	if breach_seconds <= 0:
		return 0
	pct = int((elapsed_seconds(started_at, now) / breach_seconds) * 100)
	return max(0, min(pct, 100))


def fire_at(started_at: datetime, breach_seconds: int) -> datetime:
	return started_at + timedelta(seconds=breach_seconds)
