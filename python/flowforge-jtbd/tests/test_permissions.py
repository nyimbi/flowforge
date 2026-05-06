"""Tests for flowforge_jtbd.permissions — E-19 RBAC seeds."""

from __future__ import annotations

import asyncio
from typing import Any

from flowforge_jtbd.permissions import (
	CURATOR_ROLE,
	JTBD_PERMISSION_NAMES,
	JTBD_PERMISSIONS,
	JTBD_ROLES,
	REVIEWER_ROLE,
	USER_ROLE,
	PermissionDef,
	RoleDef,
	permissions_for_role,
	seed_jtbd_permissions,
)


def _run(coro: Any) -> Any:
	return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Permission catalog
# ---------------------------------------------------------------------------


def test_eight_permissions_defined() -> None:
	assert len(JTBD_PERMISSIONS) == 8


def test_all_names_unique() -> None:
	names = [p.name for p in JTBD_PERMISSIONS]
	assert len(names) == len(set(names))


def test_all_names_start_with_jtbd_prefix() -> None:
	for p in JTBD_PERMISSIONS:
		assert p.name.startswith("jtbd."), f"{p.name!r} missing jtbd. prefix"


def test_permission_names_frozenset_matches_catalog() -> None:
	assert JTBD_PERMISSION_NAMES == {p.name for p in JTBD_PERMISSIONS}


def test_required_permissions_present() -> None:
	names = JTBD_PERMISSION_NAMES
	for required in ("jtbd.read", "jtbd.write", "jtbd.publish", "jtbd.fork",
	                  "jtbd.review", "jtbd.approve", "jtbd.archive", "jtbd.compose"):
		assert required in names, f"missing {required!r}"


def test_review_permission_has_deprecated_aliases() -> None:
	review = next(p for p in JTBD_PERMISSIONS if p.name == "jtbd.review")
	assert "jtbd_editor.review" in review.deprecated_aliases
	assert "jtbd.approver" in review.deprecated_aliases


# ---------------------------------------------------------------------------
# Role archetypes
# ---------------------------------------------------------------------------


def test_three_roles_defined() -> None:
	assert len(JTBD_ROLES) == 3


def test_curator_has_write_publish_fork_archive() -> None:
	for perm in ("jtbd.write", "jtbd.publish", "jtbd.fork", "jtbd.archive"):
		assert perm in CURATOR_ROLE.permissions, f"curator missing {perm!r}"


def test_reviewer_cannot_write() -> None:
	assert "jtbd.write" not in REVIEWER_ROLE.permissions


def test_reviewer_has_review_and_approve() -> None:
	assert "jtbd.review" in REVIEWER_ROLE.permissions
	assert "jtbd.approve" in REVIEWER_ROLE.permissions


def test_user_has_read_and_compose_only() -> None:
	assert set(USER_ROLE.permissions) == {"jtbd.read", "jtbd.compose"}


def test_all_role_permissions_are_in_catalog() -> None:
	for role in JTBD_ROLES:
		for perm in role.permissions:
			assert perm in JTBD_PERMISSION_NAMES, (
				f"role {role.name!r} references unknown permission {perm!r}"
			)


# ---------------------------------------------------------------------------
# permissions_for_role
# ---------------------------------------------------------------------------


def test_permissions_for_curator_role() -> None:
	perms = permissions_for_role("jtbd.curator")
	assert "jtbd.write" in perms


def test_permissions_for_reviewer_role() -> None:
	perms = permissions_for_role("jtbd.reviewer")
	assert "jtbd.approve" in perms
	assert "jtbd.write" not in perms


def test_permissions_for_user_role() -> None:
	perms = permissions_for_role("jtbd.user")
	assert "jtbd.read" in perms
	assert "jtbd.write" not in perms


def test_unknown_role_raises_value_error() -> None:
	import pytest
	with pytest.raises(ValueError, match="Unknown JTBD role"):
		permissions_for_role("jtbd.nonexistent")


# ---------------------------------------------------------------------------
# seed_jtbd_permissions
# ---------------------------------------------------------------------------


class _FakeRbac:
	"""Minimal RbacResolver-compatible stub."""

	def __init__(self) -> None:
		self.registered: list[dict[str, Any]] = []

	async def register_permission(
		self,
		name: str,
		description: str,
		deprecated_aliases: list[str] | None = None,
	) -> None:
		self.registered.append({
			"name": name,
			"description": description,
			"deprecated_aliases": deprecated_aliases,
		})


def test_seed_registers_all_permissions() -> None:
	rbac = _FakeRbac()
	_run(seed_jtbd_permissions(rbac))

	registered_names = {r["name"] for r in rbac.registered}
	assert registered_names == JTBD_PERMISSION_NAMES


def test_seed_passes_deprecated_aliases() -> None:
	rbac = _FakeRbac()
	_run(seed_jtbd_permissions(rbac))

	review_entry = next(r for r in rbac.registered if r["name"] == "jtbd.review")
	assert "jtbd_editor.review" in review_entry["deprecated_aliases"]


def test_seed_idempotent_two_runs() -> None:
	rbac = _FakeRbac()
	_run(seed_jtbd_permissions(rbac))
	_run(seed_jtbd_permissions(rbac))

	# Both calls registered; idempotency contract is on the RbacResolver impl.
	# Our seeder just calls register_permission unconditionally.
	assert len(rbac.registered) == len(JTBD_PERMISSIONS) * 2


def test_seed_rejects_none_rbac() -> None:
	import pytest
	with pytest.raises(AssertionError):
		_run(seed_jtbd_permissions(None))  # type: ignore[arg-type]


def test_seed_rejects_rbac_without_method() -> None:
	import pytest
	with pytest.raises(AssertionError, match="register_permission"):
		_run(seed_jtbd_permissions(object()))
