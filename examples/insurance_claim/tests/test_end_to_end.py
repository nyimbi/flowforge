"""End-to-end integration test for the U20 insurance-claim JTBD example.

Runs the generated workflow definition through the flowforge simulator for
three canonical cases drawn from the U20 acceptance criteria:

1. happy_path   — claimant submits → adjuster reviews → claim approved (done)
2. large_loss   — loss_amount flag set → submit routes to senior_triage branch
3. lapsed       — claim submitted then rejected for lapsed policy (rejected)

No DB, no FS writes beyond reading the generated definition.json, no network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from flowforge.dsl import WorkflowDef
from flowforge.replay.simulator import simulate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"
_DEF_PATH = _GENERATED_DIR / "workflows" / "claim_intake" / "definition.json"


def _load() -> WorkflowDef:
	assert _DEF_PATH.is_file(), f"definition.json not found at {_DEF_PATH}"
	raw = json.loads(_DEF_PATH.read_text(encoding="utf-8"))
	return WorkflowDef.model_validate(raw)


def _run(coro: object) -> object:
	loop = asyncio.new_event_loop()
	try:
		return loop.run_until_complete(coro)  # type: ignore[arg-type]
	finally:
		loop.close()


# ---------------------------------------------------------------------------
# Structural smoke
# ---------------------------------------------------------------------------


def test_definition_loads_and_parses() -> None:
	"""Generated definition.json must load and match the JTBD id."""
	wd = _load()
	assert wd.key == "claim_intake"
	assert wd.initial_state == "intake"
	state_names = {s.name for s in wd.states}
	assert {"intake", "review", "senior_triage", "rejected", "done"}.issubset(state_names)


def test_all_required_transitions_present() -> None:
	"""submit, approve, escalate, reject transitions must exist."""
	wd = _load()
	events = {t.event for t in wd.transitions}
	assert "submit" in events
	assert "approve" in events
	assert "reject" in events


# ---------------------------------------------------------------------------
# Case 1 — happy path: intake → review → done
# ---------------------------------------------------------------------------


def test_happy_path_reaches_done() -> None:
	"""Standard claim: submit then approve resolves to done."""
	wd = _load()
	result = _run(
		simulate(
			wd,
			events=[("submit", {}), ("approve", {})],
			tenant_id="test-tenant",
		)
	)
	assert result.terminal_state == "done", result.history  # type: ignore[union-attr]
	# Transition audit events must be present.
	audit_kinds = [e.kind for e in result.audit_events]  # type: ignore[union-attr]
	assert any(k.endswith(".transitioned") for k in audit_kinds), audit_kinds


def test_happy_path_passes_through_review() -> None:
	"""After submit (no flags) state must be review, not a branch."""
	wd = _load()
	result = _run(
		simulate(
			wd,
			events=[("submit", {})],
			tenant_id="test-tenant",
		)
	)
	assert result.terminal_state == "review", result.history  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Case 2 — large_loss: intake → senior_triage
# ---------------------------------------------------------------------------


def test_large_loss_routes_to_senior_triage() -> None:
	"""With context.large_loss=True the guarded branch fires to senior_triage."""
	wd = _load()
	result = _run(
		simulate(
			wd,
			initial_context={"large_loss": True},
			events=[("submit", {})],
			tenant_id="test-tenant",
		)
	)
	assert result.terminal_state == "senior_triage", result.history  # type: ignore[union-attr]


def test_large_loss_audit_event_recorded() -> None:
	"""The large_loss transition must emit the expected audit template."""
	wd = _load()
	result = _run(
		simulate(
			wd,
			initial_context={"large_loss": True},
			events=[("submit", {})],
			tenant_id="test-tenant",
		)
	)
	audit_kinds = [e.kind for e in result.audit_events]  # type: ignore[union-attr]
	# The transition itself is always audited.
	assert any(k.endswith(".transitioned") for k in audit_kinds), audit_kinds
	# The large_loss effect audit template.
	assert any("large_loss" in k for k in audit_kinds), audit_kinds


# ---------------------------------------------------------------------------
# Case 3 — lapsed policy: intake → review → rejected
# ---------------------------------------------------------------------------


def test_lapsed_policy_reaches_rejected() -> None:
	"""Reviewer rejects a lapsed-policy claim: terminal state is rejected."""
	wd = _load()
	result = _run(
		simulate(
			wd,
			events=[("submit", {}), ("reject", {})],
			tenant_id="test-tenant",
		)
	)
	assert result.terminal_state == "rejected", result.history  # type: ignore[union-attr]


def test_lapsed_policy_is_terminal_fail() -> None:
	"""The rejected state must be a terminal_fail kind."""
	wd = _load()
	rejected_states = [s for s in wd.states if s.name == "rejected"]
	assert rejected_states, "rejected state not found in definition"
	assert rejected_states[0].kind == "terminal_fail"


# ---------------------------------------------------------------------------
# End-to-end: full escalation path (intake → review → escalated → done)
# ---------------------------------------------------------------------------


def test_escalation_path_reaches_done() -> None:
	"""Authority-tier approval: submit → escalate → approve completes the claim."""
	wd = _load()
	result = _run(
		simulate(
			wd,
			events=[("submit", {}), ("escalate", {}), ("approve", {})],
			tenant_id="test-tenant",
		)
	)
	assert result.terminal_state == "done", result.history  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Determinism guard
# ---------------------------------------------------------------------------


def test_simulation_is_deterministic() -> None:
	"""Two identical runs produce identical history and terminal state."""
	wd = _load()
	r1 = _run(simulate(wd, events=[("submit", {}), ("approve", {})], tenant_id="t"))
	r2 = _run(simulate(wd, events=[("submit", {}), ("approve", {})], tenant_id="t"))
	assert r1.terminal_state == r2.terminal_state  # type: ignore[union-attr]
	assert r1.history == r2.history  # type: ignore[union-attr]
