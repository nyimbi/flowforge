"""SettingsPort — runtime-mutable, signature-tracked configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SettingSpec:
	"""Schema for a setting row."""

	key: str
	description: str
	default: Any
	value_type: str  # "string" | "int" | "bool" | "json"
	requires_signoff: bool = False


@runtime_checkable
class SettingsPort(Protocol):
	"""Settings registry.

	All flowforge-owned keys MUST be namespaced ``flowforge.*`` to avoid
	collisions with host settings.
	"""

	async def get(self, key: str) -> Any:
		"""Read the current value (raises if unset and no default)."""

	async def set(self, key: str, value: Any, signed_by: str | None = None) -> None:
		"""Write a new value; *signed_by* required iff spec.requires_signoff."""

	async def register(self, spec: SettingSpec) -> None:
		"""Idempotent registration."""
