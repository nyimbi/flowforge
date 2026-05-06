"""Glossary-conflict linter rule — E-8.

Per ``framework/docs/flowforge-evolution.md`` §9.3 and
``framework/docs/jtbd-editor-arch.md`` §7.3.

A glossary conflict is emitted as a ``warning`` when the same term appears
in two or more domains within a bundle and those domains define the term
differently (or one domain leaves the definition missing while another fills
it in).

Integration
-----------
Register the pack with the :class:`Linter`:

.. code-block:: python

    from flowforge_jtbd.glossary import BUILTIN_CATALOG
    from flowforge_jtbd.lint import Linter, RuleRegistry
    from flowforge_jtbd.lint.glossary import GlossaryConflictRulePack

    registry = RuleRegistry([GlossaryConflictRulePack(BUILTIN_CATALOG)])
    report = Linter(registry=registry).lint(bundle)

Custom catalogs
---------------
Build your own catalog from a bundle and merge with the built-in seed:

.. code-block:: python

    from flowforge_jtbd.glossary import BUILTIN_CATALOG, GlossaryCatalog

    bundle_catalog = GlossaryCatalog.from_bundle(bundle)
    combined = BUILTIN_CATALOG.merge(bundle_catalog)
    pack = GlossaryConflictRulePack(combined)
"""

from __future__ import annotations

from flowforge_jtbd.glossary import GlossaryCatalog, TermConflict
from flowforge_jtbd.spec import JtbdBundle, JtbdLintSpec

from .registry import JtbdRule
from .results import Issue


# ---------------------------------------------------------------------------
# Rule: glossary_term_conflict
# ---------------------------------------------------------------------------

class GlossaryConflictRule:
	"""Warn when a term in the bundle is a known cross-domain collision.

	On bundle-level invocation (``spec=None``) this rule:

	1. Builds a bundle-scoped catalog from all JTBD actor roles and
	   data-capture field IDs.
	2. Merges with the external catalog supplied at construction.
	3. Calls :meth:`GlossaryCatalog.conflicts` and emits one ``warning``
	   ``Issue`` per detected conflict.

	On per-spec invocation (``spec`` is a :class:`JtbdLintSpec`) the rule
	checks whether the spec references any term that is known to be
	domain-ambiguous in the merged catalog, and warns per reference.
	"""

	rule_id: str = "glossary_term_conflict"

	def __init__(self, catalog: GlossaryCatalog) -> None:
		assert catalog is not None, "catalog is required"
		self._catalog = catalog

	def check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec | None,
	) -> list[Issue]:
		# Bundle-level: detect cross-domain conflicts.
		if spec is None:
			return self._bundle_level_check(bundle)
		return self._spec_level_check(bundle, spec)

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _bundle_level_check(self, bundle: JtbdBundle) -> list[Issue]:
		"""Emit one issue per cross-domain term conflict in the merged catalog."""
		bundle_catalog = GlossaryCatalog.from_bundle(bundle)
		merged = self._catalog.merge(bundle_catalog)
		issues: list[Issue] = []
		for conflict in merged.conflicts():
			issues.append(_conflict_to_issue(conflict))
		return issues

	def _spec_level_check(
		self,
		bundle: JtbdBundle,
		spec: JtbdLintSpec,
	) -> list[Issue]:
		"""Warn when a spec's actor role or field ID is a known ambiguous term."""
		issues: list[Issue] = []

		# Collect all terms referenced by this spec.
		spec_terms: list[str] = []
		if spec.actor and spec.actor.role:
			spec_terms.append(spec.actor.role)

		# data_capture IDs from extra payload.
		from flowforge_jtbd.glossary import _extract_data_capture_ids  # local import avoids cycle
		spec_terms.extend(_extract_data_capture_ids(spec))

		# Check each term against the merged catalog.
		bundle_catalog = GlossaryCatalog.from_bundle(bundle)
		merged = self._catalog.merge(bundle_catalog)
		conflict_terms = {c.term for c in merged.conflicts()}

		for term in spec_terms:
			normalised = term.strip().lower()
			if normalised in conflict_terms:
				entries = merged.terms_for(normalised)
				domains = sorted(
					{e.domain for e in entries if e.domain is not None}
				)
				issues.append(Issue(
					severity="warning",
					rule="glossary_term_ambiguous",
					message=(
						f"Term '{normalised}' used by '{spec.jtbd_id}' has conflicting"
						f" definitions across domains: {', '.join(domains)}."
					),
					fixhint=(
						f"Add a local glossary entry for '{normalised}' in this bundle"
						" to disambiguate which domain definition applies."
					),
					doc_url="/docs/jtbd-editor#glossary",
					context=spec.jtbd_id,
					related_jtbds=[spec.jtbd_id],
				))

		return issues


def _conflict_to_issue(conflict: TermConflict) -> Issue:
	"""Convert a :class:`TermConflict` into a lint :class:`Issue`."""
	domain_list = ", ".join(conflict.domains)
	def_snippets: list[str] = []
	for domain in conflict.domains:
		defn = conflict.definitions.get(domain)
		snippet = f"  {domain}: {defn!r}" if defn else f"  {domain}: (no definition)"
		def_snippets.append(snippet)
	defs_text = "\n".join(def_snippets)

	return Issue(
		severity="warning",
		rule="glossary_term_conflict",
		message=(
			f"Term '{conflict.term}' has conflicting definitions across"
			f" domains [{domain_list}]:\n{defs_text}"
		),
		fixhint=(
			f"Add a shared glossary entry for '{conflict.term}' to resolve"
			" which definition applies in this bundle, or rename the term in"
			" the relevant JTBD to be domain-specific."
		),
		doc_url="/docs/jtbd-editor#glossary",
		related_jtbds=conflict.source_jtbd_ids,
	)


# ---------------------------------------------------------------------------
# Rule pack
# ---------------------------------------------------------------------------

class GlossaryConflictRulePack:
	"""A :class:`JtbdRulePack` that ships the glossary-conflict rule.

	Constructed with a :class:`GlossaryCatalog`; pass
	:data:`flowforge_jtbd.glossary.BUILTIN_CATALOG` for the out-of-the-box
	cross-domain term set, or supply your own catalog.

	.. code-block:: python

		from flowforge_jtbd.glossary import BUILTIN_CATALOG
		from flowforge_jtbd.lint.glossary import GlossaryConflictRulePack

		pack = GlossaryConflictRulePack(BUILTIN_CATALOG)
	"""

	pack_id: str = "glossary"

	def __init__(self, catalog: GlossaryCatalog) -> None:
		assert catalog is not None, "catalog is required"
		self._rule = GlossaryConflictRule(catalog)

	def rules(self) -> list[JtbdRule]:
		return [self._rule]  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def builtin_glossary_pack() -> GlossaryConflictRulePack:
	"""Return a :class:`GlossaryConflictRulePack` seeded with the built-in
	cross-domain term catalog.

	Equivalent to:

	.. code-block:: python

		from flowforge_jtbd.glossary import BUILTIN_CATALOG
		GlossaryConflictRulePack(BUILTIN_CATALOG)
	"""
	from flowforge_jtbd.glossary import BUILTIN_CATALOG  # avoid module-level cycle
	return GlossaryConflictRulePack(BUILTIN_CATALOG)


__all__ = [
	"GlossaryConflictRule",
	"GlossaryConflictRulePack",
	"builtin_glossary_pack",
]
