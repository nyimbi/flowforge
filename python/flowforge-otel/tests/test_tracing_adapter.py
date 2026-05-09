"""flowforge-otel TracingPort adapter tests.

Booting an in-memory ``TracerProvider`` once per test, then asserting
the spans exported by the adapter carry the canonical attribute set
documented at ``flowforge.ports.tracing.STANDARD_SPAN_ATTRIBUTES``.
"""

from __future__ import annotations

import pytest


pytest.importorskip("opentelemetry")


from opentelemetry import trace as _otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from flowforge.ports.tracing import (
	STANDARD_SPAN_ATTRIBUTES,
	STANDARD_SPAN_NAMES,
)
from flowforge_otel import OtelTracing


@pytest.fixture
def exporter() -> InMemorySpanExporter:
	"""Wire a fresh in-memory exporter into the process tracer provider.

	OTel's ``set_tracer_provider`` is one-shot per process — calling it
	again on a fresh ``TracerProvider`` triggers a warning and the second
	provider is silently dropped. To stay test-isolated we install one
	provider on first call, then attach a fresh ``SimpleSpanProcessor``
	(with a fresh exporter) for every subsequent test.
	"""

	current = _otel_trace.get_tracer_provider()
	if not isinstance(current, TracerProvider):
		current = TracerProvider()
		_otel_trace.set_tracer_provider(current)
	span_exporter = InMemorySpanExporter()
	current.add_span_processor(SimpleSpanProcessor(span_exporter))
	return span_exporter


async def test_start_span_records_canonical_attributes(exporter: InMemorySpanExporter) -> None:
	tracing = OtelTracing(tracer_name="flowforge.test")

	attrs = {
		"flowforge.tenant_id": "tenant-1",
		"flowforge.jtbd_id": "claim_intake",
		"flowforge.state": "submitted",
		"flowforge.event": "submit",
		"flowforge.principal_user_id": "user-42",
	}
	async with tracing.start_span("flowforge.fire", attrs) as span:
		span.set_attribute("flowforge.new_state", "review")

	finished = exporter.get_finished_spans()
	assert len(finished) == 1, "exactly one span exported"
	got = finished[0]
	assert got.name == "flowforge.fire"
	assert got.name in STANDARD_SPAN_NAMES, "span name in canonical set"
	got_attrs = dict(got.attributes or {})
	for key in STANDARD_SPAN_ATTRIBUTES:
		assert key in got_attrs, f"missing standard attribute {key}"
	assert got_attrs["flowforge.new_state"] == "review"


async def test_record_exception_marks_span_errored(exporter: InMemorySpanExporter) -> None:
	tracing = OtelTracing(tracer_name="flowforge.test")

	with pytest.raises(RuntimeError, match="boom"):
		async with tracing.start_span("flowforge.fire", {"flowforge.tenant_id": "t1"}):
			raise RuntimeError("boom")

	finished = exporter.get_finished_spans()
	assert len(finished) == 1
	span = finished[0]
	# OTel exposes recorded exceptions as events with the
	# ``exception`` semantic-convention name.
	exception_events = [ev for ev in span.events if ev.name == "exception"]
	assert exception_events, "exception event recorded on span"
	# Span status flipped to ERROR.
	assert span.status.status_code.name == "ERROR"


async def test_no_attributes_is_legal(exporter: InMemorySpanExporter) -> None:
	tracing = OtelTracing(tracer_name="flowforge.test")
	async with tracing.start_span("flowforge.audit.append") as span:
		span.set_attribute("flowforge.tenant_id", "t1")
	finished = exporter.get_finished_spans()
	assert len(finished) == 1
	got_attrs = dict(finished[0].attributes or {})
	assert got_attrs.get("flowforge.tenant_id") == "t1"
