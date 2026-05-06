"""SQLAlchemy 2.x ORM models for the JTBD storage tables.

Six tables back the JTBD layer:

* ``jtbd_libraries`` — one row per ``(tenant_id, name)`` plus catalogue-
  tier rows where ``tenant_id IS NULL`` (hub-managed, globally
  readable).
* ``jtbd_domains`` — one row per domain (insurance, hr, gov, …);
  static metadata + regulator hints.
* ``jtbd_specs`` — versioned specs. Immutable on publish; the
  ``status`` column carries the lifecycle state machine.
* ``jtbd_compositions`` — one row per project bundle (a tenant's
  composed set of JTBDs).
* ``jtbd_compositions_pins`` — lockfile pins referencing
  ``jtbd_compositions`` and the resolved ``(version, spec_hash,
  source)`` of each JTBD.
* ``jtbd_lockfiles`` — generated lockfile rows; one per
  ``(composition_id, body_hash)``. Re-locking the same composition
  produces a new row, never an update.

The dialect-portable ``JsonB`` and ``UuidStr`` types are reused from
:mod:`flowforge_sqlalchemy.base`. Tenant_id columns use the same
``String(64)`` width as workflow tables to accept arbitrary tenant
identifiers (UUID strings, slugs, ``"tenant-test"``, etc.) — the RLS
policy does the comparison at the GUC level.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from flowforge_sqlalchemy.base import Base, JsonB, UuidStr
from sqlalchemy import (
	DateTime,
	ForeignKey,
	Index,
	Integer,
	String,
	Text,
	UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

JtbdLibraryStatus = Literal["active", "archived", "deprecated"]
JtbdSpecRowStatus = Literal[
	"draft", "in_review", "published", "deprecated", "archived"
]


def _utcnow() -> datetime:
	"""Default factory for timezone-aware UTC ``DateTime`` columns."""
	return datetime.now(timezone.utc)


class JtbdLibrary(Base):
	"""One JTBD library, scoped per tenant or as a catalogue-tier row.

	A catalogue-tier row has ``tenant_id IS NULL``; the marketplace
	publish flow inserts those, and tenants ``flowforge jtbd fork`` them
	to land tenant-scoped copies. The fork pointer is recorded via
	``upstream_lib_id``; ``status`` cycles ``active → archived |
	deprecated``.
	"""

	__tablename__ = "jtbd_libraries"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str | None] = mapped_column(
		String(64), nullable=True, index=True
	)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	domain: Mapped[str] = mapped_column(String(128), nullable=False)
	upstream_lib_id: Mapped[str | None] = mapped_column(
		UuidStr(),
		ForeignKey("jtbd_libraries.id", ondelete="SET NULL"),
		nullable=True,
	)
	status: Mapped[str] = mapped_column(
		String(32), nullable=False, default="active"
	)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)

	__table_args__ = (
		UniqueConstraint(
			"tenant_id", "name", name="uq_jtbd_libraries_tenant_name"
		),
		Index("ix_jtbd_libraries_domain", "domain"),
	)


class JtbdDomain(Base):
	"""Per-domain registry row (insurance, hr, healthcare, …).

	Distinct from :class:`JtbdLibrary` — a domain is a *category* and
	carries shared metadata that rule packs, validators, and the
	editor's library picker all read. Multiple libraries can sit under
	one domain (insurance / claims, insurance / underwriting, …).
	"""

	__tablename__ = "jtbd_domains"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
	display_name: Mapped[str] = mapped_column(String(255), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	regulator_hints: Mapped[list[Any]] = mapped_column(
		JsonB(), nullable=False, default=list
	)
	default_compliance: Mapped[list[Any]] = mapped_column(
		JsonB(), nullable=False, default=list
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)


class JtbdSpecRow(Base):
	"""One versioned JTBD spec.

	The ``spec`` JSONB column carries the canonical body that
	:class:`flowforge_jtbd.dsl.JtbdSpec` round-trips into. ``spec_hash``
	is the precomputed sha256 of the canonical JSON of that body and
	is the column the lockfile + verifier compare against. Immutable
	on publish — the storage layer enforces append-only via the
	``status`` lifecycle.
	"""

	__tablename__ = "jtbd_specs"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str | None] = mapped_column(
		String(64), nullable=True, index=True
	)
	library_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("jtbd_libraries.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	jtbd_id: Mapped[str] = mapped_column(String(255), nullable=False)
	version: Mapped[str] = mapped_column(String(64), nullable=False)
	spec: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False)
	spec_hash: Mapped[str] = mapped_column(String(128), nullable=False)
	parent_version_id: Mapped[str | None] = mapped_column(
		UuidStr(),
		ForeignKey("jtbd_specs.id", ondelete="SET NULL"),
		nullable=True,
	)
	replaced_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
	status: Mapped[str] = mapped_column(
		String(32), nullable=False, default="draft"
	)
	created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	published_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
	published_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True), nullable=True
	)

	__table_args__ = (
		UniqueConstraint(
			"tenant_id",
			"library_id",
			"jtbd_id",
			"version",
			name="uq_jtbd_specs_tenant_library_jtbd_version",
		),
		Index("ix_jtbd_specs_lookup", "tenant_id", "jtbd_id", "status"),
		Index("ix_jtbd_specs_hash", "spec_hash"),
	)


class JtbdCompositionRow(Base):
	"""A project bundle (the unit a tenant ``publish``es)."""

	__tablename__ = "jtbd_compositions"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	project_package: Mapped[str] = mapped_column(String(255), nullable=False)
	description: Mapped[str | None] = mapped_column(Text, nullable=True)
	status: Mapped[str] = mapped_column(
		String(32), nullable=False, default="draft"
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
	)

	__table_args__ = (
		UniqueConstraint(
			"tenant_id", "name", name="uq_jtbd_compositions_tenant_name"
		),
	)


class JtbdCompositionPin(Base):
	"""One pin on a composition (composition × jtbd_id).

	Composite primary key keeps lookups O(1) per ``(composition_id,
	jtbd_id)`` and rejects duplicate pins at the database level.
	``source`` carries the resolution origin (``local`` for in-tree,
	``jtbd-hub`` for marketplace, ``git`` / ``filesystem`` for
	dev-time pulls).
	"""

	__tablename__ = "jtbd_compositions_pins"

	composition_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("jtbd_compositions.id", ondelete="CASCADE"),
		primary_key=True,
	)
	jtbd_id: Mapped[str] = mapped_column(String(255), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	version: Mapped[str] = mapped_column(String(64), nullable=False)
	spec_hash: Mapped[str] = mapped_column(String(128), nullable=False)
	source: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
	source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
	pinned_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)


class JtbdLockfileRow(Base):
	"""One lockfile snapshot.

	Append-only — re-running ``flowforge jtbd lock`` writes a new row.
	``body`` carries the JSON the CLI emits to ``jtbd.lock``;
	``body_hash`` is the precomputed canonical sha256 the verifier
	compares against. The unique constraint on ``(composition_id,
	body_hash)`` makes idempotent re-lock a no-op.
	"""

	__tablename__ = "jtbd_lockfiles"

	id: Mapped[str] = mapped_column(UuidStr(), primary_key=True)
	tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
	composition_id: Mapped[str] = mapped_column(
		UuidStr(),
		ForeignKey("jtbd_compositions.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	body_hash: Mapped[str] = mapped_column(String(128), nullable=False)
	body: Mapped[dict[str, Any]] = mapped_column(JsonB(), nullable=False)
	pin_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	generated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
	generated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, default=_utcnow
	)

	__table_args__ = (
		UniqueConstraint(
			"composition_id",
			"body_hash",
			name="uq_jtbd_lockfiles_composition_body_hash",
		),
	)


__all__ = [
	"JtbdCompositionPin",
	"JtbdCompositionRow",
	"JtbdDomain",
	"JtbdLibrary",
	"JtbdLibraryStatus",
	"JtbdLockfileRow",
	"JtbdSpecRow",
	"JtbdSpecRowStatus",
]
