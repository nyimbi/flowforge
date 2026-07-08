"""Generic SQLAlchemy ORM implementation of ``flowforge.ports.EntityAdapter``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from flowforge.ports.entity import EntityAdapter
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession


class EntityNotFound(KeyError):
	"""Raised when an ORM entity row cannot be found."""

	def __init__(self, model_name: str, id_: str) -> None:
		self.model_name = model_name
		self.id = id_
		super().__init__(f"{model_name} entity {id_!r} not found")


class SqlAlchemyEntityAdapter:
	"""CRUD adapter for simple SQLAlchemy ORM entities.

	The flowforge engine supplies the active storage session. This adapter
	therefore flushes changes but leaves commit/rollback ownership with the
	host transaction.
	"""

	compensations: dict[str, str]

	def __init__(
		self,
		model: type[Any],
		*,
		id_field: str = "id",
		writable_fields: Iterable[str] | None = None,
		readable_fields: Iterable[str] | None = None,
		compensations: dict[str, str] | None = None,
		reject_unknown_fields: bool = True,
	) -> None:
		mapper = inspect(model)
		column_names = {prop.key for prop in mapper.column_attrs}
		if id_field not in column_names:
			raise ValueError(f"{model.__name__} has no mapped id field {id_field!r}")

		self._model = model
		self._model_name = model.__name__
		self._id_field = id_field
		self._columns = frozenset(column_names)
		self._writable = (
			frozenset(writable_fields)
			if writable_fields is not None
			else self._columns
		)
		self._readable = (
			tuple(readable_fields)
			if readable_fields is not None
			else tuple(prop.key for prop in mapper.column_attrs)
		)
		unknown_writable = self._writable - self._columns
		unknown_readable = set(self._readable) - self._columns
		if unknown_writable:
			raise ValueError(f"unknown writable fields: {sorted(unknown_writable)!r}")
		if unknown_readable:
			raise ValueError(f"unknown readable fields: {sorted(unknown_readable)!r}")
		self._reject_unknown = reject_unknown_fields
		self.compensations = dict(compensations or {})

	async def create(self, session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
		"""Create an ORM row and return its dict projection."""
		values = self._payload_values(payload, allow_id=True)
		row = self._model(**values)
		session.add(row)
		await session.flush()
		return self._project(row)

	async def update(
		self,
		session: AsyncSession,
		id_: str,
		payload: dict[str, Any],
	) -> dict[str, Any]:
		"""Update an ORM row and return its dict projection."""
		if self._id_field in payload:
			raise ValueError(f"{self._id_field!r} cannot be updated")
		row = await self._get(session, id_)
		for key, value in self._payload_values(payload, allow_id=False).items():
			setattr(row, key, value)
		await session.flush()
		return self._project(row)

	async def lookup(self, session: AsyncSession, id_: str) -> dict[str, Any]:
		"""Read an ORM row by primary key and return its dict projection."""
		row = await self._get(session, id_)
		return self._project(row)

	async def delete(self, session: AsyncSession, id_: str) -> bool:
		"""Delete an ORM row by primary key. Returns ``True`` on hit."""
		row = await session.get(self._model, id_)
		if row is None:
			return False
		await session.delete(row)
		await session.flush()
		return True

	async def _get(self, session: AsyncSession, id_: str) -> Any:
		row = await session.get(self._model, id_)
		if row is None:
			raise EntityNotFound(self._model_name, id_)
		return row

	def _payload_values(
		self,
		payload: dict[str, Any],
		*,
		allow_id: bool,
	) -> dict[str, Any]:
		if not isinstance(payload, dict):
			raise TypeError("payload must be a dict")
		allowed = self._writable if allow_id else self._writable - {self._id_field}
		unknown = set(payload) - allowed
		if unknown and self._reject_unknown:
			raise ValueError(f"unknown entity fields: {sorted(unknown)!r}")
		return {key: value for key, value in payload.items() if key in allowed}

	def _project(self, row: Any) -> dict[str, Any]:
		return {key: getattr(row, key) for key in self._readable}


_: type[EntityAdapter] = SqlAlchemyEntityAdapter
