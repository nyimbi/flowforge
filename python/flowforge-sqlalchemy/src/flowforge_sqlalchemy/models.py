"""SQLAlchemy 2.x ORM models for the flowforge storage layer.

Ten tables back the engine:

* ``workflow_definitions`` — one row per ``(tenant_id, key)``; carries
  the latest version pointer.
* ``workflow_definition_versions`` — append-only versioned blobs. The
  engine pins instances to a specific ``(def_key, def_version)``.
* ``workflow_instances`` — running + terminal instances.
* ``workflow_instance_tokens`` — parallel-region tokens for fork/join
  states (mirrors :class:`flowforge.engine.tokens.Token`).
* ``workflow_events`` — append-only event log (the source of truth for
  replay; snapshots are an optimisation).
* ``workflow_saga_steps`` — saga ledger rows
  (mirrors :class:`flowforge.engine.saga.SagaStep`).
* ``workflow_instance_quarantine`` — instances put into a parking-lot
  state by the operator (manual remediation).
* ``business_calendars`` — per-tenant working-hours / holiday data used
  by pause-aware SLA timers.
* ``pending_signals`` — persisted form of
  :class:`flowforge.engine.signals.SignalCorrelator`.
* ``workflow_instance_snapshots`` — periodic ``Instance`` checkpoints
  that :class:`SqlAlchemySnapshotStore` reads/writes.

Every table carries a ``tenant_id`` column for RLS — the
:class:`PgRlsBinder` enforces visibility via ``set_config`` GUCs at the
session level.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
	BigInteger,
	Boolean,
	DateTime,
	ForeignKey,
	Index,
	Integer,
	String,
	Text,
	UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, JsonB, UuidStr


def _utcnow() -> datetime:
	"""Default factory for timezone-aware UTC ``DateTime`` columns."""
	return datetime.now(timezone.utc)


class WorkflowDefinition(Base):
	"""One workflow definition keyed by ``(tenant_id, key)``."""

	__tablename__ = "workflow_definitions"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	key: Mapped[str] = mapped_column(String(255), nullable=False)
	subject_kind: Mapped[str] = mapped_column(String(128), nullable=False)
	current_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)

	__table_args__ = (
		UniqueConstraint("tenant_id", "key", name="uq_workflow_definitions_tenant_key"),
	)


class WorkflowDefinitionVersion(Base):
	"""Append-only versioned definition blob (the JSON DSL document)."""

	__tablename__ = "workflow_definition_versions"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	definition_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	def_key: Mapped[str] = mapped_column(String(255), nullable=False)
	version: Mapped[str] = mapped_column(String(64), nullable=False)
	body: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False)
	checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)

	__table_args__ = (
		UniqueConstraint(
			"tenant_id", "def_key", "version",
			name="uq_workflow_definition_versions_tenant_key_version",
		),
	)


class WorkflowInstance(Base):
	"""Running or terminal workflow instance."""

	__tablename__ = "workflow_instances"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	def_key: Mapped[str] = mapped_column(String(255), nullable=False)
	def_version: Mapped[str] = mapped_column(String(64), nullable=False)
	subject_kind: Mapped[str] = mapped_column(String(128), nullable=False)
	subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
	state: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
	terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
	context: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)

	__table_args__ = (
		Index("ix_workflow_instances_tenant_def", "tenant_id", "def_key"),
	)


class WorkflowInstanceToken(Base):
	"""Parallel-region token (one per active branch in a fork/join)."""

	__tablename__ = "workflow_instance_tokens"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	instance_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("workflow_instances.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	region: Mapped[str] = mapped_column(String(128), nullable=False)
	state: Mapped[str] = mapped_column(String(128), nullable=False)
	context: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)


class WorkflowEvent(Base):
	"""Append-only event log row.

	Replay reconstructs an instance by reading the most recent snapshot
	plus every event after it ordered by ``seq``. ``seq`` is unique per
	instance.
	"""

	__tablename__ = "workflow_events"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	instance_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("workflow_instances.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
	event: Mapped[str] = mapped_column(String(255), nullable=False)
	from_state: Mapped[str | None] = mapped_column(String(128), nullable=True)
	to_state: Mapped[str | None] = mapped_column(String(128), nullable=True)
	transition_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
	actor_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
	payload: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	occurred_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)

	__table_args__ = (
		UniqueConstraint("instance_id", "seq", name="uq_workflow_events_instance_seq"),
		Index("ix_workflow_events_instance_occurred", "instance_id", "occurred_at"),
	)


class WorkflowSagaStep(Base):
	"""Saga ledger row.

	One row per :class:`flowforge.engine.saga.SagaStep`. ``status`` cycles
	through ``pending → done | compensated | failed`` and the
	compensation worker reads ``status='pending'`` rows in reverse.
	"""

	__tablename__ = "workflow_saga_steps"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	instance_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("workflow_instances.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	idx: Mapped[int] = mapped_column(Integer, nullable=False)
	kind: Mapped[str] = mapped_column(String(255), nullable=False)
	args: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)

	__table_args__ = (
		UniqueConstraint("instance_id", "idx", name="uq_workflow_saga_steps_instance_idx"),
	)


class WorkflowInstanceQuarantine(Base):
	"""Operator-quarantined instance.

	Hosts move an instance here when manual remediation is required
	(e.g. a guard expression that consistently raises). The runtime
	declines to advance ``quarantined`` instances until cleared.
	"""

	__tablename__ = "workflow_instance_quarantine"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	instance_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("workflow_instances.id", ondelete="CASCADE"),
		nullable=False,
		unique=True,
	)
	reason: Mapped[str] = mapped_column(Text, nullable=False)
	details: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	quarantined_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
	quarantined_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BusinessCalendar(Base):
	"""Per-tenant working-hours / holiday data used by pause-aware SLAs."""

	__tablename__ = "business_calendars"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	calendar_key: Mapped[str] = mapped_column(String(128), nullable=False)
	timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
	# Working hours as a JSON map keyed by ISO weekday (mon..sun) → list of
	# {start: "HH:MM", end: "HH:MM"} ranges. Holidays as a JSON list of
	# ISO date strings. Kept JSON to avoid a calendar mini-schema.
	working_hours: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	holidays: Mapped[list[Any]] = mapped_column(JsonB(), nullable=False, default=list)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)

	__table_args__ = (
		UniqueConstraint(
			"tenant_id", "calendar_key", name="uq_business_calendars_tenant_key"
		),
	)


class PendingSignal(Base):
	"""Persisted signal awaiting correlation.

	Mirrors :class:`flowforge.engine.signals.SignalCorrelator`'s pending
	bucket. ``correlation_key`` indexes lookups; FIFO order within a key
	is preserved by ``created_at`` + ``id``.
	"""

	__tablename__ = "pending_signals"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	correlation_key: Mapped[str] = mapped_column(String(255), nullable=False)
	payload: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False, default=dict)
	consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

	__table_args__ = (
		Index("ix_pending_signals_lookup", "tenant_id", "name", "correlation_key", "consumed"),
	)


class WorkflowInstanceSnapshot(Base):
	"""Periodic checkpoint of an :class:`flowforge.engine.fire.Instance`.

	The :class:`SqlAlchemySnapshotStore` keeps the most recent snapshot
	per instance (``unique`` on ``instance_id``) and overwrites on every
	``put``. Retaining the full series is a host concern; the engine
	only needs the latest.
	"""

	__tablename__ = "workflow_instance_snapshots"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	instance_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("workflow_instances.id", ondelete="CASCADE"),
		nullable=False,
		unique=True,
	)
	def_key: Mapped[str] = mapped_column(String(255), nullable=False)
	def_version: Mapped[str] = mapped_column(String(64), nullable=False)
	state: Mapped[str] = mapped_column(String(128), nullable=False)
	body: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False)
	seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)
