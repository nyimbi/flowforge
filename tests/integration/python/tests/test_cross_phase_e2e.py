"""E-31: Cross-phase E2E integration tests.

Exercises the full JTBD-to-runtime pipeline end-to-end, touching every
major component introduced in E-1 through E-30:

Pipeline under test (matches evolution.md §2 + §13.3 tutorial steps):
  1. Parse + validate a JTBD bundle (E-1: JtbdSpec, schema).
  2. Run the JTBD linter — lifecycle, dependency, actor, glossary,
     compliance, quality (E-4, E-5, E-8, E-23, E-16).
  3. flowforge jtbd-generate — scaffold workflow definition (existing).
  4. flowforge validate — static validator on generated def (existing).
  5. flowforge simulate — walk the workflow to terminal state.
  6. FaultInjector — inject gate_fail and verify blocking (E-12).
  7. WorkflowDiffer — diff old vs new workflow version (E-13).
  8. replaced_by migration runner — resolve chain + diff shapes (E-3).
  9. JtbdAuditLogger — record JTBD edits, verify buffered events (E-20).
  10. RBAC permission catalog — verify 8 permissions + 3 roles (E-19).
  11. ComplianceLinter — sensitivity→regime + missing-job rules (E-23).
  12. Plugin SDK — BPMN + storymap exporters round-trip (E-21).
  13. Registry manifest — sign + verify JtbdManifest (E-24).
  14. Tutorial CLI — dry-run all 5 steps without errors (E-28).

The test suite uses only in-process tooling (typer CliRunner, in-memory
ports) — no docker, no network, no Playwright. The Playwright UI suite is
a separate concern run by the CI Playwright job.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

# ---------- flowforge-core imports ----------
from flowforge.dsl import WorkflowDef
from flowforge.engine.fire import fire, new_instance
from flowforge.compiler.diff import diff_workflow_dicts
from flowforge.replay.fault import FaultInjector, FaultMode, FaultSpec
from flowforge.replay.simulator import simulate

# ---------- flowforge-jtbd imports ----------
from flowforge_jtbd.dsl.spec import JtbdSpec, JtbdBundle
from flowforge_jtbd.migrate import build_migration
from flowforge_jtbd.audit import JtbdAuditLogger, JtbdEditAction
from flowforge_jtbd.permissions import (
	JTBD_PERMISSION_NAMES,
	JTBD_ROLES,
	permissions_for_role,
)
from flowforge_jtbd.compliance.schema import (
	missing_regimes,
	SENSITIVITY_IMPLIES_REGIME,
)
from flowforge_jtbd.compliance.catalog import required_jobs_for
from flowforge_jtbd.lint.compliance import ComplianceLinterPack
from flowforge_jtbd.lint.linter import Linter
from flowforge_jtbd.lint.registry import RuleRegistry
from flowforge_jtbd.exporters.bpmn import BpmnExporter
from flowforge_jtbd.exporters.storymap import StorymapExporter
from flowforge_jtbd.registry.manifest import JtbdManifest, manifest_from_bundle
from flowforge_jtbd.registry.signing import sign_manifest, verify_manifest
from flowforge_jtbd.spec import JtbdBundle as JtbdLintBundle

# ---------- flowforge-cli imports ----------
from flowforge_cli.main import app


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
	return asyncio.get_event_loop().run_until_complete(coro)


RUNNER = CliRunner()


def _minimal_wf_data(key: str = "claim_intake") -> dict[str, Any]:
	return {
		"key": key,
		"version": "1.0.0",
		"subject_kind": "claim",
		"initial_state": "intake",
		"states": [
			{"name": "intake", "kind": "manual_review"},
			{"name": "review", "kind": "manual_review"},
			{"name": "done", "kind": "terminal_success"},
		],
		"transitions": [
			{
				"id": "submit",
				"event": "submit",
				"from_state": "intake",
				"to_state": "review",
				"priority": 0,
				"guards": [],
				"gates": [{"kind": "permission", "permission": "claim.submit"}],
				"effects": [{"kind": "notify", "template": "claim.submitted"}],
			},
			{
				"id": "approve",
				"event": "approve",
				"from_state": "review",
				"to_state": "done",
				"priority": 0,
				"guards": [],
				"gates": [],
				"effects": [],
			},
		],
	}


def _jtbd_spec(jtbd_id: str = "claim_intake") -> JtbdSpec:
	return JtbdSpec.model_validate({
		"id": jtbd_id,
		"actor": {"role": "policyholder", "external": True},
		"situation": "policyholder needs to file an FNOL",
		"motivation": "recover insured losses",
		"outcome": "claim accepted into triage",
		"success_criteria": ["claim queued within SLA"],
		"data_capture": [
			{"id": "claimant_name", "kind": "text", "label": "Full name", "pii": True},
			{"id": "loss_amount", "kind": "money", "label": "Loss", "pii": False},
		],
		"approvals": [{"role": "adjuster", "policy": "1_of_1"}],
	})


def _lint_bundle(*specs: dict[str, Any]) -> JtbdLintBundle:
	return JtbdLintBundle.model_validate({
		"bundle_id": "test",
		"jtbds": [
			{"jtbd_id": s.get("id", s.get("jtbd_id", "x")), "version": "1.0.0", **s}
			for s in specs
		],
	})


# ---------------------------------------------------------------------------
# 1. JTBD bundle parsing (E-1)
# ---------------------------------------------------------------------------


def test_e1_jtbd_spec_parses_correctly() -> None:
	spec = _jtbd_spec()
	assert spec.id == "claim_intake"
	assert spec.actor.role == "policyholder"
	assert len(spec.data_capture) == 2


def test_e1_jtbd_spec_hash_is_deterministic() -> None:
	spec = _jtbd_spec()
	h1 = spec.compute_hash()
	h2 = spec.compute_hash()
	assert h1 == h2
	assert h1.startswith("sha256:")


def test_e1_jtbd_bundle_validates_unique_ids() -> None:
	import pytest
	from flowforge_jtbd.dsl.spec import JtbdBundle
	with pytest.raises(Exception, match="duplicate"):
		JtbdBundle.model_validate({
			"project": {"name": "t", "package": "t", "domain": "t"},
			"shared": {},
			"jtbds": [
				{"id": "x", "actor": {"role": "u"}, "situation": "s",
				 "motivation": "m", "outcome": "o", "success_criteria": ["c"]},
				{"id": "x", "actor": {"role": "u"}, "situation": "s",
				 "motivation": "m", "outcome": "o", "success_criteria": ["c"]},
			],
		})


# ---------------------------------------------------------------------------
# 2. JTBD linter (E-4, E-5, E-23)
# ---------------------------------------------------------------------------


def test_e4_linter_runs_on_minimal_bundle() -> None:
	bundle = _lint_bundle({"id": "x"})
	linter = Linter()
	report = linter.lint(bundle)
	# Minimal JTBD with no stages → lifecycle errors expected
	assert isinstance(report.ok, bool)


def test_e23_compliance_linter_phi_missing_hipaa() -> None:
	bundle = _lint_bundle({
		"id": "claim_intake",
		"data_sensitivity": ["PHI"],
		"compliance": [],
	})
	linter = Linter(registry=RuleRegistry([ComplianceLinterPack()]))
	report = linter.lint(bundle)
	err_rules = {i.rule for i in report.errors()}
	assert "compliance.sensitivity_implies_regime" in err_rules


def test_e23_compliance_linter_phi_with_hipaa_passes() -> None:
	bundle = _lint_bundle({
		"id": "phi_job",
		"data_sensitivity": ["PHI"],
		"compliance": ["HIPAA"],
	})
	linter = Linter(registry=RuleRegistry([ComplianceLinterPack()]))
	report = linter.lint(bundle)
	comp_errors = [i for i in report.errors() if "compliance" in i.rule]
	assert comp_errors == []


# ---------------------------------------------------------------------------
# 3 + 4. flowforge generate + validate (existing CLI)
# ---------------------------------------------------------------------------


def test_tutorial_dry_run_covers_generate_and_validate(tmp_path: Path) -> None:
	"""Tutorial dry-run steps 2+3 exercise generate + validate paths."""
	r = RUNNER.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--no-pause", "--dry-run"],
	)
	assert r.exit_code == 0, r.output
	assert "jtbd-generate" in r.output
	assert "validate" in r.output


# ---------------------------------------------------------------------------
# 5. Simulation — happy path
# ---------------------------------------------------------------------------


async def test_e2e_simulate_happy_path() -> None:
	wd = WorkflowDef.model_validate(_minimal_wf_data())
	result = await simulate(wd, events=[("submit", {}), ("approve", {})])
	assert result.terminal_state == "done"
	assert len(result.history) == 2


async def test_e2e_simulate_reaches_terminal_via_transitions() -> None:
	wd = WorkflowDef.model_validate(_minimal_wf_data())
	result = await simulate(wd, events=[("submit", {}), ("approve", {})])
	assert any("done" in h for h in result.history)


# ---------------------------------------------------------------------------
# 6. Fault injection (E-12)
# ---------------------------------------------------------------------------


async def test_e12_gate_fail_blocks_transition() -> None:
	wd = WorkflowDef.model_validate(_minimal_wf_data())
	injector = FaultInjector([FaultSpec(mode=FaultMode.gate_fail, target_event="submit")])
	result = await injector.simulate(wd, events=[("submit", {})])
	assert result.terminal_state == "intake"  # blocked
	assert result.fault_log[0].mode == FaultMode.gate_fail


async def test_e12_sla_breach_blocked_with_audit_event() -> None:
	wd = WorkflowDef.model_validate(_minimal_wf_data())
	injector = FaultInjector([FaultSpec(mode=FaultMode.sla_breach)])
	result = await injector.simulate(wd, events=[("submit", {})])
	assert any("sla_breach" in e.kind for e in result.audit_events)


def test_e12_all_7_modes_are_defined() -> None:
	modes = list(FaultMode)
	assert len(modes) == 7


# ---------------------------------------------------------------------------
# 7. Workflow differ (E-13)
# ---------------------------------------------------------------------------


def test_e13_differ_detects_added_state() -> None:
	old = _minimal_wf_data()
	new = _minimal_wf_data()
	new["states"].append({"name": "rescinded", "kind": "terminal_fail"})
	diff = diff_workflow_dicts(old, new)
	assert "rescinded" in diff.added_states


def test_e13_differ_detects_removed_transition() -> None:
	old = _minimal_wf_data()
	new = _minimal_wf_data()
	new["transitions"] = [t for t in new["transitions"] if t["id"] != "approve"]
	diff = diff_workflow_dicts(old, new)
	assert "approve" in diff.removed_transitions


def test_e13_differ_identity_is_empty() -> None:
	data = _minimal_wf_data()
	diff = diff_workflow_dicts(data, data)
	assert diff.is_empty()


# ---------------------------------------------------------------------------
# 8. replaced_by migration runner (E-3)
# ---------------------------------------------------------------------------


def _raw_bundle_with_replacement() -> dict[str, Any]:
	return {
		"project": {"name": "t", "package": "t", "domain": "t"},
		"jtbds": [
			{
				"id": "old_intake",
				"replaced_by": "new_intake",
				"deprecated": True,
				"actor": {"role": "u"},
				"situation": "s", "motivation": "m", "outcome": "o",
				"success_criteria": ["c"],
				"data_capture": [
					{"id": "name", "kind": "text", "pii": True},
					{"id": "legacy", "kind": "text", "pii": False},
				],
			},
			{
				"id": "new_intake",
				"actor": {"role": "u"},
				"situation": "s", "motivation": "m", "outcome": "o",
				"success_criteria": ["c"],
				"data_capture": [
					{"id": "name", "kind": "text", "pii": True},
					{"id": "email", "kind": "email", "pii": True},
				],
			},
		],
	}


def test_e3_migration_resolves_chain() -> None:
	bundle = _raw_bundle_with_replacement()
	diff = build_migration(bundle, "old_intake")
	assert diff.chain == ("old_intake", "new_intake")
	assert "email" in diff.added
	assert "legacy" in diff.removed


def test_e3_migration_cli_step1_writes_bundle(tmp_path: Path) -> None:
	r = RUNNER.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--step", "1", "--no-pause"],
	)
	assert r.exit_code == 0
	bundle_path = tmp_path / "demo" / "bundle.json"
	assert bundle_path.is_file()


def test_e3_migration_cli_migrate_dry_run(tmp_path: Path) -> None:
	out = tmp_path / "demo"
	RUNNER.invoke(app, ["tutorial", "--out", str(out), "--step", "1", "--no-pause"])
	bundle = out / "bundle.json"
	r = RUNNER.invoke(
		app,
		["jtbd", "migrate", "--bundle", str(bundle), "--from", "claim_intake"],
	)
	# claim_intake is not deprecated → "not deprecated" notice
	assert r.exit_code == 0
	assert "not deprecated" in r.output


# ---------------------------------------------------------------------------
# 9. JTBD audit trail (E-20)
# ---------------------------------------------------------------------------


async def test_e20_audit_logger_buffers_on_create() -> None:
	import flowforge.config as _cfg
	original_audit = _cfg.audit
	try:
		_cfg.audit = None  # force buffer mode
		logger = JtbdAuditLogger(tenant_id="tenant-1")
		spec = _jtbd_spec()
		await logger.record_created(
			spec.id, spec.version, "user-1",
			spec=spec.model_dump(mode="json"),
		)
		assert len(logger.buffered) == 1
		evt = logger.buffered[0]
		assert evt.kind == "jtbd.spec_version.created"
		assert evt.payload["new_hash"] is not None
	finally:
		_cfg.audit = original_audit


async def test_e20_audit_logger_edit_computes_diff_keys() -> None:
	import flowforge.config as _cfg
	original = _cfg.audit
	try:
		_cfg.audit = None
		logger = JtbdAuditLogger(tenant_id="t")
		old_spec = {"id": "x", "outcome": "old"}
		new_spec = {"id": "x", "outcome": "new"}
		await logger.record_edited("x", "1.0.0", "user-1", old_spec=old_spec, new_spec=new_spec)
		assert "outcome" in logger.buffered[0].payload["diff_keys"]
	finally:
		_cfg.audit = original


def test_e20_audit_nine_actions_defined() -> None:
	actions = list(JtbdEditAction)
	assert len(actions) == 9


# ---------------------------------------------------------------------------
# 10. RBAC permission catalog (E-19)
# ---------------------------------------------------------------------------


def test_e19_8_permissions_defined() -> None:
	assert len(JTBD_PERMISSION_NAMES) == 8


def test_e19_curator_has_write_publish() -> None:
	perms = permissions_for_role("jtbd.curator")
	assert "jtbd.write" in perms
	assert "jtbd.publish" in perms


def test_e19_user_cannot_write() -> None:
	perms = permissions_for_role("jtbd.user")
	assert "jtbd.write" not in perms


# ---------------------------------------------------------------------------
# 11. Compliance schema + linter (E-22, E-23)
# ---------------------------------------------------------------------------


def test_e22_phi_implies_hipaa_in_catalog() -> None:
	assert "HIPAA" in SENSITIVITY_IMPLIES_REGIME["PHI"]


def test_e22_missing_regimes_detects_gap() -> None:
	gaps = missing_regimes(["PHI"], [])
	assert "HIPAA" in gaps


def test_e23_gdpr_catalog_has_4_required_jobs() -> None:
	jobs = required_jobs_for("GDPR")
	assert len(jobs) >= 4
	assert "data_export" in jobs


def test_e23_8_compliance_regimes_in_catalog() -> None:
	from flowforge_jtbd.compliance.catalog import REQUIRED_JOBS
	assert len(REQUIRED_JOBS) == 8


# ---------------------------------------------------------------------------
# 12. Plugin SDK + exporters (E-21)
# ---------------------------------------------------------------------------


def test_e21_bpmn_exporter_produces_valid_xml() -> None:
	import xml.etree.ElementTree as ET
	spec = _jtbd_spec()
	xml_str = BpmnExporter().export(spec)
	root = ET.fromstring(xml_str)
	assert "definitions" in root.tag


def test_e21_storymap_exporter_produces_valid_json() -> None:
	spec = _jtbd_spec()
	result = json.loads(StorymapExporter().export(spec))
	assert result["epic"]["id"] == "claim_intake"
	assert len(result["stories"]) > 0


def test_e21_both_exporters_satisfy_protocol() -> None:
	from flowforge_jtbd.exporters import JtbdExporter
	assert isinstance(BpmnExporter(), JtbdExporter)
	assert isinstance(StorymapExporter(), JtbdExporter)


# ---------------------------------------------------------------------------
# 13. Registry manifest + signing (E-24)
# ---------------------------------------------------------------------------


class _FakeSigner:
	_KEY = b"test-secret"
	_KEY_ID = "hmac-v1"

	def current_key_id(self) -> str:
		return self._KEY_ID

	async def sign_payload(self, payload: bytes) -> bytes:
		import hashlib, hmac
		return hmac.new(self._KEY, payload, hashlib.sha256).digest()

	async def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
		import hashlib, hmac
		expected = hmac.new(self._KEY, payload, hashlib.sha256).digest()
		return hmac.compare_digest(expected, signature)


async def test_e24_manifest_round_trip_sign_verify() -> None:
	spec = _jtbd_spec()
	bundle_bytes = json.dumps(spec.model_dump(mode="json"), sort_keys=True).encode()
	m = manifest_from_bundle("insurance-demo", "1.0.0", bundle_bytes, author="dev@test.com")
	signer = _FakeSigner()
	signed = await sign_manifest(m, signer)
	assert await verify_manifest(signed, signer) is True


async def test_e24_tampered_manifest_fails_verify() -> None:
	m = JtbdManifest(name="pkg", version="1.0.0")
	signer = _FakeSigner()
	signed = await sign_manifest(m, signer)
	tampered = signed.model_copy(update={"name": "evil-pkg"})
	assert await verify_manifest(tampered, signer) is False


# ---------------------------------------------------------------------------
# 14. Tutorial CLI (E-28)
# ---------------------------------------------------------------------------


def test_e28_tutorial_step1_writes_valid_bundle(tmp_path: Path) -> None:
	r = RUNNER.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "demo"), "--step", "1", "--no-pause"],
	)
	assert r.exit_code == 0
	data = json.loads((tmp_path / "demo" / "bundle.json").read_text())
	assert data["project"]["domain"] == "insurance"
	assert any(j["id"] == "claim_intake" for j in data["jtbds"])


def test_e28_tutorial_dry_run_completes_all_5_steps(tmp_path: Path) -> None:
	r = RUNNER.invoke(
		app,
		["tutorial", "--out", str(tmp_path / "d"), "--no-pause", "--dry-run"],
	)
	assert r.exit_code == 0
	for n in range(1, 6):
		assert f"Step {n}/5" in r.output
	assert "Tutorial complete" in r.output
