"""flowforge-sqlalchemy — async SQLAlchemy 2.x storage adapter.

This package provides the durable storage layer for the flowforge engine:

* ORM models for the ten engine-managed tables
  (``workflow_definitions``, ``workflow_definition_versions``,
  ``workflow_instances``, ``workflow_instance_tokens``,
  ``workflow_events``, ``workflow_saga_steps``,
  ``workflow_instance_quarantine``, ``business_calendars``,
  ``pending_signals``, ``workflow_instance_snapshots``).
* :class:`SqlAlchemySnapshotStore` — implements
  :class:`flowforge.engine.snapshots.SnapshotStore`.
* :class:`SagaQueries` — read helpers for the saga ledger.
* :class:`PgRlsBinder` — implements
  :class:`flowforge.ports.rls.RlsBinder` for PostgreSQL.
* An Alembic version bundle (``r1_initial``) that creates all tables and
  is dialect-aware (skips ``set_config()`` GUC plumbing on SQLite).

Hosts wire :class:`SqlAlchemySnapshotStore` into the engine via
``flowforge.config``; see ``README.md`` for an end-to-end example.
"""

from __future__ import annotations

from .base import Base, metadata
from .models import (
	BusinessCalendar,
	PendingSignal,
	WorkflowDefinition,
	WorkflowDefinitionVersion,
	WorkflowEvent,
	WorkflowInstance,
	WorkflowInstanceQuarantine,
	WorkflowInstanceSnapshot,
	WorkflowInstanceToken,
	WorkflowSagaStep,
)
from .rls_pg import PgRlsBinder
from .saga_queries import SagaQueries
from .snapshot_store import SqlAlchemySnapshotStore

__all__ = [
	"Base",
	"BusinessCalendar",
	"PendingSignal",
	"PgRlsBinder",
	"SagaQueries",
	"SqlAlchemySnapshotStore",
	"WorkflowDefinition",
	"WorkflowDefinitionVersion",
	"WorkflowEvent",
	"WorkflowInstance",
	"WorkflowInstanceQuarantine",
	"WorkflowInstanceSnapshot",
	"WorkflowInstanceToken",
	"WorkflowSagaStep",
	"metadata",
]
