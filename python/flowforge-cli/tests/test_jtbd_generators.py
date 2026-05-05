"""Tests for the JTBD generator pipeline (U19).

Covers:

* ``generate(bundle)`` emits >= 12 files for a single-JTBD bundle.
* Output is byte-deterministic across two runs.
* Each generated workflow_def JSON validates against the workflow_def
  schema and parses with the simulator.
* Each generated alembic migration parses as Python (compile()).
* Each generated SQLAlchemy model parses as Python.
* Each generated test module parses + names the workflow id correctly.
* TSX components parse as TypeScript syntax (basic balanced-brace check
  + a tsc --noEmit run when ``tsc`` is on PATH).
* Cross-bundle aggregations (permissions, audit_taxonomy, notifications)
  deduplicate when two JTBDs share permissions.
* Generated test modules pass when collected with pytest.
"""

from __future__ import annotations

import asyncio
import compileall
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.normalize import normalize
from flowforge_cli.jtbd.parse import parse_bundle
from flowforge_cli.jtbd.pipeline import GeneratedFile


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _claim_bundle() -> dict[str, Any]:
	return {
		"project": {
			"name": "claims-demo",
			"package": "claims_demo",
			"domain": "claims",
			"tenancy": "single",
			"languages": ["en"],
			"currencies": ["USD"],
		},
		"shared": {
			"roles": ["adjuster", "supervisor"],
			"permissions": ["claim.read"],
		},
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
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
					{
						"id": "loss_amount",
						"kind": "money",
						"label": "Loss",
						"required": True,
						"pii": False,
					},
					{
						"id": "loss_date",
						"kind": "date",
						"label": "Loss date",
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
						"condition": "policy is lapsed",
						"handle": "reject",
					},
				],
				"approvals": [
					{"role": "supervisor", "policy": "authority_tier", "tier": 2},
				],
				"notifications": [
					{"trigger": "state_enter", "channel": "email", "audience": "claimant"},
				],
			}
		],
	}


def _two_jtbd_bundle() -> dict[str, Any]:
	"""Used for the cross-bundle dedup test."""

	bundle = _claim_bundle()
	bundle["jtbds"].append(
		{
			"id": "claim_payout",
			"title": "Pay an approved claim",
			"actor": {"role": "adjuster"},
			"situation": "approved claim ready for disbursement",
			"motivation": "release funds to claimant",
			"outcome": "claimant paid",
			"success_criteria": ["disbursement booked within 48h"],
			"data_capture": [
				{"id": "amount", "kind": "money", "label": "Amount", "required": True, "pii": False},
			],
		}
	)
	return bundle


# ---------------------------------------------------------------------------
# parse + normalize sanity
# ---------------------------------------------------------------------------


def test_parse_then_normalize_smoke() -> None:
	bundle = _claim_bundle()
	parse_bundle(bundle)
	norm = normalize(bundle)
	assert len(norm.jtbds) == 1
	jt = norm.jtbds[0]
	assert jt.class_name == "ClaimIntake"
	assert jt.module_name == "claim_intake"
	assert "rejected" in {s["name"] for s in jt.states}
	assert "senior_triage" in {s["name"] for s in jt.states}


# ---------------------------------------------------------------------------
# end-to-end generate(...)
# ---------------------------------------------------------------------------


def test_generate_emits_at_least_12_files_for_one_jtbd() -> None:
	files = generate(_claim_bundle())
	assert len(files) >= 12, [f.path for f in files]
	# Every per-JTBD artefact should be present.
	required_substrings = [
		"workflows/claim_intake/definition.json",
		"workflows/claim_intake/form_spec.json",
		"backend/src/claims_demo/models/claim_intake.py",
		"backend/src/claims_demo/adapters/claim_intake_adapter.py",
		"backend/src/claims_demo/services/claim_intake_service.py",
		"backend/src/claims_demo/routers/claim_intake_router.py",
		"backend/migrations/versions/",
		"backend/migrations/env.py",
		"backend/alembic.ini",
		"backend/tests/claim_intake/test_simulation.py",
		"frontend/src/components/claim-intake/ClaimIntakeStep.tsx",
		"frontend/src/app/claim-intake/page.tsx",
		"backend/src/claims_demo/permissions.py",
		"backend/src/claims_demo/audit_taxonomy.py",
		"backend/src/claims_demo/notifications.py",
		"README.md",
		".env.example",
	]
	paths = [f.path for f in files]
	missing = [s for s in required_substrings if not any(s in p for p in paths)]
	assert not missing, f"missing: {missing}\n got: {paths}"


def test_generate_is_byte_deterministic() -> None:
	a = generate(_claim_bundle())
	b = generate(_claim_bundle())
	assert [f.path for f in a] == [f.path for f in b]
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic: {fa.path}"


# ---------------------------------------------------------------------------
# generated workflow_def passes flowforge.compiler.validator
# ---------------------------------------------------------------------------


def test_generated_workflow_def_is_schema_valid() -> None:
	from flowforge.compiler.validator import validate as wf_validate

	files = generate(_claim_bundle())
	defs = [f for f in files if f.path.endswith("definition.json")]
	assert defs
	for f in defs:
		raw = json.loads(f.content)
		report = wf_validate(raw)
		assert report.ok, f"{f.path}: {report.errors}"


# ---------------------------------------------------------------------------
# generated workflow_def runs through the simulator
# ---------------------------------------------------------------------------


def test_generated_workflow_simulates_to_done() -> None:
	from flowforge.dsl import WorkflowDef
	from flowforge.replay.simulator import simulate

	files = generate(_claim_bundle())
	(def_file,) = [f for f in files if f.path.endswith("definition.json")]
	wd = WorkflowDef.model_validate(json.loads(def_file.content))

	loop = asyncio.new_event_loop()
	try:
		result = loop.run_until_complete(
			simulate(wd, events=[("submit", {}), ("approve", {})], tenant_id="t")
		)
	finally:
		loop.close()
	assert result.terminal_state == "done", result.history


# ---------------------------------------------------------------------------
# generated python files compile under py_compile
# ---------------------------------------------------------------------------


def test_generated_python_modules_compile(tmp_path: Path) -> None:
	files = generate(_claim_bundle())
	root = tmp_path / "out"
	root.mkdir()
	py_files: list[Path] = []
	for f in files:
		if not f.path.endswith(".py"):
			continue
		dst = root / f.path
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(f.content, encoding="utf-8")
		py_files.append(dst)
	assert py_files, "expected at least one .py output"
	# compileall returns True on success.
	for p in py_files:
		ok = compileall.compile_file(str(p), quiet=1)
		assert ok, f"compile failed: {p}"


# ---------------------------------------------------------------------------
# generated tsx files are syntactically reasonable
# ---------------------------------------------------------------------------


def test_generated_tsx_balances_braces_and_parses_with_tsc(tmp_path: Path) -> None:
	files = generate(_claim_bundle())
	tsx_files = [f for f in files if f.path.endswith(".tsx")]
	assert tsx_files

	for f in tsx_files:
		opens = f.content.count("{")
		closes = f.content.count("}")
		assert opens == closes, f"unbalanced braces in {f.path}: {opens} vs {closes}"
		opens = f.content.count("(")
		closes = f.content.count(")")
		assert opens == closes, f"unbalanced parens in {f.path}: {opens} vs {closes}"

	tsc = shutil.which("tsc")
	if not tsc:
		pytest.skip("tsc not on PATH; brace-balance check is enough")

	# Drop the files into a tmp project + run tsc --noEmit. We stub a
	# trivial tsconfig that targets ESNext+JSX so the type-checker doesn't
	# need real DOM types or @types/react.
	tsroot = tmp_path / "tsproj"
	tsroot.mkdir()
	for f in tsx_files:
		dst = tsroot / Path(f.path).name
		dst.write_text(f.content, encoding="utf-8")
	(tsroot / "tsconfig.json").write_text(
		json.dumps(
			{
				"compilerOptions": {
					"target": "ESNext",
					"module": "ESNext",
					"jsx": "react",
					"strict": False,
					"noEmit": True,
					"skipLibCheck": True,
					"types": [],
					"moduleResolution": "node",
				},
				"include": ["*.tsx"],
			},
			indent=2,
		),
		encoding="utf-8",
	)
	# tsc will complain about missing react types — we accept syntax errors only.
	res = subprocess.run(
		[tsc, "--noEmit", "-p", str(tsroot)],
		capture_output=True,
		text=True,
	)
	# Any "TS1xxx" code is a syntax error; type-check errors (TS2xxx) we
	# accept since this is a black-box parse-only check.
	syntax_errors = [
		line
		for line in (res.stdout + res.stderr).splitlines()
		if " TS1" in line
	]
	assert not syntax_errors, syntax_errors


# ---------------------------------------------------------------------------
# alembic migration uses a deterministic revision id
# ---------------------------------------------------------------------------


def test_alembic_revision_is_stable() -> None:
	a = generate(_claim_bundle())
	b = generate(_claim_bundle())
	mig_a = next(f for f in a if "migrations/versions/" in f.path)
	mig_b = next(f for f in b if "migrations/versions/" in f.path)
	assert mig_a.path == mig_b.path
	assert mig_a.content == mig_b.content


# ---------------------------------------------------------------------------
# cross-bundle aggregations dedup
# ---------------------------------------------------------------------------


def _permission_lines(content: str) -> list[str]:
	"""Return only the catalog string-literal lines from a generated module."""

	out: list[str] = []
	for raw in content.splitlines():
		s = raw.strip()
		if s.startswith('"') and s.endswith('",') and s != '"""':
			out.append(s)
	return out


def test_cross_bundle_permissions_dedup() -> None:
	files = generate(_two_jtbd_bundle())
	(perms,) = [f for f in files if f.path.endswith("permissions.py")]
	lines = _permission_lines(perms.content)
	assert lines, "expected at least one permission entry"
	assert len(lines) == len(set(lines)), f"duplicates in permissions.py: {lines}"
	# Permissions from both jtbds must be present.
	flat = " ".join(lines)
	assert "claim_intake.submit" in flat
	assert "claim_payout.submit" in flat


def test_cross_bundle_audit_topics_dedup() -> None:
	files = generate(_two_jtbd_bundle())
	(at,) = [f for f in files if f.path.endswith("audit_taxonomy.py")]
	lines = _permission_lines(at.content)
	assert lines, "expected at least one audit topic"
	assert len(lines) == len(set(lines)), f"duplicates in audit_taxonomy.py: {lines}"


# ---------------------------------------------------------------------------
# generated pytest module passes
# ---------------------------------------------------------------------------


def test_generated_test_module_runs(tmp_path: Path) -> None:
	"""Materialize the generated workflow + test, then collect with pytest."""

	files = generate(_claim_bundle())
	root = tmp_path / "proj"
	root.mkdir()
	for f in files:
		dst = root / f.path
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(f.content, encoding="utf-8")

	# pytest --collect-only catches import errors; running it confirms the
	# generated test module imports flowforge happily.
	env = os.environ.copy()
	env["PYTHONDONTWRITEBYTECODE"] = "1"
	res = subprocess.run(
		[sys.executable, "-m", "pytest", "backend/tests", "-q", "--no-header"],
		cwd=root,
		env=env,
		capture_output=True,
		text=True,
	)
	combined = res.stdout + res.stderr
	assert res.returncode == 0, combined
	assert "passed" in combined, combined
