"""JTBD RBAC permission seeds — curator / reviewer / user roles (E-19).

Defines the canonical JTBD permission catalogue and the three role
archetypes from ``docs/flowforge-evolution.md`` §7 and §22.2.

**Roles**

==========  ==================================================================
Role        Permissions granted
==========  ==================================================================
curator     write, publish, fork, archive — full lifecycle management.
reviewer    review, approve — read + gate approval (no write authority).
user        read, compose — browse and compose bundles; no mutation rights.
==========  ==================================================================

**Permission names** follow the ``jtbd.<verb>`` convention so they live in a
distinct namespace from workflow permissions (``claim.submit`` etc.) and
can be toggled independently in SpiceDB / UMS IAM.

Usage::

    import flowforge.config as config
    from flowforge_jtbd.permissions import seed_jtbd_permissions

    await seed_jtbd_permissions(config.rbac)

The seeder is idempotent — re-running after a deploy that already seeded
is safe (the ``RbacResolver.register_permission`` contract is idempotent).

To verify catalogue coverage after a deploy::

    missing = await config.rbac.assert_seed(JTBD_PERMISSION_NAMES)
    assert not missing, f"missing from catalogue: {missing}"
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Coroutine


# ---------------------------------------------------------------------------
# Permission definitions
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PermissionDef:
	"""A single JTBD permission entry."""

	name: str
	description: str
	deprecated_aliases: tuple[str, ...] = ()


#: Ordered permission catalogue — the source of truth.
JTBD_PERMISSIONS: tuple[PermissionDef, ...] = (
	PermissionDef(
		name="jtbd.read",
		description="Browse and read JTBD spec versions.",
	),
	PermissionDef(
		name="jtbd.compose",
		description="Compose JTBDs into a bundle configuration (read-only authoring).",
	),
	PermissionDef(
		name="jtbd.write",
		description="Create and edit JTBD spec versions.",
		deprecated_aliases=("jtbd_editor.write",),
	),
	PermissionDef(
		name="jtbd.publish",
		description="Publish a JTBD spec version to the registry.",
		deprecated_aliases=("jtbd_editor.publish",),
	),
	PermissionDef(
		name="jtbd.fork",
		description="Fork an upstream JTBD library into a tenant-scoped copy.",
		deprecated_aliases=("jtbd_editor.fork",),
	),
	PermissionDef(
		name="jtbd.review",
		description="Submit a review comment or approval decision on a JTBD.",
		deprecated_aliases=("jtbd_editor.review", "jtbd.approver"),
	),
	PermissionDef(
		name="jtbd.approve",
		description="Approve a reviewed JTBD spec version (gating publication).",
	),
	PermissionDef(
		name="jtbd.archive",
		description="Archive or deprecate a JTBD spec version.",
	),
)

#: Flat set of canonical permission names for quick membership testing.
JTBD_PERMISSION_NAMES: frozenset[str] = frozenset(p.name for p in JTBD_PERMISSIONS)


# ---------------------------------------------------------------------------
# Role archetypes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RoleDef:
	"""JTBD role archetype — name + the permissions it grants."""

	name: str
	description: str
	permissions: tuple[str, ...]


#: Curator — full lifecycle authority (write/publish/fork/archive).
CURATOR_ROLE = RoleDef(
	name="jtbd.curator",
	description="Curator: full lifecycle authority over JTBD specs.",
	permissions=(
		"jtbd.read",
		"jtbd.compose",
		"jtbd.write",
		"jtbd.publish",
		"jtbd.fork",
		"jtbd.archive",
	),
)

#: Reviewer — read + approval gate (no mutation rights).
REVIEWER_ROLE = RoleDef(
	name="jtbd.reviewer",
	description="Reviewer: can read, review, and approve JTBD specs.",
	permissions=(
		"jtbd.read",
		"jtbd.review",
		"jtbd.approve",
	),
)

#: User — browse and compose only.
USER_ROLE = RoleDef(
	name="jtbd.user",
	description="User: can browse and compose JTBD bundles.",
	permissions=(
		"jtbd.read",
		"jtbd.compose",
	),
)

#: Canonical three-role set (order: curator → reviewer → user).
JTBD_ROLES: tuple[RoleDef, ...] = (CURATOR_ROLE, REVIEWER_ROLE, USER_ROLE)


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------


async def seed_jtbd_permissions(rbac: object) -> None:
	"""Idempotently register all JTBD permissions in *rbac*.

	*rbac* must implement :class:`~flowforge.ports.rbac.RbacResolver` —
	specifically its ``register_permission(name, description,
	deprecated_aliases)`` method.

	Raises :exc:`AttributeError` if *rbac* does not have the expected method.

	Example (wired at host startup)::

	    import flowforge.config as config
	    from flowforge_jtbd.permissions import seed_jtbd_permissions

	    await seed_jtbd_permissions(config.rbac)
	"""
	assert rbac is not None, "rbac must not be None"
	register: Any = getattr(rbac, "register_permission", None)
	assert callable(register), (
		f"{type(rbac).__name__!r} does not implement register_permission(); "
		"ensure it satisfies the RbacResolver protocol"
	)

	for perm in JTBD_PERMISSIONS:
		await register(
			perm.name,
			perm.description,
			deprecated_aliases=list(perm.deprecated_aliases) or None,
		)


def permissions_for_role(role_name: str) -> tuple[str, ...]:
	"""Return the permission names for a named JTBD role archetype.

	:param role_name: One of ``"jtbd.curator"``, ``"jtbd.reviewer"``,
	  ``"jtbd.user"``.
	:raises ValueError: for an unknown role name.
	"""
	for role in JTBD_ROLES:
		if role.name == role_name:
			return role.permissions
	raise ValueError(
		f"Unknown JTBD role {role_name!r}. "
		f"Known roles: {[r.name for r in JTBD_ROLES]}"
	)


__all__ = [
	"CURATOR_ROLE",
	"JTBD_PERMISSION_NAMES",
	"JTBD_PERMISSIONS",
	"JTBD_ROLES",
	"PermissionDef",
	"REVIEWER_ROLE",
	"RoleDef",
	"USER_ROLE",
	"permissions_for_role",
	"seed_jtbd_permissions",
]
