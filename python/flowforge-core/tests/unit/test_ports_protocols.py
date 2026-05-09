"""Verify every port ABC is a runtime-checkable Protocol with a default fake."""

from __future__ import annotations

import pytest

from flowforge.ports import (
	AccessGrantPort,
	AnalyticsPort,
	AuditSink,
	DocumentPort,
	HistogramMetricsPort,
	MetricsPort,
	MoneyPort,
	NotificationPort,
	OutboxRegistry,
	RbacResolver,
	RlsBinder,
	SettingsPort,
	SigningPort,
	TaskTrackerPort,
	TenancyResolver,
	TracingPort,
)
from flowforge.testing.port_fakes import (
	InMemoryAccessGrant,
	InMemoryAnalytics,
	InMemoryAuditSink,
	InMemoryDocuments,
	InMemoryMetrics,
	InMemoryMoney,
	InMemoryNotifications,
	InMemoryOutbox,
	InMemoryRbac,
	InMemorySettings,
	InMemorySigning,
	InMemoryTaskTracker,
	InMemoryTenancy,
	NoopRls,
	NoopTracing,
)


def test_every_port_is_runtime_checkable() -> None:
	pairs = [
		(TenancyResolver, InMemoryTenancy()),
		(RbacResolver, InMemoryRbac()),
		(AuditSink, InMemoryAuditSink()),
		(OutboxRegistry, InMemoryOutbox()),
		(DocumentPort, InMemoryDocuments()),
		(MoneyPort, InMemoryMoney()),
		(SettingsPort, InMemorySettings()),
		(SigningPort, InMemorySigning()),
		(NotificationPort, InMemoryNotifications()),
		(RlsBinder, NoopRls()),
		(MetricsPort, InMemoryMetrics()),
		# v0.3.0 W2 / item 12: HistogramMetricsPort is the optional
		# extension Protocol; the in-memory fake implements both.
		(HistogramMetricsPort, InMemoryMetrics()),
		(TaskTrackerPort, InMemoryTaskTracker()),
		(AccessGrantPort, InMemoryAccessGrant()),
		(AnalyticsPort, InMemoryAnalytics()),
		# v0.3.0 W2 / item 12: TracingPort port + NoopTracing fake.
		(TracingPort, NoopTracing()),
	]
	for proto, fake in pairs:
		assert isinstance(fake, proto), f"{type(fake).__name__} doesn't satisfy {proto.__name__}"


async def test_noop_tracing_records_span_attributes() -> None:
	"""W2 item 12: NoopTracing fake captures span name + attributes for test assertions."""

	tracing = NoopTracing()
	async with tracing.start_span(
		"flowforge.fire",
		{
			"flowforge.tenant_id": "t1",
			"flowforge.jtbd_id": "claim_intake",
			"flowforge.event": "submit",
			"flowforge.principal_user_id": "user-42",
		},
	) as span:
		span.set_attribute("flowforge.new_state", "review")

	assert len(tracing.spans) == 1
	got = tracing.spans[0]
	assert got.name == "flowforge.fire"
	assert got.attributes["flowforge.tenant_id"] == "t1"
	assert got.attributes["flowforge.jtbd_id"] == "claim_intake"
	assert got.attributes["flowforge.event"] == "submit"
	assert got.attributes["flowforge.principal_user_id"] == "user-42"
	assert got.attributes["flowforge.new_state"] == "review"


async def test_noop_tracing_records_exceptions() -> None:
	"""Exceptions raised inside the span body land on the span's exceptions list."""

	tracing = NoopTracing()
	with pytest.raises(RuntimeError, match="boom"):
		async with tracing.start_span("flowforge.fire"):
			raise RuntimeError("boom")
	assert len(tracing.spans) == 1
	assert len(tracing.spans[0].exceptions) == 1
	assert isinstance(tracing.spans[0].exceptions[0], RuntimeError)


def test_in_memory_metrics_records_histograms() -> None:
	"""W2 item 12: InMemoryMetrics records histogram observations independently of counters."""

	from flowforge.ports.metrics import FIRE_DURATION_HISTOGRAM

	m = InMemoryMetrics()
	m.emit("flowforge.fires_total", 1.0, {"tenant_id": "t1"})
	m.record_histogram(FIRE_DURATION_HISTOGRAM, 0.42, {"tenant_id": "t1"})
	assert m.points == [("flowforge.fires_total", 1.0, {"tenant_id": "t1"})]
	assert m.histograms == [(FIRE_DURATION_HISTOGRAM, 0.42, {"tenant_id": "t1"})]


async def test_in_memory_analytics_records_events_in_order() -> None:
	"""W2 item 16: AnalyticsPort fake captures (event, properties) tuples in insertion order."""

	sink = InMemoryAnalytics()
	await sink.track("claim_intake.submission_started", {"instanceId": "abc"})
	await sink.track("claim_intake.submission_succeeded", {"instanceId": "abc", "fieldCount": 3})

	assert len(sink.events) == 2
	assert sink.events[0] == ("claim_intake.submission_started", {"instanceId": "abc"})
	assert sink.events[1] == ("claim_intake.submission_succeeded", {"instanceId": "abc", "fieldCount": 3})


async def test_in_memory_analytics_defensive_copy_isolates_caller_mutations() -> None:
	"""Mutating the original property dict after track() must not rewrite captured history."""

	sink = InMemoryAnalytics()
	props: dict[str, object] = {"fieldId": "claimant_name"}
	await sink.track("claim_intake.field_focused", props)
	props["fieldId"] = "ROTATED"  # caller-side mutation
	assert sink.events[0][1]["fieldId"] == "claimant_name"
