"""Unit tests for the W0 / item 2 compensation synthesis.

Covers:

* ``derive_states`` adds a per-edge ``manual_review`` compensation point
  state plus a ``compensated`` terminal_fail when at least one edge_case
  declares ``handle: "compensate"``.
* ``derive_transitions`` emits one ``compensate`` transition per
  compensate edge_case with the deterministic id
  ``<jtbd>_<edge_id>_compensate`` and effects in **LIFO** order:

    - every forward ``create_entity`` → paired ``compensate_delete``
    - every forward ``notify``        → paired ``notify_cancellation``
      with template ``<jtbd>.<event>.cancelled``

* The new per-JTBD ``compensation_handlers`` generator is silent when
  the JTBD declares no compensate handle (preserving byte-identical
  regen for existing examples) and emits a stub registering the synthesised
  compensation kinds when at least one edge_case declares compensate.
* Byte-deterministic regen across two pipeline runs even when
  compensation transitions are present.
* The fixture-coverage registry agrees with the generator's
  ``CONSUMES`` declaration.
"""

from __future__ import annotations

import compileall
from pathlib import Path
from typing import Any

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import compensation_handlers as comp_gen
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.normalize import normalize
from flowforge_cli.jtbd.transforms import derive_states, derive_transitions


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _bundle_with_compensate() -> dict[str, Any]:
	"""Two JTBDs: one with compensate edge_case, one without (boundary check)."""

	return {
		"project": {
			"name": "saga-demo",
			"package": "saga_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {"roles": ["adjuster"], "permissions": []},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["claim is queued within 24h"],
				"data_capture": [
					{"id": "claimant_name", "kind": "text", "label": "Claimant", "required": True, "pii": True},
					{"id": "loss_amount", "kind": "money", "label": "Loss", "required": True, "pii": False},
				],
				"edge_cases": [
					{
						"id": "payment_failed",
						"condition": "external payment processor returned non-2xx",
						"handle": "compensate",
					}
				],
				"approvals": [],
				"notifications": [
					{"trigger": "state_enter", "channel": "email", "audience": "claimant"}
				],
			},
			{
				# Boundary check: a sibling JTBD without compensate emits no
				# compensation_handlers.py — guards against accidental cross-JTBD coupling.
				"id": "claim_payout",
				"title": "Pay an approved claim",
				"actor": {"role": "adjuster"},
				"situation": "approved claim ready for disbursement",
				"motivation": "release funds to claimant",
				"outcome": "claimant paid",
				"success_criteria": ["disbursement booked within 48h"],
				"data_capture": [
					{"id": "amount", "kind": "money", "label": "Amount", "required": True, "pii": False}
				],
			},
		],
	}


def _claim_jtbd(bundle: dict[str, Any]) -> dict[str, Any]:
	return next(j for j in bundle["jtbds"] if j["id"] == "claim_intake")


# ---------------------------------------------------------------------------
# transforms.derive_states
# ---------------------------------------------------------------------------


def test_derive_states_adds_compensated_terminal() -> None:
	jt = _claim_jtbd(_bundle_with_compensate())
	states = derive_states(jt)
	names = [s["name"] for s in states]
	# Singleton ``compensated`` terminal_fail. The compensation point is the
	# existing ``review`` state (already a manual_review state), so no new
	# per-edge state is needed and the reachability validator stays green.
	assert "compensated" in names
	comp = next(s for s in states if s["name"] == "compensated")
	assert comp["kind"] == "terminal_fail"
	# done remains the final state.
	assert names[-1] == "done"


def test_derive_states_no_compensate_handle_unchanged() -> None:
	"""A JTBD with no compensate edge_case must not gain compensation states."""

	jt = {
		"id": "x",
		"title": "X",
		"actor": {"role": "a"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["x"],
		"edge_cases": [],
	}
	names = [s["name"] for s in derive_states(jt)]
	assert "compensated" not in names
	# Base flow unchanged.
	assert names == ["intake", "review", "done"]


# ---------------------------------------------------------------------------
# transforms.derive_transitions
# ---------------------------------------------------------------------------


def test_derive_transitions_emits_compensate_transition() -> None:
	jt = _claim_jtbd(_bundle_with_compensate())
	states = derive_states(jt)
	tr = derive_transitions(jt, states)

	compensate = [t for t in tr if t["event"] == "compensate"]
	assert len(compensate) == 1, [t["id"] for t in tr]

	t = compensate[0]
	# Deterministic id pattern: <jtbd>_<edge_id>_compensate.
	assert t["id"] == "claim_intake_payment_failed_compensate"
	# Compensation point is the existing ``review`` state; transition routes
	# to the singleton ``compensated`` terminal_fail. Guarded by
	# ``context.<edge_id>`` (same expr shape ``branch`` already uses, so no
	# new operator enters the cross-runtime parity fixture).
	assert t["from_state"] == "review"
	assert t["to_state"] == "compensated"
	assert t["guards"] == [{"kind": "expr", "expr": {"var": "context.payment_failed"}}]


def test_compensation_effects_are_lifo_paired() -> None:
	"""Forward order: submit (create_entity, audit), approve (notify).
	Compensation order (LIFO): notify_cancellation(approve), compensate_delete(claim_intake).

	Effects use the canonical workflow_def schema: ``kind = "compensate"``
	with ``compensation_kind`` naming the saga-step kind the host registers
	a handler for (matches engine fire.py:243).
	"""

	jt = _claim_jtbd(_bundle_with_compensate())
	states = derive_states(jt)
	tr = derive_transitions(jt, states)
	compensate = next(t for t in tr if t["event"] == "compensate")

	effects = compensate["effects"]
	# Every paired effect is a ``compensate`` effect — the engine appends
	# them to ``instance.saga`` so :class:`CompensationWorker.replay_pending`
	# can dispatch by ``compensation_kind`` later.
	assert all(e["kind"] == "compensate" for e in effects), effects
	# Two paired effects: one for the create_entity (submit), one for the
	# notify (approve). The audit effect on submit does not pair.
	comp_kinds = [e["compensation_kind"] for e in effects]
	assert comp_kinds == ["notify_cancellation", "compensate_delete"], comp_kinds

	# notify_cancellation template is <jtbd>.<event>.cancelled (event = approve).
	notify_eff = effects[0]
	assert notify_eff["values"]["template"] == "claim_intake.approve.cancelled"

	# compensate_delete carries the entity name from the forward effect.
	delete_eff = effects[1]
	assert delete_eff["values"]["entity"] == "claim_intake"


def test_no_compensate_no_compensation_transitions() -> None:
	"""Boundary: a JTBD without compensate edge_case must not gain a
	compensate transition (preserves byte-identical regen for examples)."""

	jt = {
		"id": "claim_payout",
		"title": "Pay",
		"actor": {"role": "adjuster"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["x"],
		"edge_cases": [],
	}
	states = derive_states(jt)
	tr = derive_transitions(jt, states)
	assert all(t["event"] != "compensate" for t in tr)


def test_multiple_compensate_edges_emit_distinct_transitions() -> None:
	"""Each compensate edge_case produces its own deterministic transition id
	with a ``context.<edge_id>``-shaped guard so the engine can pick the
	matching transition by priority."""

	jt = {
		"id": "shipping",
		"title": "Ship",
		"actor": {"role": "warehouse"},
		"situation": "s",
		"motivation": "m",
		"outcome": "o",
		"success_criteria": ["x"],
		"edge_cases": [
			{"id": "carrier_outage", "condition": "carrier api down", "handle": "compensate"},
			{"id": "address_invalid", "condition": "address rejected", "handle": "compensate"},
		],
	}
	states = derive_states(jt)
	tr = derive_transitions(jt, states)
	ids = sorted(t["id"] for t in tr if t["event"] == "compensate")
	assert ids == [
		"shipping_address_invalid_compensate",
		"shipping_carrier_outage_compensate",
	]
	# Singleton compensated terminal — not duplicated even with two compensate edges.
	assert sum(1 for s in states if s["name"] == "compensated") == 1
	# Each compensate transition carries its own ``context.<edge_id>`` guard.
	guards = sorted(
		t["guards"][0]["expr"]["var"] for t in tr if t["event"] == "compensate"
	)
	assert guards == ["context.address_invalid", "context.carrier_outage"]


# ---------------------------------------------------------------------------
# compensation_handlers generator
# ---------------------------------------------------------------------------


def test_compensation_handlers_emitted_only_when_jtbd_has_compensate() -> None:
	bundle = _bundle_with_compensate()
	files = generate(bundle)
	paths = [f.path for f in files]

	# Emitted for the JTBD that declares compensate.
	expected = "backend/src/saga_demo/claim_intake/compensation_handlers.py"
	assert expected in paths, paths

	# Not emitted for the sibling JTBD with no compensate edge.
	assert "backend/src/saga_demo/claim_payout/compensation_handlers.py" not in paths


def test_compensation_handlers_stub_registers_known_kinds() -> None:
	bundle = _bundle_with_compensate()
	files = generate(bundle)
	(stub,) = [f for f in files if f.path.endswith("/claim_intake/compensation_handlers.py")]
	# Mentions every kind the synthesiser emits.
	assert "compensate_delete" in stub.content
	assert "notify_cancellation" in stub.content
	# Exposes the documented entry point.
	assert "def register_compensations(worker: CompensationWorker)" in stub.content


def test_compensation_handlers_module_compiles(tmp_path: Path) -> None:
	bundle = _bundle_with_compensate()
	files = generate(bundle)
	(stub,) = [f for f in files if f.path.endswith("/claim_intake/compensation_handlers.py")]
	dst = tmp_path / "compensation_handlers.py"
	dst.write_text(stub.content, encoding="utf-8")
	assert compileall.compile_file(str(dst), quiet=1)


def test_workflow_adapter_imports_compensation_handlers_when_present() -> None:
	bundle = _bundle_with_compensate()
	files = generate(bundle)
	(adapter,) = [
		f for f in files if f.path.endswith("/adapters/claim_intake_adapter.py")
	]
	# Conditional import + register entrypoint live in the adapter so the
	# host wires saga compensations through the same surface as ``fire_event``.
	assert "from flowforge.engine.saga import CompensationWorker" in adapter.content
	assert "from ..claim_intake.compensation_handlers import" in adapter.content
	assert "def register_compensations(worker: CompensationWorker)" in adapter.content


def test_workflow_adapter_unchanged_when_no_compensate() -> None:
	"""Adapter for a JTBD without compensate edges must not leak saga imports."""

	bundle = _bundle_with_compensate()
	files = generate(bundle)
	(adapter,) = [
		f for f in files if f.path.endswith("/adapters/claim_payout_adapter.py")
	]
	assert "CompensationWorker" not in adapter.content
	assert "compensation_handlers" not in adapter.content


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_compensate_pipeline_is_byte_deterministic() -> None:
	a = generate(_bundle_with_compensate())
	b = generate(_bundle_with_compensate())
	assert [f.path for f in a] == [f.path for f in b]
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic: {fa.path}"


# ---------------------------------------------------------------------------
# fixture-registry coverage
# ---------------------------------------------------------------------------


def test_compensation_handlers_consumes_matches_registry() -> None:
	"""Generator's CONSUMES tuple agrees with the central registry."""

	declared = comp_gen.CONSUMES
	registered = _fixture_registry.get("compensation_handlers")
	assert tuple(sorted(declared)) == tuple(sorted(registered)), (declared, registered)


def test_example_bundle_exercises_compensation_consumes() -> None:
	"""At least one example bundle in this test populates each declared field."""

	bundle = _bundle_with_compensate()
	# jtbds[].edge_cases — claim_intake declares one
	assert any(j.get("edge_cases") for j in bundle["jtbds"])
	# jtbds[].id — every JTBD has one
	assert all(j.get("id") for j in bundle["jtbds"])


# ---------------------------------------------------------------------------
# normalize wires through
# ---------------------------------------------------------------------------


def test_normalize_carries_compensate_transitions_through_view_model() -> None:
	bundle = _bundle_with_compensate()
	norm = normalize(bundle)
	(claim,) = [j for j in norm.jtbds if j.id == "claim_intake"]
	compensate = [t for t in claim.transitions if t["event"] == "compensate"]
	assert len(compensate) == 1
	# Singleton ``compensated`` terminal_fail surfaces in the view-model.
	assert any(s["name"] == "compensated" for s in claim.states)
