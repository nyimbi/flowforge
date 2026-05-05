"""Shared fixtures: well-formed and broken workflow definitions used by
multiple command tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _ok_workflow() -> dict[str, Any]:
	return {
		"key": "claim_intake",
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
				"effects": [
					{"kind": "create_entity", "entity": "claim"},
					{"kind": "set", "target": "context.triage.priority", "expr": "high"},
					{"kind": "notify", "template": "claim.submitted"},
				],
			},
			{
				"id": "approve",
				"event": "approve",
				"from_state": "review",
				"to_state": "done",
				"priority": 0,
				"guards": [],
				"gates": [{"kind": "permission", "permission": "claim.approve"}],
				"effects": [],
			},
		],
	}


def _broken_workflow() -> dict[str, Any]:
	"""A workflow with a duplicate priority + an unreachable state."""

	wf = _ok_workflow()
	# Add a second submit transition with the same priority.
	wf["transitions"].append(
		{
			"id": "submit_dup",
			"event": "submit",
			"from_state": "intake",
			"to_state": "review",
			"priority": 0,
			"guards": [],
			"gates": [],
			"effects": [],
		}
	)
	# Add an unreachable state with no incoming transition.
	wf["states"].append({"name": "rescinded", "kind": "manual_review"})
	return wf


def _ok_jtbd_bundle() -> dict[str, Any]:
	return {
		"project": {
			"name": "my-claims",
			"package": "my_claims",
			"domain": "claims",
			"tenancy": "single",
		},
		"shared": {
			"roles": ["adjuster", "supervisor"],
			"permissions": ["claim.read", "claim.submit", "claim.approve"],
		},
		"jtbds": [
			{
				"id": "claim_intake",
				"title": "File a claim",
				"actor": {"role": "policyholder", "external": True},
				"situation": "policyholder needs to file an FNOL",
				"motivation": "recover insured losses",
				"outcome": "claim accepted into triage",
				"success_criteria": ["claim is queued within SLA"],
			}
		],
	}


@pytest.fixture()
def workflow_ok(tmp_path: Path) -> Path:
	path = tmp_path / "definition.json"
	path.write_text(json.dumps(_ok_workflow(), indent=2), encoding="utf-8")
	return path


@pytest.fixture()
def workflow_broken(tmp_path: Path) -> Path:
	path = tmp_path / "definition.json"
	path.write_text(json.dumps(_broken_workflow(), indent=2), encoding="utf-8")
	return path


@pytest.fixture()
def workflows_dir_ok(tmp_path: Path) -> Path:
	"""Build ``workflows/<key>/definition.json`` for two OK workflows."""

	root = tmp_path / "workflows"
	a = root / "claim_intake"
	a.mkdir(parents=True)
	(a / "definition.json").write_text(json.dumps(_ok_workflow(), indent=2), encoding="utf-8")

	# A second workflow keyed differently so we can test catalog.
	other = _ok_workflow()
	other["key"] = "claim_payout"
	other["subject_kind"] = "payment"
	b = root / "claim_payout"
	b.mkdir(parents=True)
	(b / "definition.json").write_text(json.dumps(other, indent=2), encoding="utf-8")
	return root


@pytest.fixture()
def jtbd_bundle(tmp_path: Path) -> Path:
	path = tmp_path / "bundle.json"
	path.write_text(json.dumps(_ok_jtbd_bundle(), indent=2), encoding="utf-8")
	return path
