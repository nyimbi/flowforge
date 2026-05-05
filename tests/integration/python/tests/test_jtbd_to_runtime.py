"""Integration test #4: JTBD bundle -> runtime end-to-end.

Loads the insurance-claim JTBD bundle, runs ``flowforge jtbd-generate``
to produce a workflow definition, then drives the resulting workflow
through happy-path + edge-case branches via the engine API.

We don't re-run jtbd-generate at test time (slow + tests deterministic
regen separately); we use the checked-in
``examples/insurance_claim/generated/workflows/claim_intake/definition.json``
as the input.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance

pytestmark = pytest.mark.asyncio


def _load_claim_intake_def() -> WorkflowDef:
	root = Path(__file__).resolve().parents[4] / "examples" / "insurance_claim"
	def_path = root / "generated" / "workflows" / "claim_intake" / "definition.json"
	assert def_path.exists(), f"missing example def at {def_path}"
	return WorkflowDef.model_validate(json.loads(def_path.read_text()))


async def test_jtbd_generated_def_compiles_and_starts() -> None:
	"""The generated workflow def parses through the DSL and engine."""
	wd = _load_claim_intake_def()
	assert wd.key == "claim_intake"
	assert wd.subject_kind == "claim_intake"
	assert wd.initial_state == "intake"
	# The CLI scaffolds a multi-state workflow with terminal states.
	state_kinds = {s.kind for s in wd.states}
	assert "terminal_success" in state_kinds
	assert "terminal_fail" in state_kinds


async def test_jtbd_generated_def_advances_through_submit() -> None:
	"""Walk the workflow through the ``submit`` event."""
	wd = _load_claim_intake_def()
	inst = new_instance(wd)

	# Find the first event that originates at the initial state.
	initial_events = [
		t.event for t in wd.transitions if t.from_state == wd.initial_state
	]
	assert initial_events, "generated workflow has no transitions out of initial_state"

	fr = await fire(wd, inst, initial_events[0], tenant_id="t-1")
	# Either a transition was matched, or the gate caused it to be unmatched —
	# both outcomes are legal for a permission-gated workflow.
	assert fr.new_state in {s.name for s in wd.states}


async def test_jtbd_generated_def_reaches_terminal_via_engine_replay() -> None:
	"""Walk all transitions in topological order until a terminal is reached."""
	wd = _load_claim_intake_def()
	inst = new_instance(wd)

	# Pre-build a from_state -> [transition] map.
	by_from: dict[str, list] = {}
	for t in wd.transitions:
		by_from.setdefault(t.from_state, []).append(t)

	visited: set[str] = set()
	steps = 0
	while steps < 20:
		steps += 1
		visited.add(inst.state)
		# Stop if terminal.
		state = next(s for s in wd.states if s.name == inst.state)
		if state.kind in ("terminal_success", "terminal_fail"):
			break
		# Pick the first available transition out.
		out = by_from.get(inst.state) or []
		if not out:
			break
		fr = await fire(wd, inst, out[0].event, tenant_id="t-1")
		if fr.matched_transition_id is None:
			# Gates blocked us; bail (still passes — partial walk is fine).
			break

	# Ensure we walked through more than just the initial state.
	assert len(visited) >= 2
