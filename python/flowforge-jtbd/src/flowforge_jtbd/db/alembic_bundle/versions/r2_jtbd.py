"""flowforge r2 — JTBD storage tables.

Revision ID: r2_jtbd
Revises: r1_initial
Create Date: 2026-05-06

Adds the six JTBD storage tables:

* ``jtbd_libraries``
* ``jtbd_domains``
* ``jtbd_specs``
* ``jtbd_compositions``
* ``jtbd_compositions_pins``
* ``jtbd_lockfiles``

The migration is dialect-aware: PostgreSQL gets ``JSONB`` columns
through the :class:`flowforge_sqlalchemy.base.JsonB` ``TypeDecorator``;
SQLite (test harness) falls back to generic ``JSON``. RLS policies
install on PostgreSQL only — SQLite has no RLS construct, so the
``op.execute`` block guards on ``op.get_bind().dialect.name``.

The RLS pattern matches :class:`flowforge_sqlalchemy.PgRlsBinder`'s
GUC contract: ``app.tenant_id`` is the current tenant; ``app.elevated``
opens a hub-managed catalogue scope. Catalogue rows have ``tenant_id
IS NULL`` and are visible to every tenant; tenant-scoped rows match by
GUC equality.
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from flowforge_sqlalchemy.base import JsonB, UuidStr
from sqlalchemy.sql import quoted_name

# Alembic identifiers
revision: str = "r2_jtbd"
down_revision: Union[str, None] = "r1_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables to drop on downgrade in dependency-aware order.
_TABLES_REVERSE: tuple[str, ...] = (
	"jtbd_lockfiles",
	"jtbd_compositions_pins",
	"jtbd_compositions",
	"jtbd_specs",
	"jtbd_domains",
	"jtbd_libraries",
)


def upgrade() -> None:
	op.create_table(
		"jtbd_libraries",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=True, index=True),
		sa.Column("name", sa.String(255), nullable=False),
		sa.Column("domain", sa.String(128), nullable=False),
		sa.Column(
			"upstream_lib_id",
			UuidStr(),
			sa.ForeignKey("jtbd_libraries.id", ondelete="SET NULL"),
			nullable=True,
		),
		sa.Column(
			"status", sa.String(32), nullable=False, server_default="active"
		),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint(
			"tenant_id", "name", name="uq_jtbd_libraries_tenant_name"
		),
	)
	op.create_index(
		"ix_jtbd_libraries_domain", "jtbd_libraries", ["domain"]
	)

	op.create_table(
		"jtbd_domains",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("name", sa.String(128), nullable=False, unique=True),
		sa.Column("display_name", sa.String(255), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("regulator_hints", JsonB(), nullable=False),
		sa.Column("default_compliance", JsonB(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
	)

	op.create_table(
		"jtbd_specs",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=True, index=True),
		sa.Column(
			"library_id",
			UuidStr(),
			sa.ForeignKey("jtbd_libraries.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column("jtbd_id", sa.String(255), nullable=False),
		sa.Column("version", sa.String(64), nullable=False),
		sa.Column("spec", JsonB(), nullable=False),
		sa.Column("spec_hash", sa.String(128), nullable=False),
		sa.Column(
			"parent_version_id",
			UuidStr(),
			sa.ForeignKey("jtbd_specs.id", ondelete="SET NULL"),
			nullable=True,
		),
		sa.Column("replaced_by", sa.String(255), nullable=True),
		sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
		sa.Column("created_by", sa.String(128), nullable=True),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("published_by", sa.String(128), nullable=True),
		sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
		sa.UniqueConstraint(
			"tenant_id",
			"library_id",
			"jtbd_id",
			"version",
			name="uq_jtbd_specs_tenant_library_jtbd_version",
		),
	)
	op.create_index(
		"ix_jtbd_specs_lookup",
		"jtbd_specs",
		["tenant_id", "jtbd_id", "status"],
	)
	op.create_index(
		"ix_jtbd_specs_hash", "jtbd_specs", ["spec_hash"]
	)

	op.create_table(
		"jtbd_compositions",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column("name", sa.String(255), nullable=False),
		sa.Column("project_package", sa.String(255), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column(
			"status", sa.String(32), nullable=False, server_default="draft"
		),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint(
			"tenant_id", "name", name="uq_jtbd_compositions_tenant_name"
		),
	)

	op.create_table(
		"jtbd_compositions_pins",
		sa.Column(
			"composition_id",
			UuidStr(),
			sa.ForeignKey("jtbd_compositions.id", ondelete="CASCADE"),
			primary_key=True,
		),
		sa.Column("jtbd_id", sa.String(255), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column("version", sa.String(64), nullable=False),
		sa.Column("spec_hash", sa.String(128), nullable=False),
		sa.Column("source", sa.String(64), nullable=False, server_default="local"),
		sa.Column("source_ref", sa.Text(), nullable=True),
		sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=False),
	)

	op.create_table(
		"jtbd_lockfiles",
		sa.Column("id", UuidStr(), primary_key=True),
		sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
		sa.Column(
			"composition_id",
			UuidStr(),
			sa.ForeignKey("jtbd_compositions.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column("body_hash", sa.String(128), nullable=False),
		sa.Column("body", JsonB(), nullable=False),
		sa.Column("pin_count", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("generated_by", sa.String(128), nullable=True),
		sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
		sa.UniqueConstraint(
			"composition_id",
			"body_hash",
			name="uq_jtbd_lockfiles_composition_body_hash",
		),
	)

	_install_rls_if_postgres()


def downgrade() -> None:
	_drop_rls_if_postgres()
	op.drop_index("ix_jtbd_specs_hash", table_name="jtbd_specs")
	op.drop_index("ix_jtbd_specs_lookup", table_name="jtbd_specs")
	op.drop_index("ix_jtbd_libraries_domain", table_name="jtbd_libraries")
	for table in _TABLES_REVERSE:
		op.drop_table(table)


# --- RLS plumbing ---------------------------------------------------------
#
# PostgreSQL only. SQLite has no RLS, so we guard on dialect at runtime.
# The policy contract matches ``flowforge_sqlalchemy.PgRlsBinder``: the
# GUC ``app.tenant_id`` carries the active tenant; the GUC
# ``app.elevated`` (string ``'true'`` / ``'false'``) opens a hub /
# operator scope for catalogue inserts and cross-tenant fork audits.
#
# Catalogue tier rows live with ``tenant_id IS NULL`` (read-globally,
# write-elevated). Tenant-scoped rows enforce ``tenant_id =
# current_setting('app.tenant_id')`` for both read and write.

_RLS_TABLES_TENANT_NULLABLE: tuple[str, ...] = ("jtbd_libraries", "jtbd_specs")
_RLS_TABLES_TENANT_REQUIRED: tuple[str, ...] = (
	"jtbd_compositions",
	"jtbd_compositions_pins",
	"jtbd_lockfiles",
)

# E-38 / J-01: explicit allow-list of every table the RLS DDL is permitted
# to touch. Anything outside this set raises ValueError before SQL is
# emitted, even if a future refactor pulls names from a non-constant source.
_RLS_ALLOWLIST: frozenset[str] = frozenset(
	{
		"jtbd_libraries",
		"jtbd_specs",
		"jtbd_compositions",
		"jtbd_compositions_pins",
		"jtbd_lockfiles",
		"jtbd_domains",
	}
)

# Identifier shape Postgres + the audit accept (letters, digits, underscore;
# leading non-digit). The allow-list is the authoritative gate; the regex
# is defence-in-depth so a future allow-list typo can't sneak through.
_IDENT_RE: "re.Pattern[str]" = re.compile(r"^[a-z_][a-z0-9_]*$")


def _assert_known_table(name: str) -> "quoted_name":
	"""Validate *name* against the allow-list and return a ``quoted_name``.

	The returned ``quoted_name`` carries SQLAlchemy's identifier-shape
	contract — splicing it into a string still produces just the bare
	identifier, so callers see a typed identifier rather than an untrusted
	``str``.
	"""
	if not isinstance(name, str) or not _IDENT_RE.match(name) or name not in _RLS_ALLOWLIST:
		raise ValueError(
			f"refusing to splice unknown / malformed table name into RLS DDL: {name!r}"
		)
	return quoted_name(name, quote=True)


def _is_postgres() -> bool:
	bind = op.get_bind()
	return bind.dialect.name == "postgresql"


def _install_rls_if_postgres() -> None:
	# Validate every table name first so a malicious tuple raises before
	# any SQL is emitted (audit J-01 acceptance criterion).
	tier_a = [_assert_known_table(t) for t in _RLS_TABLES_TENANT_NULLABLE]
	tier_b = [_assert_known_table(t) for t in _RLS_TABLES_TENANT_REQUIRED]
	domains = _assert_known_table("jtbd_domains")
	if not _is_postgres():
		return
	for table in tier_a:
		op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
		op.execute(
			f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ("
			" tenant_id IS NULL"
			" OR tenant_id = current_setting('app.tenant_id', true)"
			" OR current_setting('app.elevated', true) = 'true'"
			");"
		)
		op.execute(
			f"CREATE POLICY {table}_write ON {table} FOR ALL USING ("
			" tenant_id = current_setting('app.tenant_id', true)"
			" OR current_setting('app.elevated', true) = 'true'"
			") WITH CHECK ("
			" tenant_id = current_setting('app.tenant_id', true)"
			" OR current_setting('app.elevated', true) = 'true'"
			");"
		)
	for table in tier_b:
		op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
		op.execute(
			f"CREATE POLICY {table}_tenant_iso ON {table} FOR ALL USING ("
			" tenant_id = current_setting('app.tenant_id', true)"
			" OR current_setting('app.elevated', true) = 'true'"
			") WITH CHECK ("
			" tenant_id = current_setting('app.tenant_id', true)"
			" OR current_setting('app.elevated', true) = 'true'"
			");"
		)
	# jtbd_domains is hub-only catalogue (no tenant_id column at all);
	# RLS is enabled with read-open / write-elevated to keep the contract
	# uniform.
	op.execute(f"ALTER TABLE {domains} ENABLE ROW LEVEL SECURITY;")
	op.execute(
		f"CREATE POLICY {domains}_read ON {domains} FOR SELECT USING (true);"
	)
	op.execute(
		f"CREATE POLICY {domains}_write ON {domains} FOR ALL USING ("
		" current_setting('app.elevated', true) = 'true'"
		") WITH CHECK ("
		" current_setting('app.elevated', true) = 'true'"
		");"
	)


def _drop_rls_if_postgres() -> None:
	tier_a = [_assert_known_table(t) for t in _RLS_TABLES_TENANT_NULLABLE]
	tier_b = [_assert_known_table(t) for t in _RLS_TABLES_TENANT_REQUIRED]
	domains = _assert_known_table("jtbd_domains")
	if not _is_postgres():
		return
	op.execute(f"DROP POLICY IF EXISTS {domains}_write ON {domains};")
	op.execute(f"DROP POLICY IF EXISTS {domains}_read ON {domains};")
	op.execute(f"ALTER TABLE {domains} DISABLE ROW LEVEL SECURITY;")
	for table in tier_b:
		op.execute(f"DROP POLICY IF EXISTS {table}_tenant_iso ON {table};")
		op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
	for table in tier_a:
		op.execute(f"DROP POLICY IF EXISTS {table}_write ON {table};")
		op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table};")
		op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
