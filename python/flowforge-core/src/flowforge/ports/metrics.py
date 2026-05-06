"""MetricsPort — minimal emit-only metrics surface.

E-10 adds ``jtbd_id`` and ``jtbd_version`` to the standard label set so
dashboards can group per-JTBD instance volume, cycle time, and SLA breach
rate (see ``framework/docs/jtbd-editor-arch.md`` §6.2).
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable


#: Canonical label names emitted by the engine for every workflow event.
#: Hosts may add additional labels; removing names from this set is a
#: breaking change (requires a major version bump per portability §9.1).
STANDARD_LABEL_NAMES: tuple[str, ...] = (
	"tenant_id",
	"def_key",
	"state",
	"jtbd_id",      # originating JTBD spec id (None → empty string)
	"jtbd_version", # originating JTBD version  (None → empty string)
)


@runtime_checkable
class MetricsPort(Protocol):
	"""Emit a numeric metric.

	Standard labels (E-10): ``{tenant_id, def_key, state, jtbd_id,
	jtbd_version}``.  ``jtbd_id`` / ``jtbd_version`` are empty strings
	when the workflow was not spawned from a JTBD bundle.  Hosts may wrap
	to relabel for Datadog / Prometheus / etc.

	See :data:`STANDARD_LABEL_NAMES` for the canonical label set.
	"""

	def emit(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
		"""Emit metric *name* = *value* with optional labels."""
