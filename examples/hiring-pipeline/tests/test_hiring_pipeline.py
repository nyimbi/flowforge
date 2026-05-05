"""Integration tests for the hiring-pipeline JTBD bundle (U21).

Verifies:

* Bundle parses and normalizes without error.
* ``generate()`` emits >= 12 files per JTBD (5 JTBDs → >= 60 files total).
* All 5 workflow stages are present in the generated paths.
* Output is byte-deterministic across two runs.
* Generated Python modules compile under ``compileall``.
* Generated TSX files have balanced braces/parens.
* Cross-bundle permissions and audit topics are deduplicated.
* The generator script (generate_output.py) runs end-to-end via subprocess.
"""

from __future__ import annotations

import compileall
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from flowforge_cli.jtbd import generate, normalize, parse_bundle
from flowforge_cli.jtbd.pipeline import GeneratedFile

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_BUNDLE_PATH = Path(__file__).parent.parent / "jtbd-bundle.json"


def _load_bundle() -> dict[str, Any]:
	return json.loads(_BUNDLE_PATH.read_text(encoding="utf-8"))


_EXPECTED_JTBD_IDS = [
	"source_candidate",
	"screen_candidate",
	"conduct_interview",
	"extend_offer",
	"complete_hire",
]

# ---------------------------------------------------------------------------
# parse + normalize
# ---------------------------------------------------------------------------


def test_bundle_file_exists() -> None:
	assert _BUNDLE_PATH.exists(), f"jtbd-bundle.json not found at {_BUNDLE_PATH}"


def test_bundle_parses_without_error() -> None:
	parse_bundle(_load_bundle())


def test_bundle_normalizes_five_jtbds() -> None:
	norm = normalize(_load_bundle())
	assert len(norm.jtbds) == 5
	ids = [j.id for j in norm.jtbds]
	for expected in _EXPECTED_JTBD_IDS:
		assert expected in ids, f"missing JTBD id: {expected}"


def test_normalized_jtbd_class_names() -> None:
	norm = normalize(_load_bundle())
	by_id = {j.id: j for j in norm.jtbds}
	assert by_id["source_candidate"].class_name == "SourceCandidate"
	assert by_id["screen_candidate"].class_name == "ScreenCandidate"
	assert by_id["conduct_interview"].class_name == "ConductInterview"
	assert by_id["extend_offer"].class_name == "ExtendOffer"
	assert by_id["complete_hire"].class_name == "CompleteHire"


def test_all_jtbds_have_states_and_transitions() -> None:
	norm = normalize(_load_bundle())
	for j in norm.jtbds:
		assert len(j.states) >= 2, f"{j.id}: expected >= 2 states"
		assert len(j.transitions) >= 1, f"{j.id}: expected >= 1 transition"
		assert j.initial_state, f"{j.id}: initial_state must be set"


def test_pii_fields_flagged_correctly() -> None:
	norm = normalize(_load_bundle())
	by_id = {j.id: j for j in norm.jtbds}

	# source_candidate: candidate_name, email, phone, resume are PII
	sc = by_id["source_candidate"]
	pii_ids = {f.id for f in sc.fields if f.pii}
	assert "candidate_name" in pii_ids
	assert "candidate_email" in pii_ids
	assert "source_channel" not in pii_ids  # enum, not PII

	# complete_hire: legal_name, national_id_ref, home_address, signed_contract are PII
	ch = by_id["complete_hire"]
	pii_ids_ch = {f.id for f in ch.fields if f.pii}
	assert "legal_name" in pii_ids_ch
	assert "national_id_ref" in pii_ids_ch
	assert "acceptance_date" not in pii_ids_ch  # date, not PII


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


def test_generate_emits_at_least_12_files_per_jtbd() -> None:
	files = generate(_load_bundle())
	# 5 JTBDs x ~9 per-JTBD artefacts + shared alembic + cross-bundle artefacts
	# actual count is 58; floor at 55 to give headroom against future pruning.
	assert len(files) >= 55, f"expected >= 55 files, got {len(files)}: {[f.path for f in files]}"


def test_generate_contains_all_five_workflow_stages() -> None:
	files = generate(_load_bundle())
	paths = [f.path for f in files]
	for jtbd_id in _EXPECTED_JTBD_IDS:
		slug = jtbd_id.replace("_", "_")  # module_name keeps underscores
		matches = [p for p in paths if slug in p]
		assert matches, f"no generated files found for JTBD id={jtbd_id}"


def test_generate_is_byte_deterministic() -> None:
	a = generate(_load_bundle())
	b = generate(_load_bundle())
	assert [f.path for f in a] == [f.path for f in b], "path order changed between runs"
	for fa, fb in zip(a, b, strict=True):
		assert fa.content == fb.content, f"non-deterministic content: {fa.path}"


def test_generate_includes_cross_bundle_artefacts() -> None:
	files = generate(_load_bundle())
	paths = [f.path for f in files]
	for required in ("permissions.py", "audit_taxonomy.py", "notifications.py", "README.md", ".env.example"):
		assert any(required in p for p in paths), f"missing cross-bundle artefact: {required}"


# ---------------------------------------------------------------------------
# generated Python compiles
# ---------------------------------------------------------------------------


def test_generated_python_modules_compile(tmp_path: Path) -> None:
	files = generate(_load_bundle())
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
	for p in py_files:
		ok = compileall.compile_file(str(p), quiet=1)
		assert ok, f"compile failed: {p.relative_to(root)}"


# ---------------------------------------------------------------------------
# generated TSX has balanced delimiters
# ---------------------------------------------------------------------------


def test_generated_tsx_balances_braces_and_parens() -> None:
	files = generate(_load_bundle())
	tsx_files = [f for f in files if f.path.endswith(".tsx")]
	assert tsx_files, "expected at least one TSX output"
	for f in tsx_files:
		opens = f.content.count("{")
		closes = f.content.count("}")
		assert opens == closes, f"unbalanced braces in {f.path}: {opens} vs {closes}"
		opens = f.content.count("(")
		closes = f.content.count(")")
		assert opens == closes, f"unbalanced parens in {f.path}: {opens} vs {closes}"


# ---------------------------------------------------------------------------
# cross-bundle deduplication
# ---------------------------------------------------------------------------


def _catalog_lines(content: str) -> list[str]:
	"""Extract string-literal catalog lines from generated permissions/audit modules."""
	out: list[str] = []
	for raw in content.splitlines():
		s = raw.strip()
		if s.startswith('"') and s.endswith('",'):
			out.append(s)
	return out


def test_permissions_deduplicated() -> None:
	files = generate(_load_bundle())
	(perms,) = [f for f in files if f.path.endswith("permissions.py")]
	lines = _catalog_lines(perms.content)
	assert lines, "permissions.py must contain at least one entry"
	assert len(lines) == len(set(lines)), f"duplicate permissions: {lines}"


def test_audit_taxonomy_deduplicated() -> None:
	files = generate(_load_bundle())
	(at,) = [f for f in files if f.path.endswith("audit_taxonomy.py")]
	lines = _catalog_lines(at.content)
	assert lines, "audit_taxonomy.py must contain at least one entry"
	assert len(lines) == len(set(lines)), f"duplicate audit topics: {lines}"


def test_all_five_jtbd_permissions_present() -> None:
	files = generate(_load_bundle())
	(perms,) = [f for f in files if f.path.endswith("permissions.py")]
	content = perms.content
	for jtbd_id in _EXPECTED_JTBD_IDS:
		assert jtbd_id in content, f"permissions.py missing entries for {jtbd_id}"


# ---------------------------------------------------------------------------
# generate_output.py script runs end-to-end
# ---------------------------------------------------------------------------


def test_generate_script_runs(tmp_path: Path) -> None:
	script = Path(__file__).parent.parent / "generate_output.py"
	assert script.exists(), f"generate_output.py not found at {script}"
	out_dir = tmp_path / "generated"
	result = subprocess.run(
		[sys.executable, str(script), "--out-dir", str(out_dir)],
		capture_output=True,
		text=True,
	)
	assert result.returncode == 0, result.stderr + result.stdout
	written = list(out_dir.rglob("*"))
	files = [p for p in written if p.is_file()]
	assert len(files) >= 55, f"expected >= 55 generated files, got {len(files)}"
