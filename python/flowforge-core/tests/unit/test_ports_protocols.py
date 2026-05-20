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
from flowforge.ports import entity as entity_module
from flowforge.ports.entity import EntityAdapter, EntityRegistry, register_entity
from flowforge.ports.metrics import (
	AUDIT_APPEND_DURATION_HISTOGRAM,
	FIRE_DURATION_HISTOGRAM,
	OUTBOX_DISPATCH_DURATION_HISTOGRAM,
	STANDARD_HISTOGRAM_NAMES,
	STANDARD_LABEL_NAMES,
	default_fire_duration_buckets,
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

	m = InMemoryMetrics()
	m.emit("flowforge.fires_total", 1.0, {"tenant_id": "t1"})
	m.record_histogram(FIRE_DURATION_HISTOGRAM, 0.42, {"tenant_id": "t1"})
	assert m.points == [("flowforge.fires_total", 1.0, {"tenant_id": "t1"})]
	assert m.histograms == [(FIRE_DURATION_HISTOGRAM, 0.42, {"tenant_id": "t1"})]


def test_metrics_public_constants_and_bucket_edges_are_stable() -> None:
	assert STANDARD_LABEL_NAMES == (
		"tenant_id",
		"def_key",
		"state",
		"jtbd_id",
		"jtbd_version",
	)
	assert STANDARD_HISTOGRAM_NAMES == (
		FIRE_DURATION_HISTOGRAM,
		OUTBOX_DISPATCH_DURATION_HISTOGRAM,
		AUDIT_APPEND_DURATION_HISTOGRAM,
	)
	assert default_fire_duration_buckets(None) == (0.1, 1.0, 10.0, 60.0, 600.0)
	assert default_fire_duration_buckets(0) == (0.1, 1.0, 10.0, 60.0, 600.0)
	assert default_fire_duration_buckets(-5.0) == (0.1, 1.0, 10.0, 60.0, 600.0)
	assert default_fire_duration_buckets(2.0) == (0.1, 1.0, 2.0, 4.0, 10.0, 60.0, 600.0)
	assert default_fire_duration_buckets(1.0) == (0.1, 0.5, 1.0, 2.0, 10.0, 60.0, 600.0)
	with pytest.raises(TypeError, match="numeric"):
		default_fire_duration_buckets("slow")  # type: ignore[arg-type]


async def test_entity_registry_and_decorator_contract(monkeypatch: pytest.MonkeyPatch) -> None:
	class ClaimAdapter:
		compensations = {"undo": "undo_claim"}

		async def create(self, session, payload):
			return {"id": "claim-1", **payload}

		async def update(self, session, id_, payload):
			return {"id": id_, **payload}

		async def lookup(self, session, id_):
			return {"id": id_}

	registry = EntityRegistry()
	adapter = ClaimAdapter()
	registry.register("claim", adapter)
	registry.register("policy", adapter)
	assert registry.get("claim") is adapter
	assert registry.get("missing") is None
	assert registry.list_kinds() == ["claim", "policy"]
	assert isinstance(adapter, EntityAdapter)
	assert await adapter.create(None, {"status": "new"}) == {"id": "claim-1", "status": "new"}
	assert await adapter.update(None, "claim-2", {"status": "done"}) == {
		"id": "claim-2",
		"status": "done",
	}
	assert await adapter.lookup(None, "claim-3") == {"id": "claim-3"}

	monkeypatch.setattr(entity_module, "_GLOBAL_REGISTRY", None)

	@register_entity("claim")
	class DecoratedClaimAdapter(ClaimAdapter):
		pass

	registered = entity_module._registry().get("claim")
	assert registered is not None
	assert registered.compensations == {"undo": "undo_claim"}


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
