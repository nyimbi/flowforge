"""MetricsPort — minimal emit-only metrics surface.

E-10 adds ``jtbd_id`` and ``jtbd_version`` to the standard label set so
dashboards can group per-JTBD instance volume, cycle time, and SLA breach
rate (see ``framework/docs/jtbd-editor-arch.md`` §6.2).

v0.3.0 W2 / item 12 extends the port with OTel-compatible histogram
naming. The histogram protocol :class:`HistogramMetricsPort` is an
*additive* extension — it inherits :class:`MetricsPort` and adds
``record_histogram``. Hosts that already implement :class:`MetricsPort`
keep working untouched; hosts wanting per-fire latency histograms (the
default ``flowforge-otel`` adapter does) implement the extension. The
in-memory fake :class:`flowforge.testing.port_fakes.InMemoryMetrics`
implements both Protocols so tests stay one-stop.
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


#: OTel-compatible histogram name for engine-fire latency. Generated
#: adapter code records one observation per ``fire`` call; PromQL alert
#: rules under ``tests/observability/promql/`` ratchet against this
#: exact name.
FIRE_DURATION_HISTOGRAM: str = "flowforge.fire.duration_seconds"


#: OTel-compatible histogram name for outbox-dispatch latency.
OUTBOX_DISPATCH_DURATION_HISTOGRAM: str = "flowforge.outbox.dispatch.duration_seconds"


#: OTel-compatible histogram name for audit-append latency.
AUDIT_APPEND_DURATION_HISTOGRAM: str = "flowforge.audit.append.duration_seconds"


#: All emit-side OTel-compatible histogram names declared by flowforge-core.
STANDARD_HISTOGRAM_NAMES: tuple[str, ...] = (
	FIRE_DURATION_HISTOGRAM,
	OUTBOX_DISPATCH_DURATION_HISTOGRAM,
	AUDIT_APPEND_DURATION_HISTOGRAM,
)


def default_fire_duration_buckets(sla_breach_seconds: float) -> tuple[float, ...]:
	"""Recommended bucket edges for the fire-duration histogram.

	Buckets are rounded into a deterministic float-stable tuple so
	regen + dashboards stay byte-stable across runs.

	Standard buckets (regardless of SLA): 0.1s, 1s, 10s, 60s, 600s
	(matches the OTel ``http.server.duration`` shape but stretched out
	to workflow-fire scale where 60s+ is normal). On top of those,
	three SLA-relative buckets land at ``0.5×``, ``1×``, ``2×`` of
	``sla_breach_seconds`` so the alert rule
	``flowforge_fire_duration_seconds_bucket{le="<sla>"}`` sees a clean
	cutoff at the configured budget.

	The function is total — a missing/zero/non-positive
	``sla_breach_seconds`` returns just the standard buckets.
	"""

	assert isinstance(sla_breach_seconds, (int, float)), \
		"sla_breach_seconds must be numeric"
	standard = (0.1, 1.0, 10.0, 60.0, 600.0)
	if sla_breach_seconds is None or sla_breach_seconds <= 0:
		return standard
	sla = float(sla_breach_seconds)
	sla_buckets = (sla * 0.5, sla, sla * 2.0)
	# Sort + dedupe (e.g. sla=0.2 collides with the 0.1 bucket only at
	# half-bucket; collisions are exact only when sla∈{0.2, 1, 10, 60,
	# 300, 600, 1200}; dedupe defends against either pre-existing or
	# post-merge equal floats).
	merged = tuple(sorted(set(standard + sla_buckets)))
	return merged


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


@runtime_checkable
class HistogramMetricsPort(MetricsPort, Protocol):
	"""Optional extension: record a histogram observation.

	Adapters wishing to participate in the OTel-compatible histogram
	contract (e.g. ``flowforge-otel``) implement this Protocol on top of
	:class:`MetricsPort`. Generated code that needs a histogram falls
	back to :meth:`MetricsPort.emit` when the configured port doesn't
	expose ``record_histogram`` — so adopting the histogram adapter is
	host-side opt-in without breaking pre-existing wrappers.
	"""

	def record_histogram(
		self,
		name: str,
		value: float,
		labels: Mapping[str, str] | None = None,
	) -> None:
		"""Record observation *value* into histogram *name*.

		``name`` SHOULD be one of :data:`STANDARD_HISTOGRAM_NAMES`.
		"""
