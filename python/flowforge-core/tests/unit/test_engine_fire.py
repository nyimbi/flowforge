"""Engine two-phase fire end-to-end."""

from __future__ import annotations

import asyncio

import pytest

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.dsl.workflow_def import Guard
from flowforge.engine import fire, new_instance
from flowforge.engine.fire import (
	ConcurrentFireRejected,
	GuardEvaluationError,
	InvalidTargetError,
	OutboxDispatchError,
	make_context,
)
from flowforge.ports.types import Principal


pytestmark = pytest.mark.asyncio


def _claim_intake_def() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "claim_intake",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "intake",
			"states": [
				{"name": "intake", "kind": "manual_review"},
				{"name": "triage", "kind": "manual_review"},
				{"name": "senior_triage", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
				{"name": "rejected", "kind": "terminal_fail"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "intake",
					"to_state": "triage",
					"priority": 0,
					"guards": [
						{
							"kind": "expr",
							"expr": {
								"and": [
									{"not_null": {"var": "context.intake.policy_id"}},
									{">": [{"var": "context.intake.loss_amount"}, 0]},
								]
							},
						}
					],
					"effects": [
						{
							"kind": "create_entity",
							"entity": "claim",
							"values": {
								"policy_id": {"var": "context.intake.policy_id"},
								"loss_amount": {"var": "context.intake.loss_amount"},
							},
						},
						{
							"kind": "set",
							"target": "context.triage.priority",
							"expr": {
								"if": [
									{">": [{"var": "context.intake.loss_amount"}, 100000]},
									"high",
									"normal",
								]
							},
						},
						{"kind": "notify", "template": "claim.submitted"},
					],
				},
				{
					"id": "branch_large_loss",
					"event": "submit",
					"from_state": "intake",
					"to_state": "senior_triage",
					"priority": 10,
					"guards": [
						{
							"kind": "expr",
							"expr": {">": [{"var": "context.intake.loss_amount"}, 100000]},
						}
					],
				},
				{
					"id": "reject_lapsed",
					"event": "policy_check",
					"from_state": "intake",
					"to_state": "rejected",
					"guards": [
						{
							"kind": "expr",
							"expr": {"==": [{"var": "context.policy.status"}, "lapsed"]},
						}
					],
					"effects": [
						{
							"kind": "set",
							"target": "context.rejection_reason",
							"expr": "policy_lapsed",
						}
					],
				},
			],
		}
	)


@pytest.fixture(autouse=True)
def reset_config():
	config.reset_to_fakes()
	yield


async def test_happy_path_lands_in_triage() -> None:
	wd = _claim_intake_def()
	inst = new_instance(
		wd,
		initial_context={"intake": {"policy_id": "p-1", "loss_amount": 5000}},
	)
	result = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert result.matched_transition_id == "submit"
	assert result.new_state == "triage"
	assert inst.context["triage"]["priority"] == "normal"
	assert any(e[0] == "claim" for e in inst.created_entities)


async def test_priority_branch_for_large_loss() -> None:
	wd = _claim_intake_def()
	inst = new_instance(
		wd,
		initial_context={"intake": {"policy_id": "p-1", "loss_amount": 250000}},
	)
	result = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert result.matched_transition_id == "branch_large_loss"
	assert result.new_state == "senior_triage"


async def test_reject_lapsed_policy_terminates() -> None:
	wd = _claim_intake_def()
	inst = new_instance(
		wd,
		initial_context={
			"policy": {"status": "lapsed"},
			"intake": {"policy_id": "p-1", "loss_amount": 100},
		},
	)
	result = await fire(wd, inst, "policy_check", principal=Principal(user_id="u", is_system=True))
	assert result.new_state == "rejected"
	assert result.terminal is True


async def test_no_match_keeps_state() -> None:
	wd = _claim_intake_def()
	inst = new_instance(wd, initial_context={"intake": {"policy_id": None, "loss_amount": 0}})
	result = await fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
	assert result.matched_transition_id is None
	assert result.new_state == "intake"


def _single_transition_def(effects: list[dict[str, object]] | None = None) -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "case_flow",
			"version": "1.0.0",
			"subject_kind": "case",
			"initial_state": "draft",
			"states": [
				{"name": "draft", "kind": "manual_review"},
				{"name": "done", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "complete",
					"event": "complete",
					"from_state": "draft",
					"to_state": "done",
					"effects": effects or [],
				}
			],
		}
	)


async def test_terminal_instance_returns_without_mutation_or_dispatch() -> None:
	wd = _single_transition_def([
		{"kind": "notify", "template": "case.done"},
	])
	inst = new_instance(wd, initial_context={"x": 1})
	inst.state = "done"

	result = await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert result.terminal is True
	assert result.matched_transition_id is None
	assert result.planned_effects == []
	assert result.audit_events == []
	assert result.outbox_envelopes == []
	assert config.audit.events == []
	assert config.outbox.dispatched == []


async def test_effect_planning_covers_audit_update_compensate_signal_and_jtbd_metadata() -> None:
	wd = _single_transition_def([
		{
			"kind": "set",
			"target": "context.review.status",
			"expr": "ready",
		},
		{
			"kind": "audit",
			"template": "case.custom_audit",
		},
		{
			"kind": "update_entity",
			"entity": "case",
			"target": "case-1",
			"values": {"status": "ready"},
		},
		{
			"kind": "compensate",
			"compensation_kind": "undo_case_update",
			"values": {"case_id": "case-1"},
		},
		{
			"kind": "emit_signal",
			"signal": "case.completed",
		},
		{
			"kind": "notify",
			"template": "case.done",
		},
	])
	inst = new_instance(wd, initial_context={"review": "not-a-dict"})

	result = await fire(
		wd,
		inst,
		"complete",
		principal=Principal(user_id="reviewer"),
		tenant_id="tenant-a",
		jtbd_id="case_completion",
		jtbd_version="1.2.3",
		dispatch_ports=False,
	)

	assert result.terminal is True
	assert inst.context["review"]["status"] == "ready"
	assert inst.saga == [{"kind": "undo_case_update", "args": {"case_id": "case-1"}}]
	assert [event.kind for event in result.audit_events] == [
		"wf.case_flow.transitioned",
		"case.custom_audit",
		"wf.case_flow.entity_update_requested",
	]
	assert result.audit_events[0].payload["jtbd_id"] == "case_completion"
	assert result.audit_events[0].payload["jtbd_version"] == "1.2.3"
	assert result.audit_events[1].payload["context_snapshot"]["review"]["status"] == "ready"
	assert [env.kind for env in result.outbox_envelopes] == ["wf.signal", "wf.notify"]
	assert result.outbox_envelopes[0].body == {
		"signal": "case.completed",
		"instance_id": inst.id,
	}
	assert result.outbox_envelopes[1].body["jtbd_id"] == "case_completion"
	assert result.outbox_envelopes[1].body["jtbd_version"] == "1.2.3"
	assert config.audit.events == []
	assert config.outbox.dispatched == []


async def test_audit_effect_marks_non_json_context_values() -> None:
	wd = _single_transition_def([
		{
			"kind": "audit",
			"template": "case.snapshot",
		},
	])
	inst = new_instance(
		wd,
		initial_context={
			"plain": "ok",
			"unsafe": {1},
			"nested": [{"value": {2}}],
			"tupled": ({3},),
		},
	)

	result = await fire(
		wd,
		inst,
		"complete",
		principal=Principal(user_id="reviewer"),
		dispatch_ports=False,
	)

	snapshot = result.audit_events[1].payload["context_snapshot"]
	assert snapshot == {
		"plain": "ok",
		"unsafe": {"__non_json__": "{1}"},
		"nested": [{"value": {"__non_json__": "{2}"}}],
		"tupled": [{"__non_json__": "{3}"}],
	}


async def test_invalid_set_target_surfaces_authoring_error() -> None:
	wd = _single_transition_def([
		{
			"kind": "set",
			"target": "context",
			"expr": "bad",
		},
	])
	inst = new_instance(wd)

	with pytest.raises(InvalidTargetError, match="context"):
		await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert inst.state == "draft"
	assert inst.context == {}


async def test_guard_evaluation_error_surfaces_bad_guard_expression() -> None:
	wd = _single_transition_def()
	wd.transitions[0].guards = [Guard(expr={"var": 123})]
	inst = new_instance(wd)

	with pytest.raises(GuardEvaluationError) as exc_info:
		await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert exc_info.value.transition_id == "complete"
	assert exc_info.value.expr == {"var": 123}
	assert inst.state == "draft"
	assert inst.history == []


async def test_engine_exception_constructors_preserve_context() -> None:
	concurrent = ConcurrentFireRejected("inst-1")
	assert concurrent.instance_id == "inst-1"
	assert "inst-1" in str(concurrent)

	outbox = OutboxDispatchError("inst-2")
	assert outbox.instance_id == "inst-2"
	assert outbox.envelope_kind is None
	assert "envelope.kind" not in str(outbox)


async def test_concurrent_fire_rejects_second_fire_for_same_instance() -> None:
	class BlockingAudit:
		def __init__(self) -> None:
			self.entered = asyncio.Event()
			self.release = asyncio.Event()

		async def record(self, event):
			self.entered.set()
			await self.release.wait()

	audit = BlockingAudit()
	config.audit = audit
	wd = _single_transition_def()
	inst = new_instance(wd)

	first_fire = asyncio.create_task(
		fire(wd, inst, "complete", principal=Principal(user_id="u"))
	)
	await audit.entered.wait()

	with pytest.raises(ConcurrentFireRejected) as exc_info:
		await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert exc_info.value.instance_id == inst.id
	audit.release.set()
	result = await first_fire
	assert result.new_state == "done"


async def test_outbox_dispatch_failure_restores_all_mutated_instance_fields() -> None:
	class FailingOutbox:
		async def dispatch(self, envelope):
			raise RuntimeError("transport down")

	config.outbox = FailingOutbox()
	wd = _single_transition_def([
		{
			"kind": "set",
			"target": "context.review.status",
			"expr": "ready",
		},
		{
			"kind": "compensate",
			"compensation_kind": "undo_case_update",
			"values": {"case_id": "case-1"},
		},
		{"kind": "notify", "template": "case.done"},
	])
	inst = new_instance(wd, initial_context={"review": {"status": "draft"}})

	with pytest.raises(OutboxDispatchError) as exc_info:
		await fire(
			wd,
			inst,
			"complete",
			principal=Principal(user_id="u"),
			jtbd_id="case_completion",
			jtbd_version="1.2.3",
		)

	assert exc_info.value.instance_id == inst.id
	assert exc_info.value.envelope_kind == "wf.notify"
	assert isinstance(exc_info.value.__cause__, RuntimeError)
	assert inst.state == "draft"
	assert inst.context == {"review": {"status": "draft"}}
	assert inst.saga == []
	assert inst.history == []
	assert [event.kind for event in config.audit.events] == [
		"wf.case_flow.transitioned",
		"wf.case_flow.transition_rolled_back",
	]
	assert config.audit.events[1].payload == {
		"transition_id": "complete",
		"from_state": "draft",
		"to_state": "done",
		"restored_state": "draft",
		"event": "complete",
		"failed_envelope_kind": "wf.notify",
		"jtbd_id": "case_completion",
		"jtbd_version": "1.2.3",
	}


async def test_outbox_failure_preserves_original_error_when_rollback_audit_fails() -> None:
	class FailingOutbox:
		async def dispatch(self, envelope):
			raise RuntimeError("transport down")

	class RollbackAuditFails:
		def __init__(self) -> None:
			self.events = []

		async def record(self, event):
			self.events.append(event)
			if len(self.events) > 1:
				raise RuntimeError("audit rollback down")

	audit = RollbackAuditFails()
	config.audit = audit
	config.outbox = FailingOutbox()
	wd = _single_transition_def([
		{"kind": "set", "target": "context.review.status", "expr": "ready"},
		{"kind": "notify", "template": "case.done"},
	])
	inst = new_instance(wd, initial_context={"review": {"status": "draft"}})

	with pytest.raises(OutboxDispatchError) as exc_info:
		await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert isinstance(exc_info.value.__cause__, RuntimeError)
	assert inst.state == "draft"
	assert inst.context == {"review": {"status": "draft"}}
	assert [event.kind for event in audit.events] == [
		"wf.case_flow.transitioned",
		"wf.case_flow.transition_rolled_back",
	]


async def test_outbox_dispatch_still_runs_when_audit_port_is_unconfigured() -> None:
	wd = _single_transition_def([
		{"kind": "notify", "template": "case.done"},
	])
	inst = new_instance(wd)
	config.audit = None

	result = await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert result.new_state == "done"
	assert [env.kind for env in config.outbox.dispatched] == ["wf.notify"]


async def test_audit_dispatch_failure_restores_state_and_skips_outbox() -> None:
	class FailingAudit:
		async def record(self, event):
			raise RuntimeError("audit down")

	config.audit = FailingAudit()
	wd = _single_transition_def([
		{"kind": "notify", "template": "case.done"},
	])
	inst = new_instance(wd)

	with pytest.raises(RuntimeError, match="audit down"):
		await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert inst.state == "draft"
	assert inst.history == []
	assert config.outbox.dispatched == []


async def test_make_context_carries_tenant_principal_and_elevation() -> None:
	principal = Principal(user_id="system", is_system=True)

	ctx = make_context("tenant-a", principal, elevated=True)

	assert ctx.tenant_id == "tenant-a"
	assert ctx.principal is principal
	assert ctx.elevated is True


async def test_unknown_state_is_not_terminal() -> None:
	wd = _single_transition_def()
	inst = new_instance(wd)
	inst.state = "detached"

	result = await fire(wd, inst, "complete", principal=Principal(user_id="u"))

	assert result.terminal is False
	assert result.new_state == "detached"
