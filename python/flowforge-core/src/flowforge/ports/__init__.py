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
from .audit import AuditSink, Verdict
from .documents import DocumentPort
from .entity import EntityAdapter, register_entity
from .grants import AccessGrantPort
from .metrics import MetricsPort
from .money import MoneyPort
from .notification import NotificationPort
from .outbox import OutboxRegistry
from .rbac import RbacResolver
from .rls import RlsBinder
from .settings import SettingsPort, SettingSpec
from .signing import SigningPort
from .tasks import TaskTrackerPort
from .tenancy import TenancyResolver

__all__ = [
	"AuditEvent",
	"AuditSink",
	"Verdict",
	"AccessGrantPort",
	"DocumentPort",
	"EntityAdapter",
	"register_entity",
	"ExecutionContext",
	"MetricsPort",
	"MoneyPort",
	"NotificationPort",
	"NotificationSpec",
	"OutboxEnvelope",
	"OutboxRegistry",
	"PermissionName",
	"Principal",
	"RbacResolver",
	"RlsBinder",
	"Scope",
	"SettingsPort",
	"SettingSpec",
	"SigningPort",
	"TaskTrackerPort",
	"TenancyResolver",
	"TenantId",
]
