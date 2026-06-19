"""flowforge r2: add workflow_tasks table.

Revision ID: r2_workflow_tasks
Revises: r1_initial
Create Date: 2026-06-19

Adds the ``workflow_tasks`` table used by :class:`PostgresTaskTracker`
to surface pending manual-review items.  The table is intentionally
separate from ``workflow_instances`` so ops dashboards can query it
without touching the core engine tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from flowforge_sqlalchemy.base import UuidStr

revision = "r2_workflow_tasks"
down_revision = "r1_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.create_table(
		"workflow_tasks",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False),
		sa.Column("kind", sa.String(64), nullable=False),
		sa.Column("ref", sa.String(512), nullable=False),
		sa.Column("note", sa.Text(), nullable=False, server_default=""),
		sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			nullable=False,
			server_default=sa.text("now()"),
		),
		sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
	)
	op.create_index("ix_workflow_tasks_tenant_id", "workflow_tasks", ["tenant_id"])
	op.create_index("ix_workflow_tasks_ref", "workflow_tasks", ["ref"])
	op.create_index("ix_workflow_tasks_status", "workflow_tasks", ["status"])
	op.create_index(
		"ix_workflow_tasks_status_created",
		"workflow_tasks",
		["status", "created_at"],
	)


def downgrade() -> None:
	op.drop_index("ix_workflow_tasks_status_created", table_name="workflow_tasks")
	op.drop_index("ix_workflow_tasks_status", table_name="workflow_tasks")
	op.drop_index("ix_workflow_tasks_ref", table_name="workflow_tasks")
	op.drop_index("ix_workflow_tasks_tenant_id", table_name="workflow_tasks")
	op.drop_table("workflow_tasks")
