"""flowforge r1 initial schema.

Revision ID: r1_initial
Revises:
Create Date: 2026-05-05

Creates the ten engine-managed tables. The migration is dialect-aware:
PostgreSQL gets ``JSONB`` columns; SQLite/MySQL fall back to ``JSON``
through the :class:`flowforge_sqlalchemy.base.JsonB` ``TypeDecorator``.
RLS policies are NOT installed by this revision — hosts that want them
ship a follow-up migration tailored to their tenancy model.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from flowforge_sqlalchemy.base import JsonB, UuidStr

# Alembic identifiers
revision = "r1_initial"
down_revision = None
branch_labels = ("flowforge",)
depends_on = None


def upgrade() -> None:
	op.create_table(
		"workflow_definitions",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column("key", sa.String(255), nullable=False),
		sa.Column("subject_kind", sa.String(128), nullable=False),
		sa.Column("current_version", sa.String(64), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint("tenant_id", "key", name="uq_workflow_definitions_tenant_key"),
	)

	op.create_table(
		"workflow_definition_versions",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"definition_id",
			UuidStr(),
			sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column("def_key", sa.String(255), nullable=False),
		sa.Column("version", sa.String(64), nullable=False),
		sa.Column("body", JsonB(), nullable=False),
		sa.Column("checksum", sa.String(128), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint(
			"tenant_id", "def_key", "version",
			name="uq_workflow_definition_versions_tenant_key_version",
		),
	)

	op.create_table(
		"workflow_instances",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column("def_key", sa.String(255), nullable=False),
		sa.Column("def_version", sa.String(64), nullable=False),
		sa.Column("subject_kind", sa.String(128), nullable=False),
		sa.Column("subject_id", sa.String(128), nullable=True, index=True),
		sa.Column("state", sa.String(128), nullable=False, index=True),
		sa.Column("terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
		sa.Column("context", JsonB(), nullable=False),
		sa.Column("correlation_id", sa.String(128), nullable=True, index=True),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
	)
	op.create_index(
		"ix_workflow_instances_tenant_def",
		"workflow_instances",
		["tenant_id", "def_key"],
	)

	op.create_table(
		"workflow_instance_tokens",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"instance_id",
			UuidStr(),
			sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column("region", sa.String(128), nullable=False),
		sa.Column("state", sa.String(128), nullable=False),
		sa.Column("context", JsonB(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
	)

	op.create_table(
		"workflow_events",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"instance_id",
			UuidStr(),
			sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column("seq", sa.BigInteger(), nullable=False),
		sa.Column("event", sa.String(255), nullable=False),
		sa.Column("from_state", sa.String(128), nullable=True),
		sa.Column("to_state", sa.String(128), nullable=True),
		sa.Column("transition_id", sa.String(255), nullable=True),
		sa.Column("actor_user_id", sa.String(128), nullable=True),
		sa.Column("payload", JsonB(), nullable=False),
		sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint("instance_id", "seq", name="uq_workflow_events_instance_seq"),
	)
	op.create_index(
		"ix_workflow_events_instance_occurred",
		"workflow_events",
		["instance_id", "occurred_at"],
	)

	op.create_table(
		"workflow_saga_steps",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"instance_id",
			UuidStr(),
			sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column("idx", sa.Integer(), nullable=False),
		sa.Column("kind", sa.String(255), nullable=False),
		sa.Column("args", JsonB(), nullable=False),
		sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint("instance_id", "idx", name="uq_workflow_saga_steps_instance_idx"),
	)

	op.create_table(
		"workflow_instance_quarantine",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"instance_id",
			UuidStr(),
			sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
			nullable=False,
			unique=True,
		),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column("details", JsonB(), nullable=False),
		sa.Column("quarantined_by", sa.String(128), nullable=True),
		sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
	)

	op.create_table(
		"business_calendars",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column("calendar_key", sa.String(128), nullable=False),
		sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
		sa.Column("working_hours", JsonB(), nullable=False),
		sa.Column("holidays", JsonB(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint(
			"tenant_id", "calendar_key", name="uq_business_calendars_tenant_key"
		),
	)

	op.create_table(
		"pending_signals",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column("name", sa.String(255), nullable=False),
		sa.Column("correlation_key", sa.String(255), nullable=False),
		sa.Column("payload", JsonB(), nullable=False),
		sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index(
		"ix_pending_signals_lookup",
		"pending_signals",
		["tenant_id", "name", "correlation_key", "consumed"],
	)

	op.create_table(
		"workflow_instance_snapshots",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"instance_id",
			UuidStr(),
			sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
			nullable=False,
			unique=True,
		),
		sa.Column("def_key", sa.String(255), nullable=False),
		sa.Column("def_version", sa.String(64), nullable=False),
		sa.Column("state", sa.String(128), nullable=False),
		sa.Column("body", JsonB(), nullable=False),
		sa.Column("seq", sa.BigInteger(), nullable=False, server_default="0"),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
	)


def downgrade() -> None:
	op.drop_table("workflow_instance_snapshots")
	op.drop_index("ix_pending_signals_lookup", table_name="pending_signals")
	op.drop_table("pending_signals")
	op.drop_table("business_calendars")
	op.drop_table("workflow_instance_quarantine")
	op.drop_table("workflow_saga_steps")
	op.drop_index("ix_workflow_events_instance_occurred", table_name="workflow_events")
	op.drop_table("workflow_events")
	op.drop_table("workflow_instance_tokens")
	op.drop_index("ix_workflow_instances_tenant_def", table_name="workflow_instances")
	op.drop_table("workflow_instances")
	op.drop_table("workflow_definition_versions")
	op.drop_table("workflow_definitions")
