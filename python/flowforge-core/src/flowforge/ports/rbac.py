"""RbacResolver port — permission checks + catalog seeding."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import PermissionName, Principal, Scope


@runtime_checkable
class RbacResolver(Protocol):
	"""Authorisation backend.

	Default impls ship in ``flowforge-rbac-static`` and
	``flowforge-rbac-spicedb``. Hosts may write their own (e.g. UMS
	wraps ``simulate_effective_access``).
	"""

	async def has_permission(
		self,
		principal: Principal,
		permission: PermissionName,
		scope: Scope,
	) -> bool:
		"""Return ``True`` iff *principal* may exercise *permission* in *scope*."""

	async def list_principals_with(
		self,
		permission: PermissionName,
		scope: Scope,
	) -> list[Principal]:
		"""Enumerate principals authorised for *permission* — used by reassign flows."""

	async def register_permission(
		self,
		name: PermissionName,
		description: str,
		deprecated_aliases: list[str] | None = None,
	) -> None:
		"""Idempotent permission catalogue registration."""

	async def assert_seed(self, names: list[PermissionName]) -> list[PermissionName]:
		"""Return the subset of *names* missing from the catalogue.

		In strict mode, implementations raise instead of returning a list.
		"""
