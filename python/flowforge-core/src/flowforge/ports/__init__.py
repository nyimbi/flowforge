"""Port ABCs.

Each module exports one runtime-checkable Protocol. Hosts implement the
Protocol; the engine only ever calls these methods. See
``docs/workflow-framework-portability.md`` §2 for the full contract.
"""

from __future__ import annotations

from .types import (
	AuditEvent,
	ExecutionContext,
	NotificationSpec,
	OutboxEnvelope,
	PermissionName,
	Principal,
	Scope,
	TenantId,
)
from .analytics import AnalyticsPort
from .audit import AuditSink, Verdict
from .documents import DocumentPort
from .entity import EntityAdapter, register_entity
from .grants import AccessGrantPort
from .metrics import (
	AUDIT_APPEND_DURATION_HISTOGRAM,
	FIRE_DURATION_HISTOGRAM,
	HistogramMetricsPort,
	MetricsPort,
	OUTBOX_DISPATCH_DURATION_HISTOGRAM,
	STANDARD_HISTOGRAM_NAMES,
	default_fire_duration_buckets,
)
from .money import MoneyPort
from .notification import NotificationPort
from .outbox import OutboxRegistry
from .rbac import RbacResolver
from .rls import RlsBinder
from .settings import SettingsPort, SettingSpec
from .signing import SigningPort
from .tasks import TaskTrackerPort
from .tenancy import TenancyResolver
from .tracing import (
	STANDARD_SPAN_ATTRIBUTES,
	STANDARD_SPAN_NAMES,
	Span,
	TracingPort,
)

__all__ = [
	"AnalyticsPort",
	"AuditEvent",
	"AuditSink",
	"Verdict",
	"AccessGrantPort",
	"AUDIT_APPEND_DURATION_HISTOGRAM",
	"DocumentPort",
	"EntityAdapter",
	"register_entity",
	"ExecutionContext",
	"FIRE_DURATION_HISTOGRAM",
	"HistogramMetricsPort",
	"MetricsPort",
	"MoneyPort",
	"NotificationPort",
	"NotificationSpec",
	"OutboxEnvelope",
	"OutboxRegistry",
	"OUTBOX_DISPATCH_DURATION_HISTOGRAM",
	"PermissionName",
	"Principal",
	"RbacResolver",
	"RlsBinder",
	"Scope",
	"SettingsPort",
	"SettingSpec",
	"SigningPort",
	"Span",
	"STANDARD_HISTOGRAM_NAMES",
	"STANDARD_SPAN_ATTRIBUTES",
	"STANDARD_SPAN_NAMES",
	"TaskTrackerPort",
	"TenancyResolver",
	"TenantId",
	"TracingPort",
	"default_fire_duration_buckets",
]
