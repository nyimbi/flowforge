"""E-73 jtbd-hub RBAC scaffold.

NOT YET WIRED. ``app.py`` still uses the comma-separated admin-token
list shipped in E-58 (JH-04 rotation + audit-log). This module carries
the planned API surface so callers and tests can begin building against
it. See ``framework/docs/design/E-73-jtbd-hub-rbac.md``.

Importing this module is safe; it has no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class Permission(str, Enum):
	"""Atomic permissions enforced by the hub admin/runtime routes."""

	# Package lifecycle.
	PACKAGE_PUBLISH = "package.publish"
	PACKAGE_UNPUBLISH = "package.unpublish"
	PACKAGE_INSTALL = "package.install"

	# Admin surface.
	ADMIN_READ = "admin.read"
	ADMIN_WRITE = "admin.write"

	# Audit / read-only review.
	AUDIT_READ = "audit.read"


class Role(str, Enum):
	"""Named bundles of permissions."""

	HUB_ADMIN = "hub_admin"
	PACKAGE_PUBLISHER = "package_publisher"
	PACKAGE_CONSUMER = "package_consumer"
	AUDITOR = "auditor"


# Static role -> permission mapping. Frozenset so callers can rely on
# hashable, immutable membership.
_ROLE_PERMS: dict[Role, frozenset[Permission]] = {
	Role.HUB_ADMIN: frozenset(
		[
			Permission.PACKAGE_PUBLISH,
			Permission.PACKAGE_UNPUBLISH,
			Permission.PACKAGE_INSTALL,
			Permission.ADMIN_READ,
			Permission.ADMIN_WRITE,
			Permission.AUDIT_READ,
		]
	),
	Role.PACKAGE_PUBLISHER: frozenset(
		[Permission.PACKAGE_PUBLISH, Permission.PACKAGE_INSTALL]
	),
	Role.PACKAGE_CONSUMER: frozenset([Permission.PACKAGE_INSTALL]),
	Role.AUDITOR: frozenset([Permission.AUDIT_READ, Permission.ADMIN_READ]),
}


def role_permissions(role: Role) -> frozenset[Permission]:
	return _ROLE_PERMS[role]


@dataclass(frozen=True)
class Principal:
	"""An authenticated identity for a hub request.

	``principal_kind`` distinguishes per-user identities ("user") from
	the legacy shared-admin-token bridge ("legacy_admin"). Audit events
	record the kind so operators can track migration progress.
	"""

	user_id: str
	roles: tuple[Role, ...] = field(default_factory=tuple)
	principal_kind: str = "user"

	def has(self, permission: Permission) -> bool:
		for role in self.roles:
			if permission in _ROLE_PERMS.get(role, frozenset()):
				return True
		return False


class PrincipalExtractor(Protocol):
	"""Pluggable identity extraction.

	Default impl (in E-73 phase 2) reads ``Authorization: Bearer ...``
	and verifies via ``flowforge_signing_kms``. Hosts can override to
	plug a custom session store. Returns ``None`` for unauthenticated
	requests.
	"""

	def __call__(self, request: object) -> Principal | None: ...


# Sentinel for the legacy admin-token bridge. Hosts using
# ``create_app(admin_token=...)`` get this synthetic Principal until the
# bridge is removed (one-minor deprecation per E-73 §3).
LEGACY_ADMIN_PRINCIPAL = Principal(
	user_id="legacy_admin",
	roles=(Role.HUB_ADMIN,),
	principal_kind="legacy_admin",
)
