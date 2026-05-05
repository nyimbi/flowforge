"""Integration test #5: designer authoring round-trip.

Simulates the designer workflow:

* Load a draft def into the runtime registry.
* Edit it (here, by validating against the compiler).
* Run the in-process simulator across a sequence of events.
* Publish the result.
* Start an instance from the published version via the runtime API.
"""

from __future__ import annotations

import pytest
from flowforge.compiler import validate
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.replay.simulator import simulate

pytestmark = pytest.mark.asyncio


async def test_validate_simulate_publish_then_start(
	claim_workflow_def: WorkflowDef,
) -> None:
	# 1. Validate the draft.
	report = validate(claim_workflow_def.model_dump(mode="json", exclude_none=True))
	assert report.ok, f"validation errors: {report.errors}"

	# 2. Run the simulator over a happy-path event sequence.
	events = [("submit", {}), ("approve", {})]
	result = await simulate(claim_workflow_def, events=events)
	assert result.terminal_state == "approved"
	assert result.fire_results[-1].terminal is True

	# 3. "Publish" — the in-memory engine binds to the def by key+version.
	published = WorkflowDef.model_validate(
		claim_workflow_def.model_dump(mode="json", exclude_none=True)
	)
	assert published.version == claim_workflow_def.version

	# 4. Start an instance from the published version.
	inst = new_instance(published)
	fr = await fire(published, inst, "submit", tenant_id="t-1")
	assert fr.matched_transition_id == "submit"
	assert fr.new_state == "review"


async def test_validator_rejects_unreachable_state(
	claim_workflow_def: WorkflowDef,
) -> None:
	"""A def with an unreachable state must surface as an error."""
	body = claim_workflow_def.model_dump(mode="json", exclude_none=True)
	body["states"].append({"name": "ghost", "kind": "manual_review"})
	report = validate(body)
	assert report.ok is False
	assert any("ghost" in e for e in report.errors)
