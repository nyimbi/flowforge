# flowforge-otel changelog

## 0.1.0 — v0.3.0 W2 (item 12)

Initial release. OpenTelemetry-backed `TracingPort` + `HistogramMetricsPort` adapter for flowforge.

### Added

- `OtelTracing` — wraps `opentelemetry.trace.get_tracer(...)` to satisfy `flowforge.ports.tracing.TracingPort`. Async-context-manager-shaped span surface aligns with the in-memory `flowforge.testing.port_fakes.NoopTracing` fake so call sites are identical regardless of host wiring.
- `OtelMetrics` — wraps `opentelemetry.metrics.get_meter(...)`. Implements both the classic `MetricsPort.emit` (counters) and the new `HistogramMetricsPort.record_histogram` (histograms) surfaces. Pre-creates instruments for every name in `flowforge.ports.metrics.STANDARD_HISTOGRAM_NAMES`.
- `OtelSpan` — adapter span that delegates `set_attribute` / `record_exception` to the underlying OTel span and flips its status to `ERROR` on exception capture.
- `install(*, tracer_name, meter_name, sla_breach_seconds)` — convenience wiring helper that mounts both adapters onto `flowforge.config`.
- `OpenTelemetryNotInstalled` — error raised on construction when the OTel SDK isn't installed (the package itself is importable without the SDK so type-stubs work).

### Notes

- The `[otel]` extra pulls `opentelemetry-api>=1.20` and `opentelemetry-sdk>=1.20`; the bare install ships only the type-stable adapter API.
- The recommended bucket layout for the engine-fire latency histogram is exposed as `OtelMetrics.recommended_fire_duration_buckets` (sourced from `flowforge.ports.metrics.default_fire_duration_buckets(sla_breach_seconds)`). OTel's instrument-creation API doesn't accept buckets directly; hosts wire the bucket layout into a `MetricExporter` view config.
