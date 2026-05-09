"""flowforge-otel — OpenTelemetry-backed TracingPort + HistogramMetricsPort.

Implements the v0.3.0 W2 / item 12 adapter:

* :class:`OtelTracing` — wraps ``opentelemetry.trace`` to satisfy
  :class:`flowforge.ports.tracing.TracingPort`.
* :class:`OtelMetrics` — wraps ``opentelemetry.metrics`` to satisfy
  :class:`flowforge.ports.metrics.HistogramMetricsPort` (and therefore
  :class:`flowforge.ports.metrics.MetricsPort`).
* :func:`install` — convenience wiring helper that mounts both adapters
  onto :mod:`flowforge.config`.

The OpenTelemetry SDK dependency is declared in the ``[otel]`` extra so
hosts that just want to import the type-stable adapter API (e.g. for
mypy) can install ``flowforge-otel`` without pulling the SDK in.
``OtelTracing`` and ``OtelMetrics`` raise :class:`OpenTelemetryNotInstalled`
at construction time when the SDK is missing.
"""

from .errors import OpenTelemetryNotInstalled
from .metrics_adapter import OtelMetrics
from .tracing_adapter import OtelSpan, OtelTracing
from .wiring import install

__all__ = [
	"OpenTelemetryNotInstalled",
	"OtelMetrics",
	"OtelSpan",
	"OtelTracing",
	"install",
]
