"""U22 integration test — building-permit JTBD worked example.

Covers:
* Bundle parses and normalizes without errors.
* All 5 JTBDs are present with correct identifiers.
* Generator emits >= 50 files (5 JTBDs x ~10 artefacts + bundle files).
* Generator output is byte-deterministic across two runs.
* Every workflow definition validates against the workflow_def schema.
* Every workflow definition can be simulated to a terminal state.
* Every generated Python file compiles cleanly.
* Generated TSX files have balanced braces and parentheses.
* Cross-bundle permissions and audit topics are deduplicated.
* Generated test modules pass when collected with pytest.
* The materialized generated/ tree matches a second generator run exactly.
"""

from __future__ import annotations

import asyncio
import compileall
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.normalize import normalize
from flowforge_cli.jtbd.parse import parse_bundle

# ---------------------------------------------------------------------------
# shared fixture
# ---------------------------------------------------------------------------

_BUNDLE_PATH = Path(__file__).parent.parent / "jtbd-bundle.json"
_GENERATED_PATH = Path(__file__).parent.parent / "generated"


def _load_bundle() -> dict[str, Any]:
	with _BUNDLE_PATH.open() as f:
		return json.load(f)


# ---------------------------------------------------------------------------
# 1. parse + normalize
# ---------------------------------------------------------------------------


def test_bundle_file_exists() -> None:
	assert _BUNDLE_PATH.exists(), f"jtbd-bundle.json not found at {_BUNDLE_PATH}"


def test_bundle_parses_without_error() -> None:
	parse_bundle(_load_bundle())


def test_bundle_normalizes_to_five_jtbds() -> None:
	norm = normalize(_load_bundle())
	assert len(norm.jtbds) == 5
	ids = {j.id for j in norm.jtbds}
	assert ids == {
		"permit_intake",
		"plan_review",
		"field_inspection",
		"permit_decision",
		"permit_issuance",
	}


def test_normalized_class_names_are_pascal_case() -> None:
	norm = normalize(_load_bundle())
	expected = {
		"permit_intake": "PermitIntake",
		"plan_review": "PlanReview",
		"field_inspection": "FieldInspection",
		"permit_decision": "PermitDecision",
		"permit_issuance": "PermitIssuance",
	}
	for jt in norm.jtbds:
		assert jt.class_name == expected[jt.id], f"{jt.id}: got {jt.class_name}"


def test_normalized_table_names_are_snake_case() -> None:
	norm = normalize(_load_bundle())
	for jt in norm.jtbds:
		assert jt.table_name == jt.id, f"{jt.id}: table_name={jt.table_name}"


def test_all_jtbds_have_initial_state_intake() -> None:
	norm = normalize(_load_bundle())
	for jt in norm.jtbds:
		assert jt.initial_state == "intake", f"{jt.id}: initial_state={jt.initial_state}"


def test_field_inspection_has_rejected_state() -> None:
	norm = normalize(_load_bundle())
	jt = next(j for j in norm.jtbds if j.id == "field_inspection")
	state_names = {s["name"] for s in jt.states}
	assert "rejected" in state_names, f"expected rejected in {state_names}"


def test_field_inspection_has_escalated_state() -> None:
	norm = normalize(_load_bundle())
	jt = next(j for j in norm.jtbds if j.id == "field_inspection")
	state_names = {s["name"] for s in jt.states}
	assert "escalated" in state_names, f"expected escalated in {state_names}"


def test_plan_review_has_variance_review_branch() -> None:
	norm = normalize(_load_bundle())
	jt = next(j for j in norm.jtbds if j.id == "plan_review")
	state_names = {s["name"] for s in jt.states}
	assert "variance_review" in state_names, f"expected variance_review in {state_names}"


def test_permit_decision_has_rejected_state() -> None:
	norm = normalize(_load_bundle())
	jt = next(j for j in norm.jtbds if j.id == "permit_decision")
	state_names = {s["name"] for s in jt.states}
	assert "rejected" in state_names, f"expected rejected in {state_names}"


# ---------------------------------------------------------------------------
# 2. generator file count and determinism
# ---------------------------------------------------------------------------


def test_generate_emits_at_least_50_files() -> None:
	files = generate(_load_bundle())
	assert len(files) >= 50, f"expected >= 50 files, got {len(files)}: {[f.path for f in files]}"


def test_all_five_workflow_definitions_present() -> None:
	files = generate(_load_bundle())
	paths = [f.path for f in files]
	for jtbd_id in ("permit_intake", "plan_review", "field_inspection", "permit_decision", "permit_issuance"):
		assert any(f"workflows/{jtbd_id}/definition.json" in p for p in paths), (
			f"missing definition.json for {jtbd_id}"
		)


def test_all_five_simulation_test_modules_present() -> None:
	files = generate(_load_bundle())
	paths = [f.path for f in files]
	for jtbd_id in ("permit_intake", "plan_review", "field_inspection", "permit_decision", "permit_issuance"):
		assert any(f"backend/tests/{jtbd_id}/test_simulation.py" in p for p in paths), (
			f"missing test_simulation.py for {jtbd_id}"
		)


def test_generate_is_byte_deterministic() -> None:
	a = generate(_load_bundle())
	b = generate(_load_bundle())
	assert [f.path for f in a] == [f.path for f in b], "path lists differ between runs"
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic content: {fa.path}"


# ---------------------------------------------------------------------------
# 3. workflow_def schema validation
# ---------------------------------------------------------------------------


def test_all_workflow_definitions_are_schema_valid() -> None:
	from flowforge.compiler.validator import validate as wf_validate

	files = generate(_load_bundle())
	defs = [f for f in files if f.path.endswith("definition.json")]
	assert len(defs) == 5, f"expected 5 definition.json files, got {len(defs)}"
	for f in defs:
		raw = json.loads(f.content)
		report = wf_validate(raw)
		assert report.ok, f"{f.path}: {report.errors}"


# ---------------------------------------------------------------------------
# 4. simulator smoke tests — one per JTBD
# ---------------------------------------------------------------------------


def _simulate(def_content: str, events: list[tuple[str, dict]]) -> Any:
	from flowforge.dsl import WorkflowDef
	from flowforge.replay.simulator import simulate

	wd = WorkflowDef.model_validate(json.loads(def_content))
	loop = asyncio.new_event_loop()
	try:
		return loop.run_until_complete(simulate(wd, events=events, tenant_id="t"))
	finally:
		loop.close()


def _get_def(files: list, jtbd_id: str) -> str:
	(f,) = [f for f in files if f.path == f"workflows/{jtbd_id}/definition.json"]
	return f.content


def test_permit_intake_simulates_to_done() -> None:
	files = generate(_load_bundle())
	result = _simulate(_get_def(files, "permit_intake"), [("submit", {}), ("approve", {})])
	assert result.terminal_state == "done", result.history


def test_plan_review_simulates_to_done() -> None:
	files = generate(_load_bundle())
	result = _simulate(_get_def(files, "plan_review"), [("submit", {}), ("approve", {})])
	assert result.terminal_state == "done", result.history


def test_field_inspection_simulates_to_done() -> None:
	files = generate(_load_bundle())
	result = _simulate(_get_def(files, "field_inspection"), [("submit", {}), ("approve", {})])
	assert result.terminal_state == "done", result.history


def test_permit_decision_simulates_to_done() -> None:
	files = generate(_load_bundle())
	result = _simulate(_get_def(files, "permit_decision"), [("submit", {}), ("approve", {})])
	assert result.terminal_state == "done", result.history


def test_permit_issuance_simulates_to_done() -> None:
	files = generate(_load_bundle())
	result = _simulate(_get_def(files, "permit_issuance"), [("submit", {}), ("approve", {})])
	assert result.terminal_state == "done", result.history


def test_permit_decision_reject_path_reaches_rejected() -> None:
	files = generate(_load_bundle())
	result = _simulate(
		_get_def(files, "permit_decision"),
		[("submit", {}), ("reject", {})],
	)
	assert result.terminal_state == "rejected", result.history


def test_field_inspection_reject_path_reaches_rejected() -> None:
	files = generate(_load_bundle())
	result = _simulate(
		_get_def(files, "field_inspection"),
		[("submit", {}), ("reject", {})],
	)
	assert result.terminal_state == "rejected", result.history


# ---------------------------------------------------------------------------
# 5. Python compile check
# ---------------------------------------------------------------------------


def test_generated_python_files_compile(tmp_path: Path) -> None:
	files = generate(_load_bundle())
	py_files: list[Path] = []
	for f in files:
		if not f.path.endswith(".py"):
			continue
		dst = tmp_path / f.path
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(f.content, encoding="utf-8")
		py_files.append(dst)
	assert py_files, "expected at least one .py output"
	for p in py_files:
		ok = compileall.compile_file(str(p), quiet=1)
		assert ok, f"compile failed: {p.relative_to(tmp_path)}"


# ---------------------------------------------------------------------------
# 6. TSX brace balance
# ---------------------------------------------------------------------------


def test_generated_tsx_files_have_balanced_braces() -> None:
	files = generate(_load_bundle())
	tsx_files = [f for f in files if f.path.endswith(".tsx")]
	assert len(tsx_files) == 10, f"expected 10 TSX files (2 per JTBD), got {len(tsx_files)}"
	for f in tsx_files:
		opens = f.content.count("{")
		closes = f.content.count("}")
		assert opens == closes, f"unbalanced braces in {f.path}: {opens} vs {closes}"
		opens = f.content.count("(")
		closes = f.content.count(")")
		assert opens == closes, f"unbalanced parens in {f.path}: {opens} vs {closes}"


# ---------------------------------------------------------------------------
# 7. cross-bundle aggregations
# ---------------------------------------------------------------------------


def test_cross_bundle_permissions_contain_all_five_jtbds() -> None:
	files = generate(_load_bundle())
	(perms,) = [f for f in files if f.path.endswith("permissions.py")]
	for jtbd_id in ("permit_intake", "plan_review", "field_inspection", "permit_decision", "permit_issuance"):
		assert f"{jtbd_id}.submit" in perms.content, f"missing {jtbd_id}.submit in permissions.py"


def test_cross_bundle_permissions_no_duplicates() -> None:
	files = generate(_load_bundle())
	(perms,) = [f for f in files if f.path.endswith("permissions.py")]
	lines = [
		line.strip()
		for line in perms.content.splitlines()
		if line.strip().startswith('"') and line.strip().endswith('",')
	]
	assert len(lines) == len(set(lines)), f"duplicate entries in permissions.py: {lines}"


def test_cross_bundle_audit_topics_no_duplicates() -> None:
	files = generate(_load_bundle())
	(at,) = [f for f in files if f.path.endswith("audit_taxonomy.py")]
	lines = [
		line.strip()
		for line in at.content.splitlines()
		if line.strip().startswith('"') and line.strip().endswith('",')
	]
	assert len(lines) == len(set(lines)), f"duplicate entries in audit_taxonomy.py: {lines}"


# ---------------------------------------------------------------------------
# 8. generated test modules run with pytest
# ---------------------------------------------------------------------------


def test_generated_simulation_tests_pass(tmp_path: Path) -> None:
	files = generate(_load_bundle())
	root = tmp_path / "proj"
	root.mkdir()
	for f in files:
		dst = root / f.path
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(f.content, encoding="utf-8")

	env = os.environ.copy()
	env["PYTHONDONTWRITEBYTECODE"] = "1"
	res = subprocess.run(
		[
			sys.executable, "-m", "pytest", "backend/tests",
			"-q", "--no-header", "--import-mode=importlib",
		],
		cwd=root,
		env=env,
		capture_output=True,
		text=True,
	)
	combined = res.stdout + res.stderr
	assert res.returncode == 0, combined
	assert "passed" in combined, combined


# ---------------------------------------------------------------------------
# 9. materialized generated/ tree matches fresh generator output
# ---------------------------------------------------------------------------


def test_materialized_generated_tree_matches_generator(tmp_path: Path) -> None:
	"""The committed generated/ directory must match what the generator produces now.

	This catches stale snapshots: if someone edits jtbd-bundle.json without
	re-running the generator the test will fail with a clear diff.
	"""
	if not _GENERATED_PATH.exists():
		pytest.skip("generated/ not materialized; run the generator first")

	files = generate(_load_bundle())
	mismatches: list[str] = []
	missing: list[str] = []

	for f in files:
		on_disk = _GENERATED_PATH / f.path
		if not on_disk.exists():
			missing.append(f.path)
			continue
		disk_content = on_disk.read_text(encoding="utf-8")
		if disk_content != f.content:
			mismatches.append(f.path)

	msgs: list[str] = []
	if missing:
		msgs.append(f"files missing from generated/: {missing}")
	if mismatches:
		msgs.append(f"files differ from generator output: {mismatches}")
	assert not msgs, "\n".join(msgs)
