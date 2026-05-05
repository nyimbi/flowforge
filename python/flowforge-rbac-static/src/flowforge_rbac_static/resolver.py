"""StaticRbac — read-only role/permission map.

Reads a config dict (or YAML/JSON file) shaped:

.. code-block:: yaml

    roles:
        clerk: [claim.create, claim.read]
    principals:
        alice: [clerk]
    permissions:
        - {name: claim.create, description: ...}

Implements :class:`flowforge.ports.RbacResolver`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowforge.ports import PermissionName, Principal, Scope


class CatalogDriftError(RuntimeError):
	"""Raised in strict mode when seeded permissions are not in the catalogue."""


class StaticRbac:
	def __init__(self, config: dict[str, Any], *, strict: bool = False) -> None:
		self._strict = strict
		self._role_perms: dict[str, set[str]] = {
			role: set(perms) for role, perms in (config.get("roles") or {}).items()
		}
		self._principal_roles: dict[str, set[str]] = {
			pid: set(roles) for pid, roles in (config.get("principals") or {}).items()
		}
		# Catalog: name -> description
		self._catalog: dict[str, str] = {}
		for entry in config.get("permissions") or []:
			self._catalog[entry["name"]] = entry.get("description", "")

	# -------------------------------------------------------------- ctors

	@classmethod
	def from_yaml(cls, path: str | Path, *, strict: bool = False) -> "StaticRbac":
		import yaml  # type: ignore[import-untyped]

		text = Path(path).read_text()
		return cls(yaml.safe_load(text) or {}, strict=strict)

	@classmethod
	def from_json(cls, path: str | Path, *, strict: bool = False) -> "StaticRbac":
		text = Path(path).read_text()
		return cls(json.loads(text), strict=strict)

	# ----------------------------------------------------- RbacResolver

	async def has_permission(
		self,
		principal: Principal,
		permission: PermissionName,
		scope: Scope,
	) -> bool:
		if principal.is_system:
			return True
		# Use either explicit principal_roles entry or the principal's roles tuple.
		roles = self._principal_roles.get(principal.user_id, set()) | set(principal.roles)
		for role in roles:
			if permission in self._role_perms.get(role, set()):
				return True
		return False

	async def list_principals_with(
		self,
		permission: PermissionName,
		scope: Scope,
	) -> list[Principal]:
		out: list[Principal] = []
		for pid, roles in self._principal_roles.items():
			if any(permission in self._role_perms.get(r, set()) for r in roles):
				out.append(Principal(user_id=pid, roles=tuple(roles)))
		return out

	async def register_permission(
		self,
		name: PermissionName,
		description: str,
		deprecated_aliases: list[str] | None = None,
	) -> None:
		self._catalog[name] = description

	async def assert_seed(self, names: list[PermissionName]) -> list[PermissionName]:
		missing = [n for n in names if n not in self._catalog]
		if missing and self._strict:
			raise CatalogDriftError(f"missing permissions: {missing}")
		return missing
