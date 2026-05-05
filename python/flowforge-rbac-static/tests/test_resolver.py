"""StaticRbac tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowforge.ports import Principal, RbacResolver, Scope
from flowforge_rbac_static import CatalogDriftError, StaticRbac


pytestmark = pytest.mark.asyncio


CONFIG = {
	"roles": {
		"intake_clerk": ["claim.create", "claim.read"],
		"supervisor": ["claim.create", "claim.read", "claim.approve"],
	},
	"principals": {
		"alice": ["intake_clerk"],
		"bob": ["supervisor"],
	},
	"permissions": [
		{"name": "claim.create", "description": "Create a new claim"},
		{"name": "claim.read", "description": "Read a claim"},
		{"name": "claim.approve", "description": "Approve a claim"},
	],
}


async def test_satisfies_protocol() -> None:
	r = StaticRbac(CONFIG)
	assert isinstance(r, RbacResolver)


async def test_has_permission_via_principal_roles_map() -> None:
	r = StaticRbac(CONFIG)
	scope = Scope(tenant_id="t-1")
	assert await r.has_permission(Principal(user_id="alice"), "claim.create", scope) is True
	assert await r.has_permission(Principal(user_id="alice"), "claim.approve", scope) is False
	assert await r.has_permission(Principal(user_id="bob"), "claim.approve", scope) is True


async def test_has_permission_via_principal_roles_tuple() -> None:
	r = StaticRbac(CONFIG)
	scope = Scope(tenant_id="t-1")
	# carol isn't in principals map, but her Principal has the supervisor role
	assert await r.has_permission(
		Principal(user_id="carol", roles=("supervisor",)),
		"claim.approve",
		scope,
	) is True


async def test_system_principal_bypasses() -> None:
	r = StaticRbac({})
	scope = Scope(tenant_id="t-1")
	assert await r.has_permission(Principal(user_id="sys", is_system=True), "anything", scope) is True


async def test_list_principals_with() -> None:
	r = StaticRbac(CONFIG)
	scope = Scope(tenant_id="t-1")
	approvers = await r.list_principals_with("claim.approve", scope)
	assert {p.user_id for p in approvers} == {"bob"}

	creators = await r.list_principals_with("claim.create", scope)
	assert {p.user_id for p in creators} == {"alice", "bob"}


async def test_register_and_assert_seed() -> None:
	r = StaticRbac(CONFIG)
	missing = await r.assert_seed(["claim.create", "claim.delete"])
	assert missing == ["claim.delete"]

	await r.register_permission("claim.delete", "Soft-delete a claim")
	missing = await r.assert_seed(["claim.create", "claim.delete"])
	assert missing == []


async def test_strict_mode_raises_on_drift() -> None:
	r = StaticRbac(CONFIG, strict=True)
	with pytest.raises(CatalogDriftError):
		await r.assert_seed(["claim.delete"])


async def test_from_json_loader(tmp_path: Path) -> None:
	p = tmp_path / "rbac.json"
	p.write_text(json.dumps(CONFIG))
	r = StaticRbac.from_json(p)
	scope = Scope(tenant_id="t-1")
	assert await r.has_permission(Principal(user_id="bob"), "claim.approve", scope) is True


async def test_from_yaml_loader(tmp_path: Path) -> None:
	yaml = pytest.importorskip("yaml")
	p = tmp_path / "rbac.yaml"
	p.write_text(yaml.safe_dump(CONFIG))
	r = StaticRbac.from_yaml(p)
	scope = Scope(tenant_id="t-1")
	assert await r.has_permission(Principal(user_id="alice"), "claim.create", scope) is True
