"""E-70 — production config validation and scoped runtime wiring.

Audit finding MEDIUM-05: module-global test fakes and noop RLS must not
silently reach production, and multi-app hosts need a scoped wiring hook
so one app's audit/outbox ports do not bleed into another.
"""

from __future__ import annotations

import pytest

from flowforge import config
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.ports.types import Principal
from flowforge.testing.port_fakes import InMemoryAuditSink, InMemoryOutbox


class _RealPort:
	pass


def _one_step_workflow() -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "config_scope",
			"version": "1.0.0",
			"subject_kind": "claim",
			"initial_state": "draft",
			"states": [
				{"name": "draft", "kind": "manual_review"},
				{"name": "done", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "submit",
					"event": "submit",
					"from_state": "draft",
					"to_state": "done",
					"effects": [{"kind": "notify", "template": "config.scope"}],
				}
			],
		}
	)


def test_M_05_production_validation_rejects_default_fakes() -> None:
	config.reset_to_fakes()

	with pytest.raises(config.ProductionConfigError) as exc_info:
		config.validate_production_config()

	errors = exc_info.value.errors
	assert any("tenancy uses testing fake InMemoryTenancy" in e for e in errors)
	assert any("rbac uses testing fake InMemoryRbac" in e for e in errors)
	assert any("audit uses testing fake InMemoryAuditSink" in e for e in errors)
	assert any("outbox uses testing fake InMemoryOutbox" in e for e in errors)
	assert any("rls uses testing fake NoopRls" in e for e in errors)


def test_M_05_production_validation_accepts_non_fake_required_ports() -> None:
	cfg = config.RuntimeConfig(
		tenancy=_RealPort(),
		rbac=_RealPort(),
		audit=_RealPort(),
		outbox=_RealPort(),
		rls=_RealPort(),
	)

	config.validate_production_config(cfg)


def test_M_05_production_validation_reports_unknown_required_port() -> None:
	cfg = config.RuntimeConfig()

	errors = config.production_config_errors(cfg, required_ports=("not_a_port",))

	assert errors == ["unknown required port 'not_a_port'"]


@pytest.mark.asyncio
async def test_M_05_scoped_runtime_config_isolates_fire_ports() -> None:
	config.reset_to_fakes()
	global_audit = config.audit
	global_outbox = config.outbox
	cfg_a = config.snapshot_runtime_config()
	cfg_b = config.snapshot_runtime_config()
	cfg_a.audit = InMemoryAuditSink()
	cfg_a.outbox = InMemoryOutbox()
	cfg_b.audit = InMemoryAuditSink()
	cfg_b.outbox = InMemoryOutbox()

	wd = _one_step_workflow()

	with config.use_runtime_config(cfg_a):
		inst_a = new_instance(wd, initial_context={})
		await fire(wd, inst_a, "submit", principal=Principal(user_id="u", is_system=True))

	with config.use_runtime_config(cfg_b):
		inst_b = new_instance(wd, initial_context={})
		await fire(wd, inst_b, "submit", principal=Principal(user_id="u", is_system=True))

	assert len(cfg_a.audit.events) == 1
	assert len(cfg_a.outbox.dispatched) == 1
	assert len(cfg_b.audit.events) == 1
	assert len(cfg_b.outbox.dispatched) == 1
	assert cfg_a.audit.events[0].subject_id != cfg_b.audit.events[0].subject_id
	assert len(global_audit.events) == 0
	assert len(global_outbox.dispatched) == 0
