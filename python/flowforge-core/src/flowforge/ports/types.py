"""Shared dataclasses + type aliases for port contracts.

These types are framework-stable: changes here imply a major version bump
per ``docs/workflow-framework-portability.md`` §9.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---- type aliases ----------------------------------------------------

TenantId = str
PermissionName = str


@dataclass(frozen=True)
class Scope:
	"""Authorisation scope. Tenant + optional resource-id."""

	tenant_id: TenantId
	resource_id: str | None = None
	resource_kind: str | None = None


@dataclass(frozen=True)
class Principal:
	"""Authenticated identity passed into the engine."""

	user_id: str
	roles: tuple[str, ...] = ()
	is_system: bool = False


@dataclass(frozen=True)
class ExecutionContext:
	"""Per-event context carried through the engine.

	The engine never mutates this; effects derive a fresh ctx per
	transition.
	"""

	tenant_id: TenantId
	principal: Principal
	elevated: bool = False
	correlation_id: str | None = None
	now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---- audit ------------------------------------------------------------


@dataclass(frozen=True)
class AuditEvent:
	"""One row of the append-only audit log."""

	kind: str
	subject_kind: str
	subject_id: str
	tenant_id: TenantId
	actor_user_id: str | None
	payload: dict[str, Any]
	occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---- outbox ------------------------------------------------------------


@dataclass(frozen=True)
class OutboxEnvelope:
	"""Outbox row payload."""

	kind: str
	tenant_id: TenantId
	body: dict[str, Any]
	correlation_id: str | None = None
	dedupe_key: str | None = None


# ---- notification ------------------------------------------------------


@dataclass(frozen=True)
class NotificationSpec:
	"""Template registration spec."""

	template_id: str
	channels: tuple[str, ...]
	subject_template: str
	body_template: str
	locale: str = "en"
