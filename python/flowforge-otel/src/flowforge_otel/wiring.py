"""Convenience wiring helper.

Hosts call :func:`install` once at startup to swap the in-memory
``tracing`` + ``metrics`` fakes for the OTel-backed adapters. The
function is idempotent and returns the constructed adapters so the
caller can keep handles for shutdown / flush.
"""

from __future__ import annotations

from .metrics_adapter import OtelMetrics
from .tracing_adapter import OtelTracing


def install(
	*,
	tracer_name: str = "flowforge",
	meter_name: str = "flowforge",
	sla_breach_seconds: float = 0.0,
) -> tuple[OtelTracing, OtelMetrics]:
	"""Mount OTel-backed adapters onto :mod:`flowforge.config`.

	Returns ``(tracing, metrics)`` so the host can flush / shut them
	down at process exit.
	"""

	from flowforge import config as _config

	tracing = OtelTracing(tracer_name=tracer_name)
	metrics = OtelMetrics(meter_name=meter_name, sla_breach_seconds=sla_breach_seconds)
	_config.tracing = tracing
	_config.metrics = metrics
	return tracing, metrics
