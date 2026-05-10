"""Tests for v0.3.0 W4a / item 4 — guard-aware reachability checker.

Covers:

* Per-JTBD generator emits ``workflows/<id>/reachability.json`` when
  ``z3-solver`` is importable.
* Per-JTBD generator emits ``workflows/<id>/reachability_skipped.txt``
  with the ADR-004 frozen placeholder when ``z3-solver`` is not
  importable. The skipped path is exercised by patching
  ``builtins.__import__`` to raise on ``import z3``.
* Per-bundle aggregator emits ``workflows/reachability_summary.md`` in
  both modes.
* Guard satisfiability: no-guard transitions are reachable; guard
  variables not in any data_capture field land in ``unwritable_vars``.
* Byte-deterministic regen across two pipeline runs for both flag
  values.
* Fixture-coverage registry agrees with the generators' ``CONSUMES``
  declarations.
"""

from __future__ import annotations

import builtins
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import (
	_fixture_registry,
	reachability,
	reachability_summary,
)
from flowforge_cli.jtbd.normalize import normalize


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _bundle_with_branch_guard() -> dict[str, Any]:
	"""Tiny bundle with one ``branch`` edge_case → produces a guarded transition.

	The synthesiser emits a ``submit`` transition guarded by
	``context.large_loss``; the data_capture has no field with that id,
	so the unwritable-vars probe should flag it.
	"""

	return {
		"project": {
			"name": "reach-demo",
			"package": "reach_demo",
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
				"success_criteria": ["queued within 24h"],
				"data_capture": [
					{
						"id": "claimant_name",
						"kind": "text",
						"label": "Claimant",
						"required": True,
						"pii": True,
					},
				],
				"edge_cases": [
					{
						"id": "large_loss",
						"condition": "loss_amount > 100000",
						"handle": "branch",
						"branch_to": "senior_triage",
					},
				],
			}
		],
	}


def _bundle_with_writable_guard_var() -> dict[str, Any]:
	"""Bundle whose guard variable IS declared as a data_capture field id.

	Used to assert the unwritable-vars probe stays empty when the guard
	variable can be populated through the synthesised form.
	"""

	bundle = _bundle_with_branch_guard()
	# Add a `large_loss` boolean field so the guard variable is "writable".
	bundle["jtbds"][0]["data_capture"].append(
		{
			"id": "large_loss",
			"kind": "boolean",
			"label": "Large loss flag",
			"required": False,
			"pii": False,
		}
	)
	return bundle


# ---------------------------------------------------------------------------
# z3-installed branch
# ---------------------------------------------------------------------------


def test_per_jtbd_emits_reachability_json_when_z3_available() -> None:
	"""z3 installed → JSON report at workflows/<id>/reachability.json."""
	pytest.importorskip("z3", reason="this test exercises the z3-installed path")
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	paths = {f.path for f in files}
	assert "workflows/claim_intake/reachability.json" in paths
	assert "workflows/claim_intake/reachability_skipped.txt" not in paths


def test_per_bundle_aggregator_emits_summary() -> None:
	"""Per-bundle aggregator always emits ``workflows/reachability_summary.md``."""
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	paths = {f.path for f in files}
	assert "workflows/reachability_summary.md" in paths


def test_reachability_json_is_well_formed_and_sorted() -> None:
	"""JSON report has the fixed schema and sorted-keys output."""
	pytest.importorskip("z3", reason="this test exercises the z3-installed path")
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	[report_file] = [f for f in files if f.path == "workflows/claim_intake/reachability.json"]
	# JSON parses; structure matches.
	data = json.loads(report_file.content)
	assert data["jtbd_id"] == "claim_intake"
	assert "summary" in data
	assert {"total", "reachable", "unreachable", "with_unwritable_vars"} <= set(
		data["summary"].keys()
	)
	# Output is sort_keys=True + trailing newline.
	assert report_file.content.endswith("\n")
	# Re-serialising the parsed object with sort_keys=True reproduces
	# the file byte-for-byte (no insertion order leak).
	assert (
		report_file.content
		== json.dumps(data, indent=2, sort_keys=True) + "\n"
	)


def test_unwritable_vars_flagged_when_guard_var_missing_field() -> None:
	"""A guard reading ``context.large_loss`` flagged when no field produces it."""
	pytest.importorskip("z3", reason="this test exercises the z3-installed path")
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	[report_file] = [
		f for f in files if f.path == "workflows/claim_intake/reachability.json"
	]
	data = json.loads(report_file.content)
	branch = next(
		t for t in data["transitions"] if t["id"] == "claim_intake_large_loss"
	)
	assert branch["guard_vars"] == ["large_loss"]
	assert branch["unwritable_vars"] == ["large_loss"]
	assert branch["reachable"] is True  # symbolically satisfiable


def test_unwritable_vars_empty_when_guard_var_has_field() -> None:
	"""Guard var declared as a data_capture field id → no unwritable_vars."""
	pytest.importorskip("z3", reason="this test exercises the z3-installed path")
	bundle = _bundle_with_writable_guard_var()
	files = generate(bundle)
	[report_file] = [
		f for f in files if f.path == "workflows/claim_intake/reachability.json"
	]
	data = json.loads(report_file.content)
	branch = next(
		t for t in data["transitions"] if t["id"] == "claim_intake_large_loss"
	)
	assert branch["guard_vars"] == ["large_loss"]
	assert "unwritable_vars" not in branch


def test_no_guard_transitions_are_reachable_without_solver_call() -> None:
	"""Transitions with no guards are reported reachable, no witness."""
	pytest.importorskip("z3", reason="this test exercises the z3-installed path")
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	[report_file] = [
		f for f in files if f.path == "workflows/claim_intake/reachability.json"
	]
	data = json.loads(report_file.content)
	submit = next(t for t in data["transitions"] if t["id"] == "claim_intake_submit")
	assert submit["guard_vars"] == []
	assert submit["reachable"] is True
	assert "witness" not in submit


def test_byte_identical_regen_with_z3() -> None:
	"""Two regens against the same bundle produce identical bytes."""
	pytest.importorskip("z3", reason="this test exercises the z3-installed path")
	bundle = _bundle_with_branch_guard()
	a = generate(bundle)
	b = generate(bundle)
	# Identical sorted file sets, identical byte content.
	a_map = {f.path: f.content for f in a}
	b_map = {f.path: f.content for f in b}
	assert a_map == b_map


# ---------------------------------------------------------------------------
# z3-not-installed branch (skipped placeholder)
# ---------------------------------------------------------------------------


@pytest.fixture
def block_z3_import(monkeypatch: pytest.MonkeyPatch):
	"""Patch ``builtins.__import__`` so ``import z3`` raises ImportError.

	The reachability generator probes ``import z3`` lazily on every
	``generate(...)`` call, so the fixture survives the import probe
	even though z3 may already be in ``sys.modules`` from earlier
	tests. We also drop ``z3`` from ``sys.modules`` to be safe.
	"""

	original = builtins.__import__

	def _blocking_import(name: str, *args: Any, **kwargs: Any) -> Any:
		if name == "z3" or name.startswith("z3."):
			raise ImportError(f"blocked by test fixture: {name}")
		return original(name, *args, **kwargs)

	# Drop already-loaded z3 so the patched import path is exercised.
	for mod_name in list(sys.modules):
		if mod_name == "z3" or mod_name.startswith("z3."):
			monkeypatch.delitem(sys.modules, mod_name, raising=False)
	monkeypatch.setattr(builtins, "__import__", _blocking_import)
	yield


def test_per_jtbd_emits_skipped_placeholder_when_z3_missing(
	block_z3_import: None,
) -> None:
	"""z3 not importable → frozen placeholder per ADR-004."""
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	paths = {f.path for f in files}
	assert "workflows/claim_intake/reachability_skipped.txt" in paths
	assert "workflows/claim_intake/reachability.json" not in paths
	[skipped] = [
		f
		for f in files
		if f.path == "workflows/claim_intake/reachability_skipped.txt"
	]
	# Frozen ADR-004 text — any drift here is a CI failure.
	assert skipped.content == reachability.SKIPPED_PLACEHOLDER
	assert skipped.content == (
		"Reachability analysis skipped: z3-solver not installed.\n"
		"Install with: pip install 'flowforge-cli[reachability]'\n"
	)


def test_summary_aggregator_marks_skipped_when_z3_missing(
	block_z3_import: None,
) -> None:
	"""Summary records ``status=skipped`` and the placeholder artefact path."""
	bundle = _bundle_with_branch_guard()
	files = generate(bundle)
	[summary] = [f for f in files if f.path == "workflows/reachability_summary.md"]
	assert "z3-solver` is **not installed**" in summary.content
	assert "reachability_skipped.txt" in summary.content
	assert "skipped" in summary.content


def test_byte_identical_regen_without_z3(block_z3_import: None) -> None:
	"""Two skipped-path regens produce identical bytes."""
	bundle = _bundle_with_branch_guard()
	a = generate(bundle)
	b = generate(bundle)
	a_map = {f.path: f.content for f in a}
	b_map = {f.path: f.content for f in b}
	assert a_map == b_map


# ---------------------------------------------------------------------------
# Fixture-registry parity
# ---------------------------------------------------------------------------


def test_fixture_registry_mirrors_generator_consumes() -> None:
	"""``CONSUMES`` on each generator agrees with the registry entry."""
	assert (
		set(reachability.CONSUMES) == set(_fixture_registry.get("reachability"))
	)
	assert (
		set(reachability_summary.CONSUMES)
		== set(_fixture_registry.get("reachability_summary"))
	)


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
	"example",
	["insurance_claim", "hiring-pipeline", "building-permit"],
)
def test_examples_emit_reachability_artefacts(example: str) -> None:
	"""Each example bundle emits a reachability artefact per JTBD + a summary."""
	bundle_path = _REPO_ROOT / "examples" / example / "jtbd-bundle.json"
	bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
	files = generate(bundle)
	paths = {f.path for f in files}
	# Per-bundle aggregator always lands.
	assert "workflows/reachability_summary.md" in paths
	# Each JTBD lands either reachability.json (z3 installed) or
	# reachability_skipped.txt (not). Same set of paths regardless of
	# z3 state — the test is run under whatever z3 state CI provides.
	norm = normalize(bundle)
	for jt in norm.jtbds:
		json_path = f"workflows/{jt.id}/reachability.json"
		txt_path = f"workflows/{jt.id}/reachability_skipped.txt"
		assert (json_path in paths) or (txt_path in paths)


# ---------------------------------------------------------------------------
# Module-level smoke imports (avoid lint warnings about importlib usage)
# ---------------------------------------------------------------------------


def test_modules_import_cleanly() -> None:
	"""Both generator modules importable from a fresh interpreter shape."""
	importlib.reload(reachability)
	importlib.reload(reachability_summary)
	assert callable(reachability.generate)
	assert callable(reachability_summary.generate)
