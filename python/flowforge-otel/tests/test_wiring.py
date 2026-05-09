"""``flowforge_otel.install`` mounts both adapters onto ``flowforge.config``."""

from __future__ import annotations

import pytest


pytest.importorskip("opentelemetry")


from opentelemetry import metrics as _otel_metrics, trace as _otel_trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from flowforge import config as _flowforge_config
from flowforge_otel import OtelMetrics, OtelTracing, install


def _ensure_otel_provider() -> None:
	"""Install a process-wide tracer + meter provider if not already set.

	OTel's setters are one-shot, so once a provider is installed in the
	test process every subsequent test reuses it. The wiring tests don't
	care about the exporter contents — only that ``install`` mounts
	itself on ``flowforge.config``.
	"""

	current_tracer = _otel_trace.get_tracer_provider()
	if not isinstance(current_tracer, TracerProvider):
		provider = TracerProvider()
		provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
		_otel_trace.set_tracer_provider(provider)
	# Meter provider: there's no public ``isinstance`` test for the
	# proxy/no-op meter provider, so call set_meter_provider once and
	# accept the warning on subsequent calls.
	if not getattr(_ensure_otel_provider, "_meter_installed", False):
		_otel_metrics.set_meter_provider(
			MeterProvider(metric_readers=[InMemoryMetricReader()])
		)
		_ensure_otel_provider._meter_installed = True  # type: ignore[attr-defined]


def test_install_mounts_adapters_on_config() -> None:
	_ensure_otel_provider()

	tracing, metrics = install(sla_breach_seconds=300.0)

	assert isinstance(tracing, OtelTracing)
	assert isinstance(metrics, OtelMetrics)
	assert _flowforge_config.tracing is tracing
	assert _flowforge_config.metrics is metrics


def test_install_idempotent() -> None:
	"""Calling install twice yields fresh instances and the latest sticks."""

	_ensure_otel_provider()

	first_tracing, first_metrics = install()
	second_tracing, second_metrics = install()

	assert first_tracing is not second_tracing
	assert first_metrics is not second_metrics
	assert _flowforge_config.tracing is second_tracing
	assert _flowforge_config.metrics is second_metrics
