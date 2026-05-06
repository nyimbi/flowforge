"""Tests for E-8 — Glossary/ontology + conflict linter.

Covers:
- GlossaryTerm model
- GlossaryCatalog: add_term, terms_for, conflicts, from_bundle, merge
- BUILTIN_CATALOG: known cross-domain conflicts present
- GlossaryConflictRule: bundle-level and per-spec warnings
- GlossaryConflictRulePack wired into Linter
- builtin_glossary_pack convenience factory
"""

from __future__ import annotations

from flowforge_jtbd.glossary import (
	BUILTIN_CATALOG,
	GlossaryCatalog,
	GlossaryTerm,
)
from flowforge_jtbd.lint import (
	Linter,
	RuleRegistry,
	GlossaryConflictRule,
	GlossaryConflictRulePack,
	builtin_glossary_pack,
)
from flowforge_jtbd.spec import ActorRef, JtbdLintSpec, StageDecl

from .conftest import make_bundle, make_full_spec


# ---------------------------------------------------------------------------
# GlossaryCatalog — core behavior
# ---------------------------------------------------------------------------

def test_add_term_stores_by_normalised_key() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="  Claim  ", domain="insurance", definition="FNOL"))
	entries = catalog.terms_for("claim")
	assert len(entries) == 1
	assert entries[0].term == "claim"


def test_add_term_updates_existing_domain_entry() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="claim", domain="insurance", definition="old"))
	catalog.add_term(GlossaryTerm(term="claim", domain="insurance", definition="new"))
	entries = catalog.terms_for("claim")
	assert len(entries) == 1
	assert entries[0].definition == "new"


def test_add_term_allows_different_domains() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="claim", domain="insurance", definition="FNOL"))
	catalog.add_term(GlossaryTerm(term="claim", domain="legal", definition="Assertion"))
	entries = catalog.terms_for("claim")
	assert len(entries) == 2
	domains = {e.domain for e in entries}
	assert domains == {"insurance", "legal"}


def test_conflicts_returns_empty_for_consistent_definitions() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="case", domain="legal", definition="A litigation matter."))
	catalog.add_term(GlossaryTerm(term="case", domain="gov", definition="A litigation matter."))
	# Same definition — no conflict.
	assert catalog.conflicts() == []


def test_conflicts_returns_conflict_for_different_definitions() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="claim", domain="insurance", definition="FNOL"))
	catalog.add_term(GlossaryTerm(term="claim", domain="legal", definition="Legal assertion"))
	conflicts = catalog.conflicts()
	assert len(conflicts) == 1
	assert conflicts[0].term == "claim"
	assert set(conflicts[0].domains) == {"insurance", "legal"}


def test_conflicts_flags_when_one_definition_missing() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="intake", domain="insurance", definition="FNOL intake"))
	catalog.add_term(GlossaryTerm(term="intake", domain="hr", definition=None))
	conflicts = catalog.conflicts()
	# One has a definition, the other doesn't → conflict.
	assert any(c.term == "intake" for c in conflicts)


def test_conflicts_no_issue_for_single_domain_term() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="underwrite", domain="insurance", definition="Risk eval"))
	assert catalog.conflicts() == []


def test_all_terms_sorted() -> None:
	catalog = GlossaryCatalog()
	catalog.add_term(GlossaryTerm(term="zebra", domain="a"))
	catalog.add_term(GlossaryTerm(term="apple", domain="a"))
	assert catalog.all_terms() == ["apple", "zebra"]


def test_merge_combines_catalogs() -> None:
	a = GlossaryCatalog([GlossaryTerm(term="claim", domain="insurance", definition="FNOL")])
	b = GlossaryCatalog([GlossaryTerm(term="claim", domain="legal", definition="Assertion")])
	merged = a.merge(b)
	entries = merged.terms_for("claim")
	assert len(entries) == 2


def test_merge_does_not_mutate_originals() -> None:
	a = GlossaryCatalog([GlossaryTerm(term="foo", domain="x", definition="X")])
	b = GlossaryCatalog([GlossaryTerm(term="bar", domain="y", definition="Y")])
	_ = a.merge(b)
	assert a.all_terms() == ["foo"]
	assert b.all_terms() == ["bar"]


# ---------------------------------------------------------------------------
# GlossaryCatalog.from_bundle
# ---------------------------------------------------------------------------

def _make_spec_with_domain(
	jtbd_id: str,
	domain: str,
	role: str = "analyst",
) -> JtbdLintSpec:
	return JtbdLintSpec(
		jtbd_id=jtbd_id,
		version="1.0.0",
		domain=domain,
		actor=ActorRef(role=role),
		stages=[
			StageDecl(name="discover"),
			StageDecl(name="execute"),
			StageDecl(name="error_handle"),
			StageDecl(name="report"),
			StageDecl(name="audit"),
		],
	)


def test_from_bundle_extracts_actor_roles() -> None:
	spec = _make_spec_with_domain("claim_intake", "insurance", role="adjuster")
	bundle = make_bundle([spec])
	catalog = GlossaryCatalog.from_bundle(bundle)
	entries = catalog.terms_for("adjuster")
	assert len(entries) == 1
	assert entries[0].domain == "insurance"


def test_from_bundle_extracts_jtbd_id_as_term() -> None:
	spec = _make_spec_with_domain("claim_intake", "insurance")
	bundle = make_bundle([spec])
	catalog = GlossaryCatalog.from_bundle(bundle)
	entries = catalog.terms_for("claim_intake")
	assert entries


def test_from_bundle_cross_domain_role_detected() -> None:
	ins = _make_spec_with_domain("claim_intake", "insurance", role="adjuster")
	hr = _make_spec_with_domain("employee_onboard", "hr", role="adjuster")
	bundle = make_bundle([ins, hr])
	catalog = GlossaryCatalog.from_bundle(bundle)
	# "adjuster" appears in two domains.
	entries = catalog.terms_for("adjuster")
	domains = {e.domain for e in entries}
	assert domains == {"insurance", "hr"}


# ---------------------------------------------------------------------------
# BUILTIN_CATALOG
# ---------------------------------------------------------------------------

def test_builtin_catalog_has_claim_conflict() -> None:
	conflicts = BUILTIN_CATALOG.conflicts()
	terms = {c.term for c in conflicts}
	assert "claim" in terms


def test_builtin_catalog_has_account_conflict() -> None:
	conflicts = BUILTIN_CATALOG.conflicts()
	terms = {c.term for c in conflicts}
	assert "account" in terms


def test_builtin_catalog_has_party_conflict() -> None:
	conflicts = BUILTIN_CATALOG.conflicts()
	terms = {c.term for c in conflicts}
	assert "party" in terms


# ---------------------------------------------------------------------------
# GlossaryConflictRule — bundle-level
# ---------------------------------------------------------------------------

def test_rule_no_issues_for_empty_catalog_and_bundle() -> None:
	catalog = GlossaryCatalog()
	rule = GlossaryConflictRule(catalog)
	bundle = make_bundle([make_full_spec("demo", actor=ActorRef(role="analyst"))])
	issues = rule.check(bundle, None)
	assert issues == []


def test_rule_emits_warning_for_known_conflict() -> None:
	# Seed catalog with a known conflict.
	catalog = GlossaryCatalog([
		GlossaryTerm(term="claim", domain="insurance", definition="FNOL"),
		GlossaryTerm(term="claim", domain="legal", definition="Legal assertion"),
	])
	rule = GlossaryConflictRule(catalog)
	# Bundle does not need to reference "claim" — it's a catalog-level conflict.
	bundle = make_bundle([make_full_spec("demo")])
	issues = rule.check(bundle, None)
	assert any(i.rule == "glossary_term_conflict" for i in issues)
	assert all(i.severity == "warning" for i in issues)


def test_rule_conflict_issue_mentions_term() -> None:
	catalog = GlossaryCatalog([
		GlossaryTerm(term="claim", domain="insurance", definition="FNOL"),
		GlossaryTerm(term="claim", domain="legal", definition="Legal assertion"),
	])
	rule = GlossaryConflictRule(catalog)
	bundle = make_bundle([make_full_spec("demo")])
	issues = rule.check(bundle, None)
	conflict_issues = [i for i in issues if i.rule == "glossary_term_conflict"]
	assert any("claim" in i.message for i in conflict_issues)


# ---------------------------------------------------------------------------
# GlossaryConflictRule — spec-level
# ---------------------------------------------------------------------------

def test_rule_spec_level_warns_on_ambiguous_actor_role() -> None:
	catalog = GlossaryCatalog([
		GlossaryTerm(term="adjuster", domain="insurance", definition="Claims handler"),
		GlossaryTerm(term="adjuster", domain="legal", definition="Court adjuster"),
	])
	rule = GlossaryConflictRule(catalog)
	spec = _make_spec_with_domain("claim_intake", "insurance", role="adjuster")
	bundle = make_bundle([spec])
	issues = rule.check(bundle, spec)
	assert any(i.rule == "glossary_term_ambiguous" for i in issues)


def test_rule_spec_level_no_warning_for_unambiguous_role() -> None:
	catalog = GlossaryCatalog([
		GlossaryTerm(term="adjuster", domain="insurance", definition="Claims handler"),
	])
	rule = GlossaryConflictRule(catalog)
	spec = _make_spec_with_domain("claim_intake", "insurance", role="adjuster")
	bundle = make_bundle([spec])
	issues = rule.check(bundle, spec)
	assert not any(i.rule == "glossary_term_ambiguous" for i in issues)


# ---------------------------------------------------------------------------
# GlossaryConflictRulePack + Linter integration
# ---------------------------------------------------------------------------

def test_pack_rules_returns_one_rule() -> None:
	pack = GlossaryConflictRulePack(GlossaryCatalog())
	assert len(pack.rules()) == 1
	assert pack.rules()[0].rule_id == "glossary_term_conflict"


def test_pack_id_is_glossary() -> None:
	pack = GlossaryConflictRulePack(GlossaryCatalog())
	assert pack.pack_id == "glossary"


def test_linter_with_glossary_pack_emits_warnings() -> None:
	catalog = GlossaryCatalog([
		GlossaryTerm(term="claim", domain="insurance", definition="FNOL"),
		GlossaryTerm(term="claim", domain="legal", definition="Assertion"),
	])
	pack = GlossaryConflictRulePack(catalog)
	registry = RuleRegistry([pack])
	bundle = make_bundle([make_full_spec("demo")])
	report = Linter(registry=registry).lint(bundle)
	# Warnings don't make report.ok False.
	assert report.ok
	all_issues = report.bundle_issues + [i for r in report.results for i in r.issues]
	assert any(i.rule == "glossary_term_conflict" for i in all_issues)


def test_builtin_glossary_pack_factory_returns_pack() -> None:
	pack = builtin_glossary_pack()
	assert pack.pack_id == "glossary"
	assert len(pack.rules()) == 1


def test_linter_with_builtin_pack_no_errors_on_clean_bundle() -> None:
	pack = builtin_glossary_pack()
	registry = RuleRegistry([pack])
	spec = make_full_spec("demo", actor=ActorRef(role="analyst"))
	bundle = make_bundle([spec])
	report = Linter(registry=registry).lint(bundle)
	# Warnings present (from builtin catalog) but no errors.
	assert report.ok
	errors = report.errors()
	assert not errors
