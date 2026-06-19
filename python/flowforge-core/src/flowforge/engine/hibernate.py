"""Multi-year workflow checkpointing via hibernation.

A ``hibernate`` state suspends a workflow instance for an extended
period (minutes to years) without holding locks or consuming memory.
The instance is serialised to the snapshot store and only woken by
an explicit trigger — either a scheduled ``WakeScheduler`` job, an
external event, or a manual operator action.

Architecture
------------
1. Engine enters ``hibernate`` state → calls :func:`begin_hibernate`.
2. Host persists the instance and records ``woken_at = now + hibernate_seconds``
   (if ``hibernate_seconds > 0``).
3. :class:`WakeScheduler` runs periodically (e.g. hourly) and calls
   :func:`check_hibernations` with candidates whose ``woken_at`` is past.
4. For each due instance, ``check_hibernations`` fires the ``wake`` event
   which transitions the instance out of ``hibernate`` to the next state.

History compaction
------------------
Long-running instances accumulate unbounded ``instance.history`` lists.
Call :func:`compact_history` after a wake to collapse older entries
into a summary snapshot, keeping the last N entries verbatim.

Usage::

    from flowforge.engine.hibernate import begin_hibernate, WakeScheduler, compact_history

    # On entering hibernate state:
    begin_hibernate(instance, state_def, now=datetime.now(timezone.utc))

    # Periodic scheduler:
    scheduler = WakeScheduler()
    results = await scheduler.check_hibernations(candidates, now=now)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..dsl.workflow_def import State, WorkflowDef
from ..engine.fire import Instance, FireResult, fire

_log = logging.getLogger(__name__)

_HIBERNATE_KEY = "__hibernate__"
_HISTORY_COMPACT_THRESHOLD = 100
_HISTORY_KEEP_TAIL = 20


class HibernationError(RuntimeError):
	"""Raised when hibernate state is invalid."""


@dataclass
class HibernationRecord:
	"""Metadata stored in ``instance.context["__hibernate__"]``."""

	entered_at: datetime
	wake_at: datetime | None
	hibernate_seconds: int
	wake_count: int = 0

	def to_dict(self) -> dict[str, Any]:
		return {
			"entered_at": self.entered_at.isoformat(),
			"wake_at": self.wake_at.isoformat() if self.wake_at else None,
			"hibernate_seconds": self.hibernate_seconds,
			"wake_count": self.wake_count,
		}

	@classmethod
	def from_dict(cls, d: dict[str, Any]) -> "HibernationRecord":
		return cls(
			entered_at=datetime.fromisoformat(d["entered_at"]),
			wake_at=datetime.fromisoformat(d["wake_at"]) if d.get("wake_at") else None,
			hibernate_seconds=d.get("hibernate_seconds", 0),
			wake_count=d.get("wake_count", 0),
		)


def begin_hibernate(
	instance: Instance,
	state_def: State,
	*,
	now: datetime | None = None,
) -> HibernationRecord:
	"""Mark *instance* as hibernating and record wake metadata.

	Writes ``instance.context["__hibernate__"]`` and appends a
	``"hibernate:entered"`` marker to ``instance.history``.

	Args:
		instance: The workflow instance (mutated in place).
		state_def: The ``hibernate`` state definition.
		now: Override for current UTC time (testing).

	Returns:
		The :class:`HibernationRecord` written to context.
	"""
	now = now or datetime.now(timezone.utc)
	seconds = state_def.hibernate_seconds or 0
	wake_at = (now + timedelta(seconds=seconds)) if seconds > 0 else None

	record = HibernationRecord(
		entered_at=now,
		wake_at=wake_at,
		hibernate_seconds=seconds,
	)
	instance.context[_HIBERNATE_KEY] = record.to_dict()
	instance.history.append(
		f"hibernate:entered:{now.isoformat()}"
		+ (f":wake_at:{wake_at.isoformat()}" if wake_at else "")
	)
	_log.info(
		"begin_hibernate: instance=%r state=%r hibernate_seconds=%d wake_at=%s",
		instance.id, state_def.name, seconds, wake_at,
	)
	return record


def is_due_for_wake(instance: Instance, *, now: datetime | None = None) -> bool:
	"""Return True if the hibernating instance's scheduled wake time has passed."""
	now = now or datetime.now(timezone.utc)
	raw = instance.context.get(_HIBERNATE_KEY)
	if not raw:
		return False
	record = HibernationRecord.from_dict(raw)
	if record.wake_at is None:
		return False
	return now >= record.wake_at


def compact_history(instance: Instance, *, keep: int = _HISTORY_KEEP_TAIL) -> int:
	"""Compact ``instance.history`` for long-running instances.

	Collapses all but the last *keep* entries into a single summary
	line.  Returns the number of entries removed.

	This prevents the history list from growing without bound in
	instances that wake/hibernate repeatedly over months or years.
	"""
	n = len(instance.history)
	if n <= _HISTORY_COMPACT_THRESHOLD:
		return 0
	compacted = n - keep
	summary = f"[compacted {compacted} earlier entries]"
	instance.history = [summary] + instance.history[-keep:]
	_log.debug("compact_history: instance=%r removed %d entries", instance.id, compacted)
	return compacted


@dataclass
class HibernationCandidate:
	"""A candidate instance to check for scheduled wake."""

	instance: Instance
	wd: WorkflowDef


@dataclass
class WakeResult:
	"""Result of attempting to wake one hibernating instance."""

	instance_id: str
	state: str
	fired: bool
	fire_result: FireResult | None = None
	error: str | None = None


class WakeScheduler:
	"""Periodic scheduler that fires ``wake`` events on due instances.

	Production hosts run :meth:`check_hibernations` from an APScheduler
	or cron job every 60–3600 seconds depending on required precision.
	"""

	async def check_hibernations(
		self,
		candidates: list[HibernationCandidate],
		*,
		now: datetime | None = None,
		tenant_id: str = "default",
		principal: Any = None,
		dispatch_ports: bool = True,
	) -> list[WakeResult]:
		"""Check candidates and fire ``wake`` on any due instances.

		Args:
			candidates: Instances the host loaded from its persistence
			            layer (filter by ``state_kind = 'hibernate'``).
			now: Current UTC time override (testing).
			tenant_id: Tenant scope for fire() calls.
			principal: Actor for audit attribution.
			dispatch_ports: Forwarded to fire().

		Returns:
			List of :class:`WakeResult` for every instance that was
			due for wake.  Non-due candidates are silently skipped.
		"""
		now = now or datetime.now(timezone.utc)
		results: list[WakeResult] = []

		for cand in candidates:
			if not is_due_for_wake(cand.instance, now=now):
				continue

			try:
				result = await fire(
					cand.wd,
					cand.instance,
					"wake",
					payload={"woken_at": now.isoformat()},
					tenant_id=tenant_id,
					principal=principal,
					dispatch_ports=dispatch_ports,
				)
				# Compact history on successful wake
				compact_history(cand.instance)
				_log.info(
					"WakeScheduler: woke instance=%r (state=%r → %r)",
					cand.instance.id, cand.instance.state, result.new_state,
				)
				results.append(WakeResult(
					instance_id=cand.instance.id,
					state=cand.instance.state,
					fired=True,
					fire_result=result,
				))
			except Exception as exc:
				_log.error(
					"WakeScheduler: wake fire failed for instance=%r: %s",
					cand.instance.id, exc, exc_info=True,
				)
				results.append(WakeResult(
					instance_id=cand.instance.id,
					state=cand.instance.state,
					fired=False,
					error=str(exc),
				))

		return results


__all__ = [
	"HibernationCandidate",
	"HibernationError",
	"HibernationRecord",
	"WakeResult",
	"WakeScheduler",
	"begin_hibernate",
	"compact_history",
	"is_due_for_wake",
]
