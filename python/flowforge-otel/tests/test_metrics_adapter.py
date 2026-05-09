"""flowforge-otel HistogramMetricsPort adapter tests."""

from __future__ import annotations

import pytest


pytest.importorskip("opentelemetry")


from opentelemetry import metrics as _otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from flowforge.ports.metrics import (
	FIRE_DURATION_HISTOGRAM,
	HistogramMetricsPort,
	MetricsPort,
	default_fire_duration_buckets,
)
from flowforge_otel import OtelMetrics


_PROVIDER: MeterProvider | None = None
_PRIMARY_READER: InMemoryMetricReader | None = None


@pytest.fixture
def reader() -> InMemoryMetricReader:
	"""Return the in-memory metric reader installed on the process meter
	provider. OTel's ``set_meter_provider`` is one-shot per process, so
	the first test installs the provider and every subsequent test
	reuses the same reader."""

	global _PROVIDER, _PRIMARY_READER
	if _PROVIDER is None:
		_PRIMARY_READER = InMemoryMetricReader()
		_PROVIDER = MeterProvider(metric_readers=[_PRIMARY_READER])
		_otel_metrics.set_meter_provider(_PROVIDER)
	assert _PRIMARY_READER is not None
	return _PRIMARY_READER


def _names_in_metrics(reader: InMemoryMetricReader) -> set[str]:
	"""Inspect the in-memory metric reader and return all instrument names."""

	data = reader.get_metrics_data()
	out: set[str] = set()
	if data is None:
		return out
	for resource_metrics in data.resource_metrics:
		for scope in resource_metrics.scope_metrics:
			for metric in scope.metrics:
				out.add(metric.name)
	return out


def test_record_histogram_routes_to_otel(reader: InMemoryMetricReader) -> None:
	metrics = OtelMetrics(meter_name="flowforge.test", sla_breach_seconds=300.0)

	metrics.record_histogram(
		FIRE_DURATION_HISTOGRAM,
		0.42,
		{"tenant_id": "t1", "jtbd_id": "claim_intake"},
	)
	names = _names_in_metrics(reader)
	assert FIRE_DURATION_HISTOGRAM in names


def test_emit_routes_to_counter(reader: InMemoryMetricReader) -> None:
	metrics = OtelMetrics(meter_name="flowforge.test")

	metrics.emit("flowforge.fires_total", 1.0, {"tenant_id": "t1"})
	metrics.emit("flowforge.fires_total", 1.0, {"tenant_id": "t1"})
	names = _names_in_metrics(reader)
	assert "flowforge.fires_total" in names


def test_satisfies_protocols() -> None:
	"""``OtelMetrics`` satisfies both port protocols at runtime."""

	metrics = OtelMetrics(meter_name="flowforge.test")
	assert isinstance(metrics, MetricsPort)
	assert isinstance(metrics, HistogramMetricsPort)


def test_recommended_buckets_match_helper() -> None:
	"""Adapter exposes the same buckets as ``default_fire_duration_buckets``."""

	sla = 300.0
	metrics = OtelMetrics(meter_name="flowforge.test", sla_breach_seconds=sla)
	assert metrics.recommended_fire_duration_buckets == default_fire_duration_buckets(sla)


def test_fire_duration_histogram_name_constant() -> None:
	metrics = OtelMetrics(meter_name="flowforge.test")
	assert metrics.fire_duration_histogram_name == FIRE_DURATION_HISTOGRAM
