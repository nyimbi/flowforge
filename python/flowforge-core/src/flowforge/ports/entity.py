"""EntityAdapter Protocol + decorator-based registry.

Hosts declare per-entity adapters via ``@register_entity("claim")``. The
engine calls these for create / update / lookup / saga compensation.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class EntityAdapter(Protocol):
	"""One adapter per workflow ``subject_kind``.

	Methods are async because they typically wrap host service code that
	hits the database.
	"""

	compensations: dict[str, str]
	"""Mapping of compensation kind -> service method name."""

	async def create(self, session: Any, payload: dict[str, Any]) -> dict[str, Any]:
		"""Create the entity; return its dict projection."""
		...

	async def update(self, session: Any, id_: str, payload: dict[str, Any]) -> dict[str, Any]:
		"""Update *id_*; return the new dict projection."""
		...

	async def lookup(self, session: Any, id_: str) -> dict[str, Any]:
		"""Read the dict projection of *id_*."""
		...


class EntityRegistry:
	"""In-memory entity-adapter registry. Hosts push, engine reads."""

	def __init__(self) -> None:
		self._impls: dict[str, EntityAdapter] = {}

	def register(self, kind: str, adapter: EntityAdapter) -> None:
		"""Register *adapter* for *kind* (last write wins; idempotent on identity)."""
		self._impls[kind] = adapter

	def get(self, kind: str) -> EntityAdapter | None:
		"""Return the registered adapter for *kind* or ``None``."""
		return self._impls.get(kind)

	def list_kinds(self) -> list[str]:
		return sorted(self._impls.keys())


_GLOBAL_REGISTRY: EntityRegistry | None = None


def _registry() -> EntityRegistry:
	global _GLOBAL_REGISTRY
	if _GLOBAL_REGISTRY is None:
		_GLOBAL_REGISTRY = EntityRegistry()
	return _GLOBAL_REGISTRY


def register_entity(kind: str):
	"""Class decorator: ``@register_entity("claim")`` on a class registers an instance."""

	def _decorator(cls: type[T]) -> type[T]:
		_registry().register(kind, cls())  # type: ignore[arg-type]
		return cls

	return _decorator
