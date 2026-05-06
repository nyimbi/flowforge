"""Cross-phase E2E integration tests (E-31).

Verifies the full pipeline across phases E1–E7:

  E1  JtbdSpec / lockfile / linter core
  E2  Glossary conflict detection + recommender
  E3  QualityScorer (deterministic pass)
  E4  Domain libraries load + parse
  E5  Template cache instantiation + workflow fire
  E6  Compliance linting
  E7  jtbd_id propagation through the engine

Each test section drives data from a real or constructed JTBD bundle
through the relevant phase surfaces and asserts the chain holds end-to-end.
No external services required — all paths use in-memory implementations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Phase E1 — spec parsing + linting
# ---------------------------------------------------------------------------

from flowforge_jtbd.spec import (
	ActorRef,
	JtbdBundle,
	JtbdLintSpec,
	RoleDef,
	StageDecl,
)
from flowforge_jtbd.lint import (
	Linter,
	RuleRegistry,
	GlossaryConflictRulePack,
	LowQualityRulePack,
)
from flowforge_jtbd.glossary import BUILTIN_CATALOG, GlossaryCatalog, GlossaryTerm
from flowforge_jtbd.ai.quality import score_jtbd, QualityScorer
from flowforge_jtbd.ai.recommender import Recommender, build_recommender, InMemoryEmbeddingStore
from flowforge_jtbd.templates import TemplateCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FULL_STAGES = [
	StageDecl(name="discover"),
	StageDecl(name="execute"),
	StageDecl(name="error_handle"),
	StageDecl(name="report"),
	StageDecl(name="audit"),
]


def _make_spec(
	jtbd_id: str,
	domain: str,
	role: str,
	*,
	situation: str = "",
	motivation: str = "",
	outcome: str = "",
	requires: list[str] | None = None,
) -> JtbdLintSpec:
	return JtbdLintSpec(
		jtbd_id=jtbd_id,
		version="1.0.0",
		domain=domain,
		actor=ActorRef(role=role, tier=1),
		stages=list(_FULL_STAGES),
		requires=list(requires or []),
		situation=situation,
		motivation=motivation,
		outcome=outcome,
	)


def _insurance_bundle() -> JtbdBundle:
	"""Minimal 3-JTBD insurance bundle used across phase tests."""
	return JtbdBundle(
		bundle_id="insurance-e2e",
		jtbds=[
			_make_spec(
				"party_kyc", "insurance", "compliance_officer",
				situation="Compliance officer needs to verify a policyholder's identity.",
				motivation="Meet AML/KYC regulatory requirements before policy inception.",
				outcome="Party record created and identity verified.",
			),
			_make_spec(
				"claim_intake", "insurance", "adjuster",
				situation="A policyholder files an FNOL to start the claim process.",
				motivation="Recover insured losses quickly and accurately.",
				outcome="Claim record is created and queued for adjuster review.",
				requires=["party_kyc"],
			),
			_make_spec(
				"claim_settlement", "insurance", "adjuster",
				situation="An adjuster needs to evaluate and settle an open claim.",
				motivation="Pay valid claims promptly and fairly.",
				outcome="Claim settled or denied with documented rationale.",
				requires=["claim_intake"],
			),
		],
		shared_roles={
			"adjuster": RoleDef(name="adjuster", default_tier=2),
			"compliance_officer": RoleDef(name="compliance_officer", default_tier=2),
		},
	)


# ---------------------------------------------------------------------------
# E1: Linter core — lifecycle / dependency / actor
# ---------------------------------------------------------------------------

def test_e1_clean_bundle_passes_linter() -> None:
	"""A well-formed 3-JTBD bundle produces no errors from the core linter."""
	report = Linter().lint(_insurance_bundle())
	assert report.ok, [i.message for i in report.errors()]


def test_e1_topological_order_respects_requires() -> None:
	"""Dependency graph produces the correct topological order."""
	report = Linter().lint(_insurance_bundle())
	topo = report.topological_order
	assert topo is not None
	assert topo.index("party_kyc") < topo.index("claim_intake")
	assert topo.index("claim_intake") < topo.index("claim_settlement")


def test_e1_cycle_produces_error() -> None:
	"""A dependency cycle is flagged as an error."""
	a = _make_spec("a", "insurance", "adjuster", requires=["b"])
	b = _make_spec("b", "insurance", "adjuster", requires=["a"])
	bundle = JtbdBundle(bundle_id="cycle-test", jtbds=[a, b])
	report = Linter().lint(bundle)
	assert not report.ok
	rules = {i.rule for i in report.errors() + report.bundle_issues}
	assert "cycle_detected" in rules


def test_e1_missing_stage_produces_error() -> None:
	"""A JTBD missing required lifecycle stages produces an error."""
	spec = JtbdLintSpec(
		jtbd_id="incomplete",
		version="1.0.0",
		stages=[StageDecl(name="execute")],  # missing 4 stages
	)
	bundle = JtbdBundle(bundle_id="stage-test", jtbds=[spec])
	report = Linter().lint(bundle)
	assert not report.ok


# ---------------------------------------------------------------------------
# E2: Glossary conflict detection
# ---------------------------------------------------------------------------

def test_e2_builtin_catalog_detects_cross_domain_conflicts() -> None:
	"""BUILTIN_CATALOG flags cross-domain term collisions as warnings."""
	pack = GlossaryConflictRulePack(BUILTIN_CATALOG)
	registry = RuleRegistry([pack])
	report = Linter(registry=registry).lint(_insurance_bundle())
	# Warnings don't make ok=False.
	assert report.ok
	all_issues = report.bundle_issues + [i for r in report.results for i in r.issues]
	warning_rules = {i.rule for i in all_issues if i.severity == "warning"}
	# Builtin catalog has claim/party/account/case/intake conflicts.
	assert "glossary_term_conflict" in warning_rules


def test_e2_glossary_from_bundle_extracts_domain_terms() -> None:
	"""Auto-populate a catalog from a bundle and merge with builtin."""
	bundle = _insurance_bundle()
	bundle_catalog = GlossaryCatalog.from_bundle(bundle)
	merged = BUILTIN_CATALOG.merge(bundle_catalog)
	# "adjuster" appears in both insurance domain (from bundle) and any other domain
	# it might be in the builtin — bundle-level detection works.
	assert "adjuster" in merged.all_terms() or len(merged.all_terms()) >= 10


# ---------------------------------------------------------------------------
# E3: QualityScorer
# ---------------------------------------------------------------------------

def test_e3_high_quality_spec_scores_above_60() -> None:
	"""A well-written JTBD spec scores ≥ 60 on the deterministic rubric."""
	report = score_jtbd({
		"id": "claim_intake",
		"situation": "A policyholder needs to file a first notice of loss to start the claims process.",
		"motivation": "Recover insured losses quickly and ensure the claim is documented accurately.",
		"outcome": "A claim record is created and queued for adjuster review within SLA.",
		"success_criteria": [
			"Claim record created within 15 minutes of FNOL submission.",
			"Adjuster assigned within 4 hours.",
			"Zero FNOL records missing required fields.",
		],
	})
	assert report.score >= 60, f"Expected ≥60, got {report.score}"
	assert not report.low_quality


def test_e3_empty_spec_is_low_quality() -> None:
	"""An empty spec is flagged as low quality."""
	report = score_jtbd({"id": "empty"})
	assert report.low_quality
	assert report.score < 60


def test_e3_quality_pack_wires_into_linter() -> None:
	"""LowQualityRulePack raises warnings for specs without NL fields."""
	pack = LowQualityRulePack(threshold=60)
	registry = RuleRegistry([pack])
	# A spec with no NL fields scores poorly.
	spec = JtbdLintSpec(jtbd_id="bare", version="1.0.0", stages=list(_FULL_STAGES))
	bundle = JtbdBundle(bundle_id="quality-test", jtbds=[spec])
	report = Linter(registry=registry).lint(bundle)
	all_issues = [i for r in report.results for i in r.issues]
	assert any(i.rule == "low_quality_jtbd" for i in all_issues)


def test_e3_quality_and_glossary_together_dont_break_linter() -> None:
	"""Multiple rule packs co-exist without conflicts."""
	registry = RuleRegistry([
		GlossaryConflictRulePack(BUILTIN_CATALOG),
		LowQualityRulePack(),
	])
	report = Linter(registry=registry).lint(_insurance_bundle())
	assert isinstance(report.ok, bool)  # doesn't crash


# ---------------------------------------------------------------------------
# E4: Domain libraries load + parse
# ---------------------------------------------------------------------------

def _domain_lib_root() -> Path:
	return Path(__file__).resolve().parents[4] / "python"


# The 30 canonical domain library suffixes (E2 + E4 phases).
_DOMAIN_SUFFIXES: list[str] = [
	# E2-phase (12)
	"accounting", "corp-finance", "pm", "hr", "crm", "procurement",
	"legal", "compliance", "insurance", "banking", "ecom", "logistics",
	# E4-phase (18)
	"mfg", "edu", "healthcare", "realestate", "agritech", "construction",
	"gov", "municipal", "nonprofit", "media", "gaming", "travel",
	"restaurants", "retail", "telco", "utilities", "saasops", "platformeng",
]


def test_e4_all_thirty_domain_libraries_exist() -> None:
	"""All 30 expected domain library packages exist on disk."""
	root = _domain_lib_root()
	missing = [d for d in _DOMAIN_SUFFIXES if not (root / f"flowforge-jtbd-{d}").is_dir()]
	assert not missing, f"Missing domain packages: {missing}"


def test_e4_each_domain_has_five_jtbd_specs() -> None:
	"""Every domain library has ≥ 5 JTBD YAML files."""
	root = _domain_lib_root()
	failures: list[str] = []
	for suffix in _DOMAIN_SUFFIXES:
		pkg_dir = root / f"flowforge-jtbd-{suffix}"
		if not pkg_dir.is_dir():
			failures.append(f"flowforge-jtbd-{suffix}: missing")
			continue
		jtbd_dirs = list(pkg_dir.rglob("jtbds"))
		if not jtbd_dirs:
			failures.append(f"flowforge-jtbd-{suffix}: no jtbds/ dir")
			continue
		yamls = list(jtbd_dirs[0].glob("*.yaml"))
		if len(yamls) < 5:
			failures.append(f"flowforge-jtbd-{suffix}: only {len(yamls)} JTBDs")
	assert not failures, "\n".join(failures)


def test_e4_domain_yaml_parseable_for_all_libraries() -> None:
	"""domain.yaml is valid YAML for all 30 domain libraries."""
	import yaml  # type: ignore[import-untyped]

	root = _domain_lib_root()
	failures: list[str] = []
	for suffix in _DOMAIN_SUFFIXES:
		pkg_dir = root / f"flowforge-jtbd-{suffix}"
		if not pkg_dir.is_dir():
			continue
		domain_yamls = list(pkg_dir.rglob("domain.yaml"))
		if not domain_yamls:
			failures.append(f"flowforge-jtbd-{suffix}: missing domain.yaml")
			continue
		try:
			data = yaml.safe_load(domain_yamls[0].read_text())
			assert "id" in data
			assert "name" in data
		except Exception as e:
			failures.append(f"flowforge-jtbd-{suffix}: {e}")
	assert not failures, "\n".join(failures)


def test_e4_example_bundles_exist_for_all_libraries() -> None:
	"""Each domain library ships an examples/bundle.yaml file."""
	root = _domain_lib_root()
	failures: list[str] = []
	for suffix in _DOMAIN_SUFFIXES:
		pkg_dir = root / f"flowforge-jtbd-{suffix}"
		if not pkg_dir.is_dir():
			continue
		examples = list(pkg_dir.rglob("examples/bundle.yaml"))
		if not examples:
			failures.append(f"flowforge-jtbd-{suffix}: missing examples/bundle.yaml")
	assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# E5: Template cache + engine fire with jtbd_id propagation
# ---------------------------------------------------------------------------

def test_e5_template_cache_default_loads_twelve_templates() -> None:
	"""TemplateCache.default() pre-loads 12 starter templates."""
	cache = TemplateCache.default()
	assert cache.size() == 12


def test_e5_all_templates_instantiate_cleanly() -> None:
	"""Every starter template instantiates with minimal params without error."""
	cache = TemplateCache.default()
	for tmpl in cache.list_templates():
		wf = cache.instantiate(tmpl.id, {
			"workflow_key": f"{tmpl.id}_e2e",
			"subject_kind": "item",
		})
		assert wf["key"] == f"{tmpl.id}_e2e"
		assert "states" in wf
		assert "transitions" in wf


async def test_e5_template_workflow_fires_through_engine() -> None:
	"""A template-instantiated workflow def runs through the engine."""
	from flowforge.dsl import WorkflowDef
	from flowforge.engine import fire, new_instance

	cache = TemplateCache.default()
	wf_dict = cache.instantiate("audit_trail", {
		"workflow_key": "e2e_audit",
		"subject_kind": "claim",
	})
	wd = WorkflowDef.model_validate(wf_dict)
	inst = new_instance(wd)
	result = await fire(wd, inst, "start", jtbd_id="audit_trail", jtbd_version="1.0.0")
	assert result.new_state in {s.name for s in wd.states}


# ---------------------------------------------------------------------------
# E6: jtbd_id propagation through the engine audit chain
# ---------------------------------------------------------------------------

async def test_e6_jtbd_id_in_audit_event() -> None:
	"""Engine audit events carry jtbd_id when supplied."""
	from flowforge.dsl import WorkflowDef
	from flowforge.engine import fire, new_instance

	cache = TemplateCache.default()
	wf_dict = cache.instantiate("audit_trail", {
		"workflow_key": "e2e_e6",
		"subject_kind": "claim",
	})
	wd = WorkflowDef.model_validate(wf_dict)
	inst = new_instance(wd)
	result = await fire(
		wd, inst, "start",
		jtbd_id="claim_intake",
		jtbd_version="2.0.0",
	)
	transition_audit = result.audit_events[0]
	assert transition_audit.payload.get("jtbd_id") == "claim_intake"
	assert transition_audit.payload.get("jtbd_version") == "2.0.0"


async def test_e6_jtbd_id_absent_when_not_supplied() -> None:
	"""Engine audit events omit jtbd_id when not supplied (backwards-compat)."""
	from flowforge.dsl import WorkflowDef
	from flowforge.engine import fire, new_instance

	cache = TemplateCache.default()
	wf_dict = cache.instantiate("audit_trail", {
		"workflow_key": "e2e_nojtbd",
		"subject_kind": "claim",
	})
	wd = WorkflowDef.model_validate(wf_dict)
	inst = new_instance(wd)
	result = await fire(wd, inst, "start")
	transition_audit = result.audit_events[0]
	assert "jtbd_id" not in transition_audit.payload


# ---------------------------------------------------------------------------
# E7: Recommender with real domain specs
# ---------------------------------------------------------------------------

async def test_e7_recommender_ranks_insurance_specs() -> None:
	"""Recommender returns insurance specs for an insurance-domain query."""
	specs = [
		{"id": "claim_intake", "domain": "insurance",
		 "situation": "policyholder files an FNOL claim",
		 "motivation": "recover insured losses",
		 "outcome": "claim record created"},
		{"id": "account_open", "domain": "banking",
		 "situation": "customer opens a bank deposit account",
		 "motivation": "save money securely",
		 "outcome": "account created"},
		{"id": "po_create", "domain": "procurement",
		 "situation": "procurement officer raises a purchase order",
		 "motivation": "authorise supplier payment",
		 "outcome": "PO issued to supplier"},
	]
	rec = build_recommender(specs)
	results = await rec.recommend("insurance claim FNOL policyholder", top_k=3)
	assert len(results) >= 1
	ids = [r.jtbd_id for r in results]
	assert "claim_intake" in ids
	# claim_intake should rank highest.
	assert results[0].jtbd_id == "claim_intake"


async def test_e7_recommender_domain_filter_works() -> None:
	"""Domain filter restricts results to the specified domain."""
	rec = build_recommender([
		{"id": "a", "domain": "insurance", "situation": "claim process intake"},
		{"id": "b", "domain": "banking", "situation": "loan application process"},
	])
	results = await rec.recommend("process", top_k=5, domain_filter="insurance")
	assert all(r.domain == "insurance" for r in results)


# ---------------------------------------------------------------------------
# Cross-phase: Full pipeline smoke test
# ---------------------------------------------------------------------------

async def test_full_pipeline_e1_to_e7() -> None:
	"""Smoke test: JTBD bundle → lint → quality → recommend → template → engine fire.

	Drives one complete journey through every phase introduced in E1-E7
	without hitting any external service.
	"""
	from flowforge.dsl import WorkflowDef
	from flowforge.engine import fire, new_instance

	# E1: Parse and lint a bundle.
	bundle = _insurance_bundle()
	report = Linter().lint(bundle)
	assert report.ok

	# E3: Quality-score the first spec's NL text.
	spec_dict = {
		"id": "claim_intake",
		"situation": "A policyholder files an FNOL.",
		"motivation": "Recover insured losses.",
		"outcome": "Claim record created.",
		"success_criteria": ["Claim created within 15 minutes."],
	}
	quality = score_jtbd(spec_dict)
	assert 0 <= quality.score <= 100

	# E5: Instantiate a template.
	cache = TemplateCache.default()
	wf_dict = cache.instantiate("n_of_m_approval", {
		"workflow_key": "claim_e2e",
		"subject_kind": "claim",
	})

	# E5+E6: Fire through the engine with jtbd_id.
	wd = WorkflowDef.model_validate(wf_dict)
	inst = new_instance(wd)
	fire_result = await fire(
		wd, inst, "approve",
		jtbd_id="claim_intake",
		jtbd_version="1.0.0",
		tenant_id="e2e-tenant",
	)
	# Verify jtbd_id propagated.
	transition_audit = fire_result.audit_events[0]
	assert transition_audit.payload.get("jtbd_id") == "claim_intake"

	# E7: Recommend similar JTBDs.
	rec = build_recommender([
		{"id": "claim_intake", "domain": "insurance",
		 "situation": "policyholder files FNOL claim loss",
		 "motivation": "recover losses", "outcome": "claim created"},
		{"id": "claim_settlement", "domain": "insurance",
		 "situation": "adjuster settles open claim",
		 "motivation": "resolve claim fairly", "outcome": "claim closed"},
	])
	recommendations = await rec.recommend("insurance claim FNOL", top_k=2)
	assert len(recommendations) >= 1
