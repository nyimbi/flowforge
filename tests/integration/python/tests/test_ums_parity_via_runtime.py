"""Integration test #11: UMS parity twins through the live runtime.

UMS reflects 22 of its workflow definitions as JSON twins for parity
verification. Here we sample the first ``N`` twins (default 5) and run
each through the engine API end-to-end, asserting the twins parse,
register, and accept the empty event set without crashing.

The richer payload-equivalence checks (same fixture in -> same context
out) live in ``backend/tests/test_workflow_def_parity.py``; this test
proves that the *framework's* runtime can host the twins without UMS
imports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flowforge.compiler import validate
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance

pytestmark = pytest.mark.asyncio


def _candidate_twin_paths() -> list[Path]:
	"""Locate UMS workflow JSON twins.

	Looks under common locations; when nothing is found, the test is
	skipped cleanly. We do not assert the twin count — UMS reflection is
	the source of truth and may legitimately diverge between releases.
	"""
	repo_root = Path(__file__).resolve().parents[5]
	roots = [
		repo_root / "backend" / "app" / "workflows" / "definitions",
		repo_root / "backend" / "tests" / "data" / "workflow_def_twins",
		repo_root / "backend" / "data" / "workflow_def_twins",
	]
	hits: list[Path] = []
	for r in roots:
		if r.is_dir():
			hits.extend(sorted(r.glob("*.json")))
	# Also accept framework example bundles as a fallback.
	if not hits:
		ex_root = repo_root / "framework" / "examples"
		for ex in ex_root.glob("*"):
			candidate = ex / "generated" / "workflows"
			if candidate.is_dir():
				hits.extend(sorted(candidate.glob("*/definition.json")))
	return hits[:5]


async def test_each_twin_compiles_and_starts_via_runtime() -> None:
	twins = _candidate_twin_paths()
	if not twins:
		pytest.skip("no UMS workflow twins or example workflow defs found")

	tested = 0
	for path in twins:
		body = json.loads(path.read_text())
		# DSL parse.
		try:
			wd = WorkflowDef.model_validate(body)
		except Exception as exc:  # pragma: no cover — twins must parse
			pytest.fail(f"twin {path.name} failed DSL parse: {exc}")

		# Validator should at minimum produce a structured report (errors
		# are fine — we don't assert the twin is bug-free, only that the
		# runtime can host it).
		report = validate(body)
		assert isinstance(report.errors, list)
		assert isinstance(report.warnings, list)

		# Spin up an instance — must produce a fresh state matching initial_state.
		inst = new_instance(wd)
		assert inst.state == wd.initial_state

		# Try firing the first event in the def (if any). The engine should
		# not crash even if guards/gates reject the event.
		first_event = next((t.event for t in wd.transitions), None)
		if first_event is not None:
			fr = await fire(wd, inst, first_event, tenant_id="t-1")
			assert fr.new_state in {s.name for s in wd.states}
		tested += 1

	assert tested >= 1, "expected at least one twin to be exercised"
