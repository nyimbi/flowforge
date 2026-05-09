"""OTel-backed implementation of :class:`flowforge.ports.metrics.HistogramMetricsPort`.

Maintains an instrument cache so a single histogram name maps to one
``opentelemetry.metrics.Histogram`` regardless of how many call sites
record observations. Counter emits go through ``record_counter`` (the
classic :meth:`MetricsPort.emit` surface) and route into an
``opentelemetry.metrics.Counter`` similarly cached.
"""

from __future__ import annotations

from typing import Any, Mapping

from flowforge.ports.metrics import (
	FIRE_DURATION_HISTOGRAM,
	STANDARD_HISTOGRAM_NAMES,
	default_fire_duration_buckets,
)

from .errors import OpenTelemetryNotInstalled


class OtelMetrics:
	"""OpenTelemetry-backed metrics adapter.

	Implements :class:`flowforge.ports.metrics.HistogramMetricsPort` so a
	host can swap ``flowforge.config.metrics`` from the in-memory fake
	to this adapter at startup.

	The constructor pre-creates instruments for every histogram name in
	:data:`flowforge.ports.metrics.STANDARD_HISTOGRAM_NAMES`. Custom
	histograms are created lazily on first observation.
	"""

	def __init__(
		self,
		meter_name: str = "flowforge",
		*,
		sla_breach_seconds: float = 0.0,
	) -> None:
		assert isinstance(meter_name, str) and meter_name, \
			"meter_name must be a non-empty string"
		try:
			from opentelemetry import metrics as _otel_metrics
		except ImportError as exc:  # pragma: no cover
			raise OpenTelemetryNotInstalled("opentelemetry") from exc
		self._meter = _otel_metrics.get_meter(meter_name)
		self._meter_name = meter_name
		self._counters: dict[str, Any] = {}
		self._histograms: dict[str, Any] = {}
		self._sla_breach_seconds = float(sla_breach_seconds)
		# Pre-create the standard histograms so the OTel SDK reports
		# them even before the first observation arrives.
		for name in STANDARD_HISTOGRAM_NAMES:
			self._histograms[name] = self._make_histogram(name)
		# Surface the recommended bucket layout for hosts that want to
		# wire it into their MetricExporter view-config. Pure metadata —
		# the OTel API doesn't accept buckets at instrument-creation
		# time; views must be configured on the SDK separately.
		self.recommended_fire_duration_buckets = default_fire_duration_buckets(
			self._sla_breach_seconds
		)

	def _make_histogram(self, name: str) -> Any:
		unit = "s" if name.endswith("_seconds") else "1"
		return self._meter.create_histogram(
			name=name,
			unit=unit,
			description=f"flowforge histogram: {name}",
		)

	def _make_counter(self, name: str) -> Any:
		return self._meter.create_counter(
			name=name,
			unit="1",
			description=f"flowforge counter: {name}",
		)

	def emit(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
		"""Record a counter add — the classic :class:`MetricsPort` API."""

		assert isinstance(name, str) and name, "metric name must be a non-empty string"
		counter = self._counters.get(name)
		if counter is None:
			counter = self._make_counter(name)
			self._counters[name] = counter
		counter.add(float(value), attributes=dict(labels or {}))

	def record_histogram(
		self,
		name: str,
		value: float,
		labels: Mapping[str, str] | None = None,
	) -> None:
		"""Record a histogram observation."""

		assert isinstance(name, str) and name, "metric name must be a non-empty string"
		hist = self._histograms.get(name)
		if hist is None:
			hist = self._make_histogram(name)
			self._histograms[name] = hist
		hist.record(float(value), attributes=dict(labels or {}))

	@property
	def fire_duration_histogram_name(self) -> str:
		"""Convenience: name of the engine-fire latency histogram."""

		return FIRE_DURATION_HISTOGRAM
