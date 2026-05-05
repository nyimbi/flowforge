"""Integration test #10: parallel regions + token table.

The flowforge DSL supports ``parallel_fork`` / ``parallel_join`` state
kinds. The engine doesn't itself manage tokens (it operates on a
single-state instance), but it does record per-region context flags so
that join guards can fire deterministically once both regions have
reached their barriers.

This test:

* Defines a workflow with two regions.
* Fires events that advance each region independently.
* Verifies that the join transition is gated until both region flags
  are true (proxy for the token-set being empty).
* Persists tokens through the ``WorkflowInstanceToken`` table so the
  storage adapter contract is exercised.
"""

from __future__ import annotations

import uuid

import pytest
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge_sqlalchemy import WorkflowInstance, WorkflowInstanceToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_parallel_regions_join_after_both_complete(
	session_factory: async_sessionmaker[AsyncSession],
	tenant_id: str,
	parallel_workflow_def: WorkflowDef,
) -> None:
	wd = parallel_workflow_def
	instance_id = str(uuid.uuid4())

	async with session_factory() as session:
		session.add(
			WorkflowInstance(
				id=instance_id,
				tenant_id=tenant_id,
				def_key=wd.key,
				def_version=wd.version,
				subject_kind=wd.subject_kind,
				state=wd.initial_state,
				terminal=False,
				context={},
			)
		)
		# Persist one token per region as the host would on fork.
		for region, state in [("region-a", "region_a"), ("region-b", "region_b")]:
			session.add(
				WorkflowInstanceToken(
					id=str(uuid.uuid4()),
					tenant_id=tenant_id,
					instance_id=instance_id,
					region=region,
					state=state,
					context={},
				)
			)
		await session.commit()

	inst = new_instance(wd, instance_id=instance_id)

	# Walk the workflow: start_a -> start_b -> done_a -> done_b -> join.
	for ev in ["start_a", "start_b", "done_a", "done_b"]:
		fr = await fire(wd, inst, ev, tenant_id=tenant_id)
		assert fr.matched_transition_id is not None, f"{ev} should match"

	# Both region flags are now set -> join must succeed.
	join_fr = await fire(wd, inst, "join", tenant_id=tenant_id)
	assert join_fr.matched_transition_id == "join"
	assert join_fr.terminal is True
	assert inst.state == "joined"

	# Token rows are still in storage — host typically removes them after join,
	# but persistence is what we're testing here.
	async with session_factory() as session:
		tokens = (
			await session.scalars(
				select(WorkflowInstanceToken).where(
					WorkflowInstanceToken.instance_id == instance_id
				)
			)
		).all()
		assert {t.region for t in tokens} == {"region-a", "region-b"}


async def test_join_blocked_when_one_region_unfinished(
	parallel_workflow_def: WorkflowDef,
) -> None:
	"""If only one region completes, the join guard must fail."""
	wd = parallel_workflow_def
	inst = new_instance(wd)

	# Walk only region A through.
	for ev in ["start_a", "start_b", "done_a"]:
		await fire(wd, inst, ev, tenant_id="t-1")

	# region_b_done is False -> join guard fails -> no transition.
	# But state is now region_a_done; we need to be in region_b_done to attempt
	# join. Force the state and attempt the join; guard should reject.
	inst.state = "region_b_done"
	inst.context["region_b_done"] = False  # explicit
	fr = await fire(wd, inst, "join", tenant_id="t-1")
	assert fr.matched_transition_id is None
	assert inst.state == "region_b_done"  # unchanged
