"""Verify every port ABC is a runtime-checkable Protocol with a default fake."""

from __future__ import annotations

from flowforge.ports import (
	AccessGrantPort,
	AuditSink,
	DocumentPort,
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
)
from flowforge.testing.port_fakes import (
	InMemoryAccessGrant,
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
		(TaskTrackerPort, InMemoryTaskTracker()),
		(AccessGrantPort, InMemoryAccessGrant()),
	]
	for proto, fake in pairs:
		assert isinstance(fake, proto), f"{type(fake).__name__} doesn't satisfy {proto.__name__}"
