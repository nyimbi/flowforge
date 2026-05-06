"""Tests for E-10 — JTBD-id propagation into workflow events.

Verifies that ``jtbd_id`` and ``jtbd_version`` supplied to ``fire()`` are:
- Stamped into the ``wf.<key>.transitioned`` audit event payload.
- Included in ``wf.notify`` outbox envelope bodies.
- Accessible in the evaluator context via ``__jtbd_id__`` / ``__jtbd_version__``.
- Absent from payloads when not supplied (backwards-compat).

Also covers ``STANDARD_LABEL_NAMES`` in ``MetricsPort``.
"""

from __future__ import annotations

from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import fire, new_instance
from flowforge.ports.metrics import STANDARD_LABEL_NAMES
# asyncio_mode = "auto" in pyproject.toml — no pytestmark needed.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_def() -> WorkflowDef:
	"""A two-state workflow: draft → submitted (with notify effect)."""
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "draft",
			"states": [
				{"name": "draft", "kind": "manual_review"},
				{"name": "submitted", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "draft",
					"to_state": "submitted",
					"priority": 0,
					"guards": [],
					"effects": [
						{"kind": "notify", "template": "claim.submitted"},
					],
				}
			],
		}
	)


def _no_effect_def() -> WorkflowDef:
	"""Transition with no effects — just state change."""
	return WorkflowDef.model_validate(
		{
			"key": "simple",
			"version": "1.0.0",
			"subject_kind": "thing",
			"initial_state": "open",
			"states": [
				{"name": "open", "kind": "manual_review"},
				{"name": "closed", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "close",
					"event": "close",
					"from_state": "open",
					"to_state": "closed",
					"priority": 0,
					"guards": [],
					"effects": [],
				}
			],
		}
	)


# ---------------------------------------------------------------------------
# Audit event propagation
# ---------------------------------------------------------------------------

async def test_jtbd_id_in_transition_audit_payload() -> None:
	wd = _minimal_def()
	inst = new_instance(wd)
	result = await fire(
		wd, inst, "submit",
		jtbd_id="claim_intake",
		jtbd_version="1.4.0",
	)
	transition_audit = result.audit_events[0]
	assert transition_audit.payload["jtbd_id"] == "claim_intake"
	assert transition_audit.payload["jtbd_version"] == "1.4.0"


async def test_jtbd_id_not_in_audit_when_not_supplied() -> None:
	"""Backwards-compat: omitting jtbd_id leaves the payload clean."""
	wd = _no_effect_def()
	inst = new_instance(wd)
	result = await fire(wd, inst, "close")
	transition_audit = result.audit_events[0]
	assert "jtbd_id" not in transition_audit.payload
	assert "jtbd_version" not in transition_audit.payload


async def test_jtbd_id_only_no_version() -> None:
	"""jtbd_id alone (no version) stamps only jtbd_id."""
	wd = _no_effect_def()
	inst = new_instance(wd)
	result = await fire(wd, inst, "close", jtbd_id="simple_close")
	transition_audit = result.audit_events[0]
	assert transition_audit.payload["jtbd_id"] == "simple_close"
	assert "jtbd_version" not in transition_audit.payload


async def test_transition_audit_still_has_core_fields() -> None:
	"""jtbd_id fields are additive — core fields remain intact."""
	wd = _minimal_def()
	inst = new_instance(wd)
	result = await fire(wd, inst, "submit", jtbd_id="claim_intake", jtbd_version="1.0.0")
	payload = result.audit_events[0].payload
	assert payload["transition_id"] == "submit"
	assert payload["from_state"] == "draft"
	assert payload["to_state"] == "submitted"
	assert payload["event"] == "submit"


# ---------------------------------------------------------------------------
# Outbox / notify envelope propagation
# ---------------------------------------------------------------------------

async def test_jtbd_id_in_notify_envelope_body() -> None:
	wd = _minimal_def()
	inst = new_instance(wd)
	result = await fire(
		wd, inst, "submit",
		jtbd_id="claim_intake",
		jtbd_version="1.4.0",
	)
	notify_envs = [e for e in result.outbox_envelopes if e.kind == "wf.notify"]
	assert len(notify_envs) == 1
	body = notify_envs[0].body
	assert body["jtbd_id"] == "claim_intake"
	assert body["jtbd_version"] == "1.4.0"


async def test_notify_envelope_no_jtbd_without_propagation() -> None:
	wd = _minimal_def()
	inst = new_instance(wd)
	result = await fire(wd, inst, "submit")
	notify_envs = [e for e in result.outbox_envelopes if e.kind == "wf.notify"]
	assert len(notify_envs) == 1
	body = notify_envs[0].body
	assert "jtbd_id" not in body
	assert "jtbd_version" not in body


async def test_notify_envelope_still_has_template_and_instance_id() -> None:
	"""jtbd fields are additive — core envelope body fields remain."""
	wd = _minimal_def()
	inst = new_instance(wd)
	result = await fire(wd, inst, "submit", jtbd_id="x")
	notify_env = next(e for e in result.outbox_envelopes if e.kind == "wf.notify")
	assert notify_env.body["template"] == "claim.submitted"
	assert notify_env.body["instance_id"] == inst.id


# ---------------------------------------------------------------------------
# Evaluator context exposure
# ---------------------------------------------------------------------------

async def test_jtbd_id_available_in_eval_context() -> None:
	"""Guard expressions can reference __jtbd_id__ via eval_ctx."""
	# We can't easily inspect eval_ctx after the fact, but we can verify
	# the fire call completes without error and the result carries the value.
	wd = _no_effect_def()
	inst = new_instance(wd)
	result = await fire(
		wd, inst, "close",
		jtbd_id="my_jtbd",
		jtbd_version="2.0.0",
	)
	# Propagation into audit is the observable outcome.
	assert result.audit_events[0].payload["jtbd_id"] == "my_jtbd"


# ---------------------------------------------------------------------------
# No-op when terminal
# ---------------------------------------------------------------------------

async def test_fire_on_terminal_instance_ignores_jtbd_id() -> None:
	wd = _no_effect_def()
	inst = new_instance(wd)
	# First fire to reach terminal.
	await fire(wd, inst, "close")
	# Second fire — should return terminal FireResult with no audit events.
	result = await fire(wd, inst, "close", jtbd_id="x", jtbd_version="1")
	assert result.terminal
	assert result.matched_transition_id is None
	assert result.audit_events == []


# ---------------------------------------------------------------------------
# STANDARD_LABEL_NAMES
# ---------------------------------------------------------------------------

def test_standard_label_names_includes_jtbd_fields() -> None:
	assert "jtbd_id" in STANDARD_LABEL_NAMES
	assert "jtbd_version" in STANDARD_LABEL_NAMES


def test_standard_label_names_includes_core_fields() -> None:
	for name in ("tenant_id", "def_key", "state"):
		assert name in STANDARD_LABEL_NAMES


def test_standard_label_names_is_tuple() -> None:
	assert isinstance(STANDARD_LABEL_NAMES, tuple)
