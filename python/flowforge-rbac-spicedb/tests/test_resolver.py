"""SpiceDBRbac tests — driven by FakeSpiceDBClient (no live SpiceDB)."""

from __future__ import annotations

import pytest

from flowforge.ports import Principal, RbacResolver, Scope
from flowforge_rbac_spicedb import (
	CatalogDriftError,
	SpiceDBClientProtocol,
	SpiceDBRbac,
)
from flowforge_rbac_spicedb.testing import FakeSpiceDBClient


# Async tests get their mark applied individually so synchronous tests
# (Protocol checks, constructor guards) don't trigger pytest-asyncio
# warnings. asyncio_mode=auto in pyproject.toml does the work for us.


# --------------------------------------------------------------- fixtures


@pytest.fixture
def fake() -> FakeSpiceDBClient:
	return FakeSpiceDBClient()


@pytest.fixture
def rbac(fake: FakeSpiceDBClient) -> SpiceDBRbac:
	return SpiceDBRbac(fake)


# --------------------------------------------------------------- protocols


def test_fake_satisfies_client_protocol(fake: FakeSpiceDBClient) -> None:
	assert isinstance(fake, SpiceDBClientProtocol)


def test_rbac_satisfies_resolver_protocol(rbac: SpiceDBRbac) -> None:
	assert isinstance(rbac, RbacResolver)


# --------------------------------------------------------------- has_permission


async def test_has_permission_hits_check_rpc(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	scope = Scope(tenant_id="t-1")
	fake.grant("user:alice", "claim.create", "tenant:t-1")

	assert await rbac.has_permission(Principal(user_id="alice"), "claim.create", scope) is True
	assert await rbac.has_permission(Principal(user_id="alice"), "claim.approve", scope) is False
	assert fake.check_calls == 2


async def test_has_permission_uses_resource_kind_when_present(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	scope = Scope(tenant_id="t-1", resource_id="c-42", resource_kind="claim")
	fake.grant("user:alice", "claim.update", "claim:c-42")

	assert await rbac.has_permission(
		Principal(user_id="alice"), "claim.update", scope
	) is True
	# A claim-scoped grant must not leak to tenant scope.
	tenant_scope = Scope(tenant_id="t-1")
	assert await rbac.has_permission(
		Principal(user_id="alice"), "claim.update", tenant_scope
	) is False


async def test_system_principal_short_circuits_rpc(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	scope = Scope(tenant_id="t-1")
	assert await rbac.has_permission(
		Principal(user_id="sys", is_system=True), "anything", scope
	) is True
	assert fake.check_calls == 0


async def test_subject_object_type_overridable(fake: FakeSpiceDBClient) -> None:
	rbac = SpiceDBRbac(fake, subject_object_type="agent")
	scope = Scope(tenant_id="t-1")
	fake.grant("agent:bot-1", "claim.read", "tenant:t-1")
	assert await rbac.has_permission(
		Principal(user_id="bot-1"), "claim.read", scope
	) is True


# --------------------------------------------------------------- list_principals_with


async def test_list_principals_with_streams_lookup(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	scope = Scope(tenant_id="t-1")
	fake.grant("user:alice", "claim.approve", "tenant:t-1")
	fake.grant("user:bob", "claim.approve", "tenant:t-1")
	fake.grant("user:carol", "claim.read", "tenant:t-1")

	principals = await rbac.list_principals_with("claim.approve", scope)
	assert {p.user_id for p in principals} == {"alice", "bob"}
	assert fake.lookup_calls == 1


async def test_list_principals_with_empty_when_no_grants(
	rbac: SpiceDBRbac,
) -> None:
	scope = Scope(tenant_id="t-1")
	assert await rbac.list_principals_with("claim.delete", scope) == []


# --------------------------------------------------------------- catalogue


async def test_register_permission_writes_relation(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	await rbac.register_permission("claim.create", "Create a new claim")
	assert fake.write_calls == 1
	# The catalogue is queryable via assert_seed.
	missing = await rbac.assert_seed(["claim.create"])
	assert missing == []


async def test_register_permission_records_aliases(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	await rbac.register_permission(
		"claim.approve",
		"Approve a claim",
		deprecated_aliases=["claim.signoff"],
	)
	# The single RPC carries both the canonical name and the alias updates.
	assert fake.write_calls == 1
	missing = await rbac.assert_seed(["claim.approve"])
	assert missing == []


async def test_assert_seed_returns_missing(
	fake: FakeSpiceDBClient, rbac: SpiceDBRbac
) -> None:
	await rbac.register_permission("claim.create", "")
	missing = await rbac.assert_seed(["claim.create", "claim.delete"])
	assert missing == ["claim.delete"]


async def test_assert_seed_strict_raises(
	fake: FakeSpiceDBClient,
) -> None:
	rbac = SpiceDBRbac(fake, strict=True)
	with pytest.raises(CatalogDriftError):
		await rbac.assert_seed(["claim.delete"])


async def test_assert_seed_strict_silent_when_present(
	fake: FakeSpiceDBClient,
) -> None:
	rbac = SpiceDBRbac(fake, strict=True)
	await rbac.register_permission("claim.create", "")
	# Should not raise.
	missing = await rbac.assert_seed(["claim.create"])
	assert missing == []


async def test_schema_prefix_isolates_catalogues(
	fake: FakeSpiceDBClient,
) -> None:
	r1 = SpiceDBRbac(fake, schema_prefix="app-a")
	r2 = SpiceDBRbac(fake, schema_prefix="app-b")
	await r1.register_permission("claim.create", "")
	# Distinct catalogue object => app-b sees nothing.
	assert await r2.assert_seed(["claim.create"]) == ["claim.create"]
	assert await r1.assert_seed(["claim.create"]) == []


# --------------------------------------------------------------- guards


def test_constructor_rejects_empty_prefix(fake: FakeSpiceDBClient) -> None:
	with pytest.raises(AssertionError):
		SpiceDBRbac(fake, schema_prefix="")
