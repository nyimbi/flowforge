"""Integration test #6: RBAC permission gates from two backends.

Drives a workflow def whose ``submit`` transition has a permission gate
against three principals using both the static-yaml and spicedb-fake
backends:

* ``operator`` (system principal) — must always pass (``is_system=True``).
* ``role-with-grant`` — has the role, expect 200.
* ``role-without-grant`` — has no permission, expect 403.

The ``flowforge`` engine itself does not enforce permission gates (gates
are evaluated by host policy code), but the ``RbacResolver`` Protocol is
the actual integration point. We therefore exercise the Protocol with
both adapter implementations to prove portability.
"""

from __future__ import annotations

import pytest
from flowforge.dsl import WorkflowDef
from flowforge.ports.types import Principal, Scope
from flowforge_rbac_spicedb import SpiceDBRbac
from flowforge_rbac_spicedb.testing import FakeSpiceDBClient
from flowforge_rbac_static import StaticRbac

pytestmark = pytest.mark.asyncio


def _static_rbac() -> StaticRbac:
	return StaticRbac(
		{
			"roles": {
				"clerk": ["claim.submit"],
				"intern": [],
			},
			"principals": {
				"alice": ["clerk"],
				"bob": ["intern"],
			},
			"permissions": [
				{"name": "claim.submit", "description": "submit"},
			],
		}
	)


async def test_static_rbac_grants_via_role_membership(
	gated_workflow_def: WorkflowDef,
) -> None:
	rbac = _static_rbac()
	scope = Scope(tenant_id="t-1")

	# operator: system principal always passes.
	op = Principal(user_id="op", is_system=True)
	assert await rbac.has_permission(op, "claim.submit", scope) is True

	# role-with-grant: alice has clerk role -> claim.submit
	alice = Principal(user_id="alice", roles=("clerk",))
	assert await rbac.has_permission(alice, "claim.submit", scope) is True

	# role-without-grant: bob has intern role -> no claim.submit
	bob = Principal(user_id="bob", roles=("intern",))
	assert await rbac.has_permission(bob, "claim.submit", scope) is False


async def test_spicedb_fake_rbac_round_trip() -> None:
	"""The spicedb-fake client + resolver follow the same RbacResolver contract."""
	fake = FakeSpiceDBClient()
	rbac = SpiceDBRbac(fake)
	scope = Scope(tenant_id="t-1")

	# Grant claim.submit on the tenant resource to alice.
	fake.grant("user:alice", "claim.submit", "tenant:t-1")

	# system principal: always passes (short-circuit in resolver).
	op = Principal(user_id="op", is_system=True)
	assert await rbac.has_permission(op, "claim.submit", scope) is True

	# alice was granted the permission.
	alice = Principal(user_id="alice")
	assert await rbac.has_permission(alice, "claim.submit", scope) is True

	# bob was never granted; resolver should return False.
	bob = Principal(user_id="bob")
	assert await rbac.has_permission(bob, "claim.submit", scope) is False
