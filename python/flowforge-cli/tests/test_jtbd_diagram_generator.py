"""Tests for the per-JTBD ``diagram.mmd`` generator (W1 / item 19).

The generator is validated at three depths:

1. Lightweight regex grammar check — runs in every CI, no external deps.
2. End-to-end ``mmdc --parseOnly`` against every emitted ``.mmd`` —
   only runs when the ``mermaid-cli`` binary is on ``PATH`` (skipped
   otherwise so CI without node is unaffected). Catches any future
   mermaid-syntax regression that the regex check might miss.
3. Determinism + byte-identical regen — covered by the dedicated
   ``test_pipeline_is_byte_deterministic_for_examples`` case below.



The generator emits one ``workflows/<jtbd>/diagram.mmd`` per JTBD plus
embeds each diagram into the per-bundle README. Verification covers:

* mermaid ``stateDiagram-v2`` syntactic shape (header, declarations,
  arrow forms, ``[*]`` start/end markers, class assignments)
* swimlane colouring by actor role
* terminal-state styling distinct from the synthesised compensation lane
* priority-derived line styling (solid / dashed / dotted)
* SLA annotation on the canonical ``review`` state
* per-JTBD-id determinism — two runs produce byte-identical output
* fixture-registry coverage parity (``CONSUMES`` mirrors the registry)
* end-to-end pipeline integration: each example bundle (insurance,
  hiring, building-permit) emits one ``.mmd`` per JTBD and the README
  embeds every diagram inside a ``mermaid`` fenced block.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from flowforge_cli.jtbd import generate
from flowforge_cli.jtbd.generators import _fixture_registry
from flowforge_cli.jtbd.generators import diagram as gen
from flowforge_cli.jtbd.normalize import normalize


_INSURANCE_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "insurance_claim"
	/ "jtbd-bundle.json"
)
_BUILDING_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "building-permit"
	/ "jtbd-bundle.json"
)
_HIRING_BUNDLE = (
	Path(__file__).resolve().parents[3]
	/ "examples"
	/ "hiring-pipeline"
	/ "jtbd-bundle.json"
)


def _load_normalized(path: Path):
	raw = json.loads(path.read_text(encoding="utf-8"))
	return normalize(raw)


# Lightweight grammar check: the parts of a stateDiagram-v2 source the
# generator promises to emit. Not a full mermaid parser — that lives in
# the JS toolchain — but enough that a malformed emit (missing header,
# unterminated note, bad arrow shape) trips the suite.
_REQUIRED_HEADER_LINES: tuple[str, ...] = (
	"---",
	"stateDiagram-v2",
	"\tdirection LR",
)
_CLASSDEF_RE = re.compile(r"^\tclassDef \w+ ")
_NOTE_OPEN_RE = re.compile(r"^\tnote right of \w+$")
_NOTE_CLOSE_RE = re.compile(r"^\tend note$")


def _grammar_check(mmd: str) -> None:
	"""Reject obviously-malformed mermaid: unmatched notes, missing header."""

	# Required headers all present in declaration order.
	for required in _REQUIRED_HEADER_LINES:
		assert required in mmd.splitlines(), f"missing required line: {required!r}"

	# Notes are balanced.
	opens = sum(1 for ln in mmd.splitlines() if _NOTE_OPEN_RE.match(ln))
	closes = sum(1 for ln in mmd.splitlines() if _NOTE_CLOSE_RE.match(ln))
	assert opens == closes, f"unbalanced notes: {opens} open, {closes} close"

	# At least one [*] --> X start marker.
	assert any(line.startswith("\t[*] --> ") for line in mmd.splitlines())
	# At least one X --> [*] end marker.
	assert any(line.strip().endswith("--> [*]") for line in mmd.splitlines())

	# At least one classDef (every JTBD has at least one swimlane).
	assert any(_CLASSDEF_RE.match(ln) for ln in mmd.splitlines())


# ---------------------------------------------------------------------------
# generator output shape
# ---------------------------------------------------------------------------


def test_emits_one_mmd_for_insurance_claim() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	out = gen.generate(bundle, jt)
	assert out.path == "workflows/claim_intake/diagram.mmd"
	assert out.content.startswith("---\n")
	assert "stateDiagram-v2" in out.content


def test_emits_per_jtbd_for_building_permit() -> None:
	bundle = _load_normalized(_BUILDING_BUNDLE)
	files = [gen.generate(bundle, jt) for jt in bundle.jtbds]
	# 5 JTBDs in the building-permit bundle.
	assert len(files) == 5
	paths = {f.path for f in files}
	assert all(p.startswith("workflows/") and p.endswith("/diagram.mmd") for p in paths)


def test_pipeline_emits_diagram_for_every_example_jtbd() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		all_files = generate(raw)
		mmd_files = [f for f in all_files if f.path.endswith("/diagram.mmd")]
		expected_count = len(raw["jtbds"])
		assert len(mmd_files) == expected_count, f"{path.name}: {len(mmd_files)} mmd files"


def test_pipeline_no_pre_rendered_svg_emitted() -> None:
	"""Determinism contract: the pipeline never emits ``diagram.svg``.

	Per the v0.3.0 plan Principle 1, pre-rendered SVG is non-deterministic
	across mermaid-cli versions and lives outside the pipeline.
	"""

	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		files = generate(raw)
		assert all(not f.path.endswith(".svg") for f in files), path.name


# ---------------------------------------------------------------------------
# mermaid syntax
# ---------------------------------------------------------------------------


def test_mmd_grammar_check_for_each_example() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		bundle = _load_normalized(path)
		for jt in bundle.jtbds:
			mmd = gen.build_mmd(bundle, jt)
			_grammar_check(mmd)


def test_mmd_starts_with_yaml_title_block() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# YAML frontmatter title with the canonical "id — title" form.
	assert mmd.splitlines()[0] == "---"
	assert mmd.splitlines()[1] == "title: claim_intake — File an insurance claim (FNOL)"
	assert mmd.splitlines()[2] == "---"


def test_mmd_includes_initial_state_arrow() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	assert "[*] --> intake" in mmd


def test_mmd_includes_terminal_exit_arrows() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# All terminal states get an exit to [*].
	assert "done --> [*]" in mmd
	assert "rejected --> [*]" in mmd
	assert "compensated --> [*]" in mmd


# ---------------------------------------------------------------------------
# swimlane colouring by actor role
# ---------------------------------------------------------------------------


def test_swimlane_classdef_per_actor_role() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# claimant + reviewer + supervisor swimlanes are emitted.
	assert "classDef swimlane_claimant" in mmd
	assert "classDef swimlane_reviewer" in mmd
	assert "classDef swimlane_supervisor" in mmd


def test_swimlane_class_assignments_per_state() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	assert "class intake swimlane_claimant" in mmd
	assert "class review swimlane_reviewer" in mmd
	assert "class senior_triage swimlane_reviewer" in mmd
	assert "class escalated swimlane_supervisor" in mmd


# ---------------------------------------------------------------------------
# terminal kinds + compensation lane
# ---------------------------------------------------------------------------


def test_terminal_kinds_classed_distinctly() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# Green for success, red for fail.
	assert "classDef terminal_success" in mmd and "#16a34a" in mmd
	assert "classDef terminal_fail" in mmd and "#dc2626" in mmd
	assert "class done terminal_success" in mmd
	assert "class rejected terminal_fail" in mmd


def test_compensation_lane_overrides_terminal_fail() -> None:
	"""``compensated`` is a ``terminal_fail`` to the engine but reads as the
	saga-compensation lane visually — blue dashed, distinct from a hard
	reject."""

	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	assert "classDef compensation" in mmd
	assert "class compensated compensation" in mmd
	# Compensate transition carries the saga-rollback glyph in its label.
	assert "⤺" in mmd
	# The glyph + event sit on the same transition line.
	assert re.search(r"⤺ compensate", mmd) is not None


def test_no_compensation_classdef_when_no_compensate_edge() -> None:
	"""Bundle without ``handle: compensate`` must not emit the
	compensation classDef — keeps the diagram lean and prevents stray
	references in the rendered output."""

	bundle = _load_normalized(_BUILDING_BUNDLE)
	# building-permit declares no compensate edges.
	for jt in bundle.jtbds:
		mmd = gen.build_mmd(bundle, jt)
		assert "classDef compensation" not in mmd, jt.id
		assert "class compensated compensation" not in mmd, jt.id


# ---------------------------------------------------------------------------
# priority-derived line styling
# ---------------------------------------------------------------------------


def test_priority_0_carries_happy_path_glyph() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# Solid bullet for happy-path transitions.
	assert "● submit" in mmd  # claim_intake_submit P0
	assert "● approve" in mmd  # claim_intake_approve P0


def test_priority_5_plus_carries_dashed_glyph() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# Dashed glyph for edge-case priority 5..9.
	assert "┄" in mmd
	# At least one P5+ transition (large_loss P5 / lapsed_reject P6).
	assert re.search(r"┄ submit \[context\.large_loss\]", mmd) is not None


def test_priority_10_plus_carries_dotted_glyph() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# Dotted glyph for escalation priority 10+.
	assert "┈" in mmd
	# claim_intake_escalate is P10.
	assert re.search(r"┈ escalate", mmd) is not None


def test_priority_in_label() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# Every transition labels its priority for readability.
	assert "(P0)" in mmd
	assert "(P5)" in mmd
	assert "(P10)" in mmd


def test_guard_var_in_label() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# branch + compensate transitions read their guard var into the label.
	assert "[context.large_loss]" in mmd
	assert "[context.fraud_detected]" in mmd


# ---------------------------------------------------------------------------
# SLA annotation
# ---------------------------------------------------------------------------


def test_sla_note_on_review_state_when_breach_seconds_set() -> None:
	bundle = _load_normalized(_INSURANCE_BUNDLE)
	(jt,) = bundle.jtbds
	mmd = gen.build_mmd(bundle, jt)
	# claim_intake declares 86400 = 24h.
	assert "note right of review" in mmd
	assert "24h SLA" in mmd
	assert "end note" in mmd


def test_no_sla_note_when_no_breach_seconds() -> None:
	"""A JTBD without ``sla.breach_seconds`` emits no SLA annotation."""

	bundle = _load_normalized(_BUILDING_BUNDLE)
	# permit_issuance has no sla declaration.
	pi = next(j for j in bundle.jtbds if j.id == "permit_issuance")
	mmd = gen.build_mmd(bundle, pi)
	if pi.sla_breach_seconds is None:
		assert "note right of review" not in mmd


def test_sla_unit_prefers_hours_over_days() -> None:
	"""24h budget renders as ``24h SLA`` (not ``1d SLA``) so existing
	operator dashboards keying off the hour count keep working."""

	assert gen._format_sla(86400) == "24h SLA"
	assert gen._format_sla(3600) == "1h SLA"
	assert gen._format_sla(172800) == "48h SLA"
	assert gen._format_sla(60) == "1m SLA"
	assert gen._format_sla(90) == "90s SLA"


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_build_mmd_is_byte_deterministic_per_jtbd() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		bundle = _load_normalized(path)
		for jt in bundle.jtbds:
			a = gen.build_mmd(bundle, jt)
			b = gen.build_mmd(bundle, jt)
			assert a == b, f"non-deterministic: {path.name} / {jt.id}"


def test_pipeline_is_byte_deterministic_for_examples() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		first = generate(raw)
		second = generate(raw)
		first_paths = [f.path for f in first]
		second_paths = [f.path for f in second]
		assert first_paths == second_paths
		for fa, fb in zip(first, second, strict=True):
			assert fa.content == fb.content, f"{path.name}: {fa.path} non-deterministic"


# ---------------------------------------------------------------------------
# README embedding
# ---------------------------------------------------------------------------


def test_readme_embeds_mermaid_block_per_jtbd() -> None:
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		files = generate(raw)
		(readme,) = [f for f in files if f.path == "README.md"]
		# ``mermaid`` fenced blocks: one per JTBD.
		fenced_count = readme.content.count("```mermaid")
		assert fenced_count == len(raw["jtbds"]), (path.name, fenced_count)
		# Each diagram source path is linked.
		for jt in raw["jtbds"]:
			assert f"workflows/{jt['id']}/diagram.mmd" in readme.content


def test_readme_diagram_section_includes_title() -> None:
	raw = json.loads(_INSURANCE_BUNDLE.read_text(encoding="utf-8"))
	files = generate(raw)
	(readme,) = [f for f in files if f.path == "README.md"]
	assert "## State-machine diagrams" in readme.content
	# stateDiagram-v2 source sits inside the mermaid block.
	assert "stateDiagram-v2" in readme.content


# ---------------------------------------------------------------------------
# fixture-registry coverage
# ---------------------------------------------------------------------------


def test_consumes_declared_in_fixture_registry() -> None:
	registry_view = _fixture_registry.get("diagram")
	assert registry_view == gen.CONSUMES


def test_fixture_registry_lists_diagram() -> None:
	assert "diagram" in _fixture_registry.all_generators()


# ---------------------------------------------------------------------------
# helper unit tests
# ---------------------------------------------------------------------------


def test_swimlane_class_sanitises_unsafe_characters() -> None:
	# Hyphenated role becomes an underscore-joined safe identifier.
	assert gen._swimlane_class("plan-reviewer") == "swimlane_plan_reviewer"
	assert gen._swimlane_class("foo bar") == "swimlane_foo_bar"
	assert gen._swimlane_class("ok_role") == "swimlane_ok_role"


def test_guard_var_extracts_first_expr_var() -> None:
	t = {
		"guards": [
			{"kind": "expr", "expr": {"var": "context.large_loss"}},
			{"kind": "expr", "expr": {"var": "context.other"}},
		]
	}
	assert gen._guard_var(t) == "context.large_loss"


def test_guard_var_returns_none_for_no_guards() -> None:
	assert gen._guard_var({}) is None
	assert gen._guard_var({"guards": []}) is None
	assert gen._guard_var({"guards": [{"kind": "permission", "permission": "x"}]}) is None


# ---------------------------------------------------------------------------
# Optional: mmdc --parse round-trip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
	shutil.which("mmdc") is None,
	reason="mermaid-cli (mmdc) not installed; skipping parse round-trip",
)
def test_mmdc_parses_every_emitted_diagram(tmp_path: Path) -> None:
	"""When mermaid-cli is on PATH, every emitted ``.mmd`` parses cleanly.

	This is the only spot the suite shells out to a node binary; the
	skip-if-missing guard keeps the lightweight CI lane green even when
	node is absent. The end-to-end check is meaningful because the regex
	grammar check above can miss subtle mermaid-syntax regressions
	(e.g. unsupported directives in ``stateDiagram-v2``).
	"""

	# Render once to a temp dir so we don't pollute the example trees.
	for path in (_INSURANCE_BUNDLE, _BUILDING_BUNDLE, _HIRING_BUNDLE):
		raw = json.loads(path.read_text(encoding="utf-8"))
		files = generate(raw)
		for f in files:
			if not f.path.endswith("/diagram.mmd"):
				continue
			src = tmp_path / Path(f.path).name
			src.write_text(f.content, encoding="utf-8")
			out = tmp_path / "rendered.svg"
			# mmdc returns non-zero on parse failure; capture stderr for
			# diagnostics if a future regression breaks parsing.
			result = subprocess.run(
				["mmdc", "-i", str(src), "-o", str(out)],
				check=False,
				capture_output=True,
				text=True,
			)
			assert result.returncode == 0, (
				f"mmdc failed for {f.path}: {result.stderr}"
			)
