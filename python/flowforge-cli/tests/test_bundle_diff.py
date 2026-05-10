"""Tests for ``flowforge bundle-diff`` (W3 item 10).

Covers:

* Categorisation rules:
  - new JTBD → ADDITIVE
  - new optional field → ADDITIVE
  - new required field → REQUIRES_COORDINATION
  - removed field → BREAKING
  - field kind narrowed → BREAKING
  - field kind changed (non-narrowing) → REQUIRES_COORDINATION
  - field required false → true → REQUIRES_COORDINATION
  - field required true → false → ADDITIVE
  - shared.permissions added → REQUIRES_COORDINATION
  - shared.permissions removed → BREAKING
  - shared.roles added → REQUIRES_COORDINATION
  - shared.roles removed → BREAKING
  - validation.enum value removed → BREAKING
  - validation.enum value added → ADDITIVE
  - edge_case branch_to retargeted → BREAKING
  - edge_case handle changed → BREAKING
  - new edge_case → ADDITIVE
  - JTBD removed → BREAKING
  - SLA tightened → REQUIRES_COORDINATION
  - SLA relaxed → ADDITIVE
  - notification add/remove → ADDITIVE both ways
  - PII flag promoted → REQUIRES_COORDINATION

* Output formats:
  - text (default) prints totals + per-row class label
  - --json file is deterministic (two runs, byte-identical)
  - --html file is single-file standalone (contains <style> + <script>
    inline, no external assets)

* CLI wiring:
  - exit 0 when only additive findings
  - exit 1 when any blocking finding present
  - --exit-zero suppresses the non-zero exit

* Integration: diff two checked-in versions of insurance_claim:
  - old: as-of-W0 (no form_renderer="real", no fraud_detected
    compensate edge_case)
  - new: as-of-W1 (current — form_renderer="real" + fraud_detected
    compensate edge)
  Asserts the W1 changes show up under the right classes.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flowforge_cli.commands.bundle_diff import (
	Change,
	compute_diff,
	render_html,
	render_json,
	render_text,
)
from flowforge_cli.main import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_bundle() -> dict[str, Any]:
	"""Minimal valid-shape bundle the tests mutate as needed."""

	return {
		"project": {
			"name": "demo",
			"package": "demo_pkg",
			"domain": "demo",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
			"frontend_framework": "nextjs",
			"frontend": {"form_renderer": "skeleton"},
		},
		"shared": {
			"roles": ["adjuster", "claimant"],
			"permissions": ["claim.read"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "claimant", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within SLA"],
				"data_capture": [
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant name",
						"required": True,
						"pii": True,
					},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Loss amount",
						"required": True,
						"pii": False,
					},
					{
						"id": "channel",
						"kind": "enum",
						"label": "Source",
						"required": False,
						"pii": False,
						"validation": {"enum": ["web", "phone", "email"]},
					},
				],
				"edge_cases": [
					{
						"id": "large_loss",
						"condition": "loss_amount > 100000",
						"handle": "branch",
						"branch_to": "senior_triage",
					}
				],
				"notifications": [
					{"trigger": "state_enter", "channel": "email", "audience": "claimant"}
				],
				"sla": {"warn_pct": 80, "breach_seconds": 86400},
			}
		],
	}


def _categories(changes: list[Change]) -> set[tuple[str, str]]:
	"""Convenience: ``{(kind, category), ...}`` for assertion clarity."""

	return {(c.kind.value, c.category) for c in changes}


# ---------------------------------------------------------------------------
# Categorisation rules
# ---------------------------------------------------------------------------


def test_no_changes_yields_empty_report() -> None:
	bundle = _base_bundle()
	rep = compute_diff(bundle, copy.deepcopy(bundle))
	assert rep.changes == []
	assert not rep.has_blocking()
	assert rep.counts() == {
		"additive": 0,
		"requires-coordination": 0,
		"breaking": 0,
	}


def test_new_jtbd_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"].append(
		{
			"id": "claim_payout",
			"title": "Pay a claim",
			"actor": {"role": "adjuster"},
			"situation": "x",
			"motivation": "y",
			"outcome": "z",
			"success_criteria": ["q"],
		}
	)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "jtbd_added") in cats
	assert not rep.has_blocking()


def test_jtbd_removed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"] = []
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "jtbd_removed") in cats
	assert rep.has_blocking()


def test_new_optional_field_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["data_capture"].append(
		{
			"id": "notes",
			"kind": "textarea",
			"label": "Notes",
			"required": False,
			"pii": False,
		}
	)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "optional_field_added") in cats
	assert not rep.has_blocking()


def test_new_required_field_is_requires_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["data_capture"].append(
		{
			"id": "incident_date",
			"kind": "date",
			"label": "Incident date",
			"required": True,
			"pii": False,
		}
	)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "required_field_added") in cats
	assert rep.has_blocking()


def test_field_removed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["data_capture"] = [
		f for f in old["jtbds"][0]["data_capture"] if f["id"] != "channel"
	]
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "field_removed") in cats


def test_field_kind_narrowed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	# textarea (width 100) → text (width 50) is a narrowing.
	old["jtbds"][0]["data_capture"].append(
		{
			"id": "loss_description",
			"kind": "textarea",
			"label": "Description",
			"required": False,
			"pii": False,
		}
	)
	new["jtbds"][0]["data_capture"].append(
		{
			"id": "loss_description",
			"kind": "text",
			"label": "Description",
			"required": False,
			"pii": False,
		}
	)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "field_kind_narrowed") in cats


def test_field_kind_changed_non_narrowing_is_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	# text (50) → textarea (100) is a widening — coord-class.
	old["jtbds"][0]["data_capture"].append(
		{"id": "extra", "kind": "text", "label": "Extra", "required": False, "pii": False}
	)
	new["jtbds"][0]["data_capture"].append(
		{"id": "extra", "kind": "textarea", "label": "Extra", "required": False, "pii": False}
	)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "field_kind_changed") in cats


def test_field_required_tightened_is_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	# channel: required false → true
	for f in new["jtbds"][0]["data_capture"]:
		if f["id"] == "channel":
			f["required"] = True
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "field_required_tightened") in cats


def test_field_required_relaxed_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	for f in new["jtbds"][0]["data_capture"]:
		if f["id"] == "claimant_name":
			f["required"] = False
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "field_required_relaxed") in cats
	# This is the only delta — the report shouldn't be blocking.
	assert not rep.has_blocking()


def test_field_pii_promoted_is_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	for f in new["jtbds"][0]["data_capture"]:
		if f["id"] == "loss_amount":
			f["pii"] = True
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "field_pii_promoted") in cats


def test_enum_value_removed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	for f in new["jtbds"][0]["data_capture"]:
		if f["id"] == "channel":
			f["validation"] = {"enum": ["web", "phone"]}
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "enum_value_removed") in cats


def test_enum_value_added_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	for f in new["jtbds"][0]["data_capture"]:
		if f["id"] == "channel":
			f["validation"] = {"enum": ["web", "phone", "email", "chat"]}
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "enum_value_added") in cats


def test_shared_permission_added_is_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"].append("claim.escalate")
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "shared_permission_added") in cats


def test_shared_permission_removed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"] = []
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "shared_permission_removed") in cats


def test_shared_role_added_is_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["roles"].append("supervisor")
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "shared_role_added") in cats


def test_shared_role_removed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["roles"] = ["claimant"]
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "shared_role_removed") in cats


def test_edge_case_added_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["edge_cases"].append(
		{"id": "lapsed", "condition": "policy lapsed", "handle": "reject"}
	)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "edge_case_added") in cats


def test_edge_case_branch_retargeted_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	for ec in new["jtbds"][0]["edge_cases"]:
		if ec["id"] == "large_loss":
			ec["branch_to"] = "executive_triage"
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "edge_case_branch_retargeted") in cats


def test_edge_case_handle_changed_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	for ec in new["jtbds"][0]["edge_cases"]:
		if ec["id"] == "large_loss":
			ec["handle"] = "escalate"
			ec.pop("branch_to", None)
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "edge_case_handle_changed") in cats


def test_sla_tightened_is_coordination() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["sla"]["breach_seconds"] = 3600
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("requires-coordination", "sla_tightened") in cats


def test_sla_relaxed_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["sla"]["breach_seconds"] = 172800
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "sla_relaxed") in cats


def test_notification_changes_are_additive_both_ways() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	# Replace the email notification with a slack one — that's one
	# remove + one add, both ADDITIVE.
	new["jtbds"][0]["notifications"] = [
		{"trigger": "state_enter", "channel": "slack", "audience": "claimant"}
	]
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "notification_added") in cats
	assert ("additive", "notification_removed") in cats
	# These notification deltas alone shouldn't be blocking.
	assert not rep.has_blocking()


def test_form_renderer_skeleton_to_real_is_additive() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["project"]["frontend"]["form_renderer"] = "real"
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("additive", "form_renderer_upgraded") in cats


def test_package_rename_is_breaking() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["project"]["package"] = "demo_pkg_v2"
	rep = compute_diff(old, new)
	cats = _categories(rep.changes)
	assert ("breaking", "project_package_changed") in cats


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------


def test_json_output_is_deterministic() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"].append("claim.escalate")
	new["jtbds"][0]["data_capture"].append(
		{"id": "notes", "kind": "textarea", "label": "Notes", "required": False, "pii": False}
	)
	a = render_json(compute_diff(old, new))
	b = render_json(compute_diff(old, new))
	assert a == b
	# Round-trip parses cleanly.
	payload = json.loads(a)
	assert payload["counts"]["additive"] >= 1
	assert payload["counts"]["requires-coordination"] >= 1
	assert payload["has_blocking"] is True
	# Changes are sorted (kind asc severity → path → category) — the
	# breaking/coord ones land first.
	first_kinds = [c["kind"] for c in payload["changes"]]
	# Most-severe first: breaking < requires-coordination < additive.
	severity_rank = {"breaking": 0, "requires-coordination": 1, "additive": 2}
	ranked = [severity_rank[k] for k in first_kinds]
	assert ranked == sorted(ranked)


def test_html_output_is_self_contained() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"].append("claim.escalate")
	html = render_html(compute_diff(old, new))
	# Single-file: inline style + inline script, no remote refs.
	assert "<style>" in html
	assert "<script>" in html
	assert "<link " not in html.lower()
	assert "src=\"http" not in html
	assert "href=\"http" not in html
	# Renders the kind chips for filtering.
	assert "data-kind=\"breaking\"" in html
	assert "data-kind=\"requires-coordination\"" in html
	assert "data-kind=\"additive\"" in html


def test_text_output_includes_totals() -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"].append("claim.escalate")
	out = render_text(compute_diff(old, new))
	assert "bundle-diff" in out
	assert "totals:" in out
	assert "requires-coordination=1" in out


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _write_json(path: Path, obj: Any) -> Path:
	path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
	return path


def test_cli_exits_zero_on_only_additive(tmp_path: Path) -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["jtbds"][0]["data_capture"].append(
		{"id": "notes", "kind": "textarea", "label": "Notes", "required": False, "pii": False}
	)
	a = _write_json(tmp_path / "old.json", old)
	b = _write_json(tmp_path / "new.json", new)
	r = runner.invoke(app, ["bundle-diff", str(a), str(b)])
	assert r.exit_code == 0, r.output
	assert "additive=1" in r.output


def test_cli_exits_one_on_blocking(tmp_path: Path) -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"] = []  # remove permission → breaking
	a = _write_json(tmp_path / "old.json", old)
	b = _write_json(tmp_path / "new.json", new)
	r = runner.invoke(app, ["bundle-diff", str(a), str(b)])
	assert r.exit_code == 1, r.output


def test_cli_exit_zero_flag_overrides(tmp_path: Path) -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"] = []  # remove permission → breaking
	a = _write_json(tmp_path / "old.json", old)
	b = _write_json(tmp_path / "new.json", new)
	r = runner.invoke(app, ["bundle-diff", str(a), str(b), "--exit-zero"])
	assert r.exit_code == 0, r.output


def test_cli_writes_json_and_html(tmp_path: Path) -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"].append("claim.escalate")
	a = _write_json(tmp_path / "old.json", old)
	b = _write_json(tmp_path / "new.json", new)
	json_out = tmp_path / "report.json"
	html_out = tmp_path / "report.html"
	r = runner.invoke(
		app,
		[
			"bundle-diff",
			str(a),
			str(b),
			"--json",
			str(json_out),
			"--html",
			str(html_out),
		],
	)
	assert r.exit_code == 1, r.output  # coord finding → blocking
	assert json_out.is_file()
	assert html_out.is_file()
	payload = json.loads(json_out.read_text(encoding="utf-8"))
	assert payload["counts"]["requires-coordination"] >= 1
	html = html_out.read_text(encoding="utf-8")
	assert "<table>" in html


def test_cli_rejects_invalid_json(tmp_path: Path) -> None:
	a = tmp_path / "old.json"
	a.write_text("not json", encoding="utf-8")
	b = _write_json(tmp_path / "new.json", _base_bundle())
	r = runner.invoke(app, ["bundle-diff", str(a), str(b)])
	# Typer surfaces BadParameter as exit code 2.
	assert r.exit_code == 2, r.output


# ---------------------------------------------------------------------------
# Integration: insurance_claim as-of-W0 vs as-of-W1
# ---------------------------------------------------------------------------


def _insurance_claim_w0() -> dict[str, Any]:
	"""W0 baseline: pre-W1 form_renderer flag, pre-W0 fraud_detected edge."""

	return {
		"project": {
			"name": "insurance-claim-demo",
			"package": "insurance_claim_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD", "ZAR"],
			"frontend_framework": "nextjs",
			# No frontend.form_renderer block — pre-W1.
		},
		"shared": {
			"roles": ["adjuster", "supervisor", "claimant"],
			"permissions": ["claim_intake.read"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File an insurance claim (FNOL)",
				"actor": {"role": "claimant", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["queued within SLA"],
				"data_capture": [
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant full name",
						"required": True,
						"pii": True,
					},
					{
						"id": "policy_number",
						"kind": "text",
						"label": "Policy number",
						"required": True,
						"pii": False,
					},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Estimated loss amount",
						"required": True,
						"pii": False,
					},
				],
				"edge_cases": [
					{
						"id": "large_loss",
						"condition": "loss_amount > 100000",
						"handle": "branch",
						"branch_to": "senior_triage",
					},
					{
						"id": "lapsed",
						"condition": "policy lapsed at date of loss",
						"handle": "reject",
					},
					# NOTE: no fraud_detected compensate edge yet (W0).
				],
				"notifications": [
					{
						"trigger": "state_enter",
						"channel": "email",
						"audience": "claimant",
					}
				],
				"sla": {"warn_pct": 80, "breach_seconds": 86400},
			}
		],
	}


def _insurance_claim_w1() -> dict[str, Any]:
	"""W1: form_renderer flipped to ``real`` + fraud_detected compensate edge."""

	bundle = _insurance_claim_w0()
	bundle["project"]["frontend"] = {"form_renderer": "real"}
	bundle["jtbds"][0]["edge_cases"].append(
		{
			"id": "fraud_detected",
			"condition": "context.fraud_detected",
			"handle": "compensate",
		}
	)
	return bundle


def test_integration_insurance_claim_w0_to_w1() -> None:
	"""The W0 → W1 jump should surface the form_renderer upgrade and the
	fraud_detected compensate edge as ADDITIVE — neither is blocking."""

	rep = compute_diff(
		_insurance_claim_w0(),
		_insurance_claim_w1(),
		old_label="insurance_claim@W0",
		new_label="insurance_claim@W1",
	)
	cats = _categories(rep.changes)
	# form_renderer skeleton (default) → real lands as the upgrade flavour.
	assert ("additive", "form_renderer_upgraded") in cats
	# New compensate edge case lands additively.
	assert ("additive", "edge_case_added") in cats
	# The W1 upgrade is non-blocking.
	assert not rep.has_blocking(), [
		(c.kind.value, c.category, c.path) for c in rep.changes
	]


def test_integration_insurance_claim_cli_run(tmp_path: Path) -> None:
	"""End-to-end CLI invocation against the W0/W1 fixture pair."""

	a = _write_json(tmp_path / "w0.json", _insurance_claim_w0())
	b = _write_json(tmp_path / "w1.json", _insurance_claim_w1())
	json_out = tmp_path / "diff.json"
	html_out = tmp_path / "diff.html"
	r = runner.invoke(
		app,
		[
			"bundle-diff",
			str(a),
			str(b),
			"--json",
			str(json_out),
			"--html",
			str(html_out),
		],
	)
	# Only additive findings → exit 0.
	assert r.exit_code == 0, r.output
	assert json_out.is_file()
	assert html_out.is_file()
	payload = json.loads(json_out.read_text(encoding="utf-8"))
	assert payload["counts"]["breaking"] == 0
	assert payload["counts"]["requires-coordination"] == 0
	assert payload["counts"]["additive"] >= 2  # at least the two W1 deltas
	assert payload["has_blocking"] is False


# ---------------------------------------------------------------------------
# Determinism — two runs yield byte-identical reports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("renderer", [render_json, render_html, render_text])
def test_renderers_are_deterministic(renderer: Any) -> None:
	old = _base_bundle()
	new = copy.deepcopy(old)
	new["shared"]["permissions"].append("claim.escalate")
	new["jtbds"][0]["data_capture"].append(
		{"id": "notes", "kind": "textarea", "label": "Notes", "required": False, "pii": False}
	)
	a = renderer(compute_diff(old, new))
	b = renderer(compute_diff(old, new))
	assert a == b
