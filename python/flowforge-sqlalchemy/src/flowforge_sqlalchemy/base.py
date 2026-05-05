"""Declarative base + dialect-portable types.

The flowforge storage layer must compile under SQLite (tests, dev,
in-process replay) AND PostgreSQL (production hosts) without two
separate model files. This module centralises the type bridges:

* ``JsonB`` — ``JSONB`` on PostgreSQL, generic ``JSON`` on SQLite/MySQL.
* ``UuidStr`` — text-stored UUIDs (string serialisation everywhere; we
  match the engine's ``str(uuid.uuid4())`` representation).

The ``flowforge_metadata`` :class:`MetaData` carries a UMS-style naming
convention so Alembic auto-generates predictable constraint names.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import String, TypeDecorator

NAMING_CONVENTION: dict[str, str] = {
	"ix": "ix_%(table_name)s_%(column_0_N_name)s",
	"uq": "uq_%(table_name)s_%(column_0_N_name)s",
	"ck": "ck_%(table_name)s_%(constraint_name)s",
	"fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
	"pk": "pk_%(table_name)s",
}

flowforge_metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
	"""Declarative base shared by all flowforge ORM models."""

	metadata = flowforge_metadata


# Public alias so callers can use ``from flowforge_sqlalchemy import metadata``.
metadata = flowforge_metadata


class JsonB(TypeDecorator[Any]):
	"""``JSONB`` on PostgreSQL, ``JSON`` everywhere else.

	JSONB gives us indexable / containment-queryable JSON in production;
	SQLite tests fall back to the generic ``JSON`` type which serialises
	through ``json.dumps``.
	"""

	impl = JSON
	cache_ok = True

	def load_dialect_impl(self, dialect: Any) -> Any:
		if dialect.name == "postgresql":
			return dialect.type_descriptor(JSONB(none_as_null=True))
		return dialect.type_descriptor(JSON())


class UuidStr(TypeDecorator[str]):
	"""UUID stored as text. Stable across dialects.

	The flowforge engine uses ``str(uuid.uuid4())`` for IDs and never
	relies on driver-side UUID coercion, so a 36-char ``VARCHAR`` is the
	simplest portable choice.
	"""

	impl = String
	cache_ok = True

	def load_dialect_impl(self, dialect: Any) -> Any:
		return dialect.type_descriptor(String(36))
