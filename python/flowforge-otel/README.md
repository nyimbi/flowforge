# flowforge-otel

OpenTelemetry-backed `TracingPort` + `HistogramMetricsPort` adapter for [flowforge](https://github.com/nyimbi/ums/tree/main/framework). Ships in v0.3.0 W2 / item 12.

## Install

```bash
uv pip install "flowforge-otel[otel]"
```

The bare `flowforge-otel` install pulls only the type-stable adapter API so you can stub against it in mypy without dragging the OpenTelemetry SDK along. The `[otel]` extra adds `opentelemetry-api>=1.20` and `opentelemetry-sdk>=1.20`. Construction will raise `OpenTelemetryNotInstalled` if the SDK is missing.

## What it does

- `OtelTracing` — wraps `opentelemetry.trace.get_tracer(...)` so generated host code (workflow_adapter, domain_service, domain_router) can `async with tracing.start_span("flowforge.fire", attributes={...}) as span:` without importing OpenTelemetry directly.
- `OtelMetrics` — wraps `opentelemetry.metrics.get_meter(...)`. Implements both `MetricsPort.emit` (counters) and `HistogramMetricsPort.record_histogram` (histograms). Pre-creates the standard histograms documented in `flowforge.ports.metrics.STANDARD_HISTOGRAM_NAMES`.
- `install(...)` — convenience wiring helper that mounts both adapters onto `flowforge.config`.

The adapter is hexagonal-friendly: `flowforge-core` declares only the port ABCs (`flowforge.ports.tracing.TracingPort`, `flowforge.ports.metrics.HistogramMetricsPort`); the OpenTelemetry imports are confined to this package.

## Quick start

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor

# Host wires its TracerProvider once at startup.
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

# Then mount the adapters.
from flowforge_otel import install
tracing, metrics = install(sla_breach_seconds=300.0)

# Now generated host code emits real spans + histograms.
```

## Span / metric naming

- Span names: `flowforge.fire`, `flowforge.router.event`, `flowforge.service.submit`, `flowforge.service.transition`, `flowforge.audit.append`, `flowforge.outbox.dispatch` (see `flowforge.ports.tracing.STANDARD_SPAN_NAMES`).
- Span attributes: `flowforge.tenant_id`, `flowforge.jtbd_id`, `flowforge.state`, `flowforge.event`, `flowforge.principal_user_id` (see `flowforge.ports.tracing.STANDARD_SPAN_ATTRIBUTES`).
- Histograms: `flowforge.fire.duration_seconds`, `flowforge.outbox.dispatch.duration_seconds`, `flowforge.audit.append.duration_seconds` (see `flowforge.ports.metrics.STANDARD_HISTOGRAM_NAMES`).
- Bucket layout: `flowforge.ports.metrics.default_fire_duration_buckets(sla_breach_seconds)` returns the recommended Prometheus-style bucket edges. The adapter exposes the result as `OtelMetrics.recommended_fire_duration_buckets` so hosts can wire it into their `MetricExporter` view config.

## Public API

- `OtelTracing(tracer_name="flowforge")` — `TracingPort` impl.
- `OtelMetrics(meter_name="flowforge", *, sla_breach_seconds=0.0)` — `HistogramMetricsPort` impl.
- `OtelSpan(otel_span)` — wraps an OpenTelemetry `Span`; satisfies `flowforge.ports.tracing.Span`.
- `install(*, tracer_name="flowforge", meter_name="flowforge", sla_breach_seconds=0.0)` — mounts both onto `flowforge.config`.
- `OpenTelemetryNotInstalled` — error raised on construction if the SDK isn't installed.

## Compatibility

- Python 3.11+
- `opentelemetry-api`, `opentelemetry-sdk` ≥ 1.20

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge-core`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- v0.3.0 engineering plan: [`docs/v0.3.0-engineering-plan.md`](https://github.com/nyimbi/ums/blob/main/framework/docs/v0.3.0-engineering-plan.md)
