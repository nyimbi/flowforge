"""Glossary / ontology model for JTBD term catalogs.

Per ``framework/docs/flowforge-evolution.md`` §9.2 and
``framework/docs/jtbd-editor-arch.md`` §7.3 (E-8).

Tracks shared terminology across domain libraries so the linter can flag
cross-domain term collisions (e.g., "claim" means one thing in insurance
and another in legal).

Usage
-----
1. Start with :data:`BUILTIN_CATALOG` (seeds common cross-domain terms).
2. Or build one from a bundle: ``GlossaryCatalog.from_bundle(bundle)``.
3. Call ``catalog.conflicts()`` to enumerate detected term collisions.
4. Pass the catalog to :class:`lint.glossary.GlossaryConflictRulePack`.

Auto-population
---------------
``GlossaryCatalog.from_bundle`` scans each JTBD's actor role, ``jtbd_id``,
and any ``data_capture[].id`` strings present in the extra payload. All
extracted strings become undecorated entries (definition=``None``) so the
administrator can fill in definitions incrementally.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .spec import JtbdBundle, JtbdLintSpec


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class GlossaryTerm(BaseModel):
	"""A single term definition scoped to one domain.

	Multiple ``GlossaryTerm`` objects may share the same ``term`` string but
	differ in ``domain`` — that is a cross-domain entry, and a conflict is
	raised if the ``definition`` fields do not match (or one is absent).
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	term: str
	"""The normalised term string (lower-cased, stripped)."""

	domain: str | None = None
	"""The domain that owns this definition (e.g., ``"insurance"``).
	``None`` means the term is cross-domain / global."""

	definition: str | None = None
	"""Human-readable definition.  ``None`` means not yet filled in."""

	aliases: list[str] = Field(default_factory=list)
	"""Alternative names recognised as the same concept in this domain."""

	source_jtbd_ids: list[str] = Field(default_factory=list)
	"""JTBDs that mention this term (for provenance / traceability)."""


class TermConflict(BaseModel):
	"""A detected cross-domain term collision.

	Raised when the same ``term`` appears with *different definitions* in
	two or more domains within the same bundle.
	"""

	model_config = ConfigDict(
		extra="forbid",
		validate_by_name=True,
		validate_by_alias=True,
	)

	term: str
	"""The conflicting term string."""

	domains: list[str]
	"""All domains that carry conflicting definitions for this term."""

	definitions: dict[str, str | None]
	"""Maps each domain to its definition (may be ``None`` if missing)."""

	source_jtbd_ids: list[str]
	"""All JTBD IDs that mention this term across the conflicting domains."""


# ---------------------------------------------------------------------------
# Private helpers (defined before GlossaryCatalog — used at module-init time)
# ---------------------------------------------------------------------------

def _normalise(term: str) -> str:
	"""Lower-case and strip a term string."""
	return term.strip().lower()


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class GlossaryCatalog:
	"""Shared terms catalog for a JTBD bundle or library set.

	Internally stores terms as ``dict[term -> list[GlossaryTerm]]``.
	Multiple entries for the same term are expected (one per domain).

	Thread-safety: not guaranteed — the catalog is typically built once at
	startup and then read-only.
	"""

	def __init__(self, terms: list[GlossaryTerm] | None = None) -> None:
		# term -> list of domain-scoped entries
		self._terms: dict[str, list[GlossaryTerm]] = {}
		for t in (terms or []):
			self._add(t)

	# ------------------------------------------------------------------
	# Mutation helpers
	# ------------------------------------------------------------------

	def add_term(self, term: GlossaryTerm) -> None:
		"""Register a term.  Duplicate (term, domain) pairs update in-place."""
		normalised = term.model_copy(update={"term": _normalise(term.term)})
		key = normalised.term
		existing = self._terms.setdefault(key, [])
		# Update or append.
		for i, entry in enumerate(existing):
			if entry.domain == normalised.domain:
				existing[i] = normalised
				return
		existing.append(normalised)

	def _add(self, term: GlossaryTerm) -> None:
		self.add_term(term)

	# ------------------------------------------------------------------
	# Queries
	# ------------------------------------------------------------------

	def terms_for(self, term: str) -> list[GlossaryTerm]:
		"""Return all domain-scoped entries for *term* (empty if absent)."""
		return list(self._terms.get(_normalise(term), []))

	def all_terms(self) -> list[str]:
		"""Sorted list of all distinct terms in the catalog."""
		return sorted(self._terms)

	def conflicts(self) -> list[TermConflict]:
		"""Return all detected cross-domain conflicts.

		A conflict exists when the same term carries *different* definitions
		(or one definition is missing while another is present) across two or
		more domains.  Terms where all domain-entries share the same definition
		(including both being ``None``) are considered consistent and are not
		flagged.
		"""
		out: list[TermConflict] = []
		for term_str, entries in sorted(self._terms.items()):
			# Only flag terms that appear in 2+ distinct domains.
			domain_entries = [e for e in entries if e.domain is not None]
			if len(domain_entries) < 2:
				continue
			definitions = {e.domain: e.definition for e in domain_entries if e.domain}
			distinct_defs = set(
				d if d is not None else "__MISSING__"
				for d in definitions.values()
			)
			if len(distinct_defs) <= 1:
				continue
			source_ids: list[str] = []
			for e in domain_entries:
				source_ids.extend(e.source_jtbd_ids)
			out.append(TermConflict(
				term=term_str,
				domains=sorted(definitions),
				definitions=definitions,
				source_jtbd_ids=sorted(set(source_ids)),
			))
		return out

	# ------------------------------------------------------------------
	# Construction helpers
	# ------------------------------------------------------------------

	@classmethod
	def from_bundle(cls, bundle: JtbdBundle) -> "GlossaryCatalog":
		"""Auto-populate a catalog from a JTBD bundle.

		Extracts:
		- Each spec's ``actor.role``
		- Each spec's ``jtbd_id`` segments (split on ``_``)
		- Any ``data_capture[].id`` strings from the spec's extra payload

		All extracted strings get ``definition=None`` so administrators can
		fill in meanings incrementally.
		"""
		catalog = cls()
		for spec in bundle.jtbds:
			domain = spec.domain
			jtbd_id = spec.jtbd_id

			# Actor role.
			if spec.actor and spec.actor.role:
				catalog.add_term(GlossaryTerm(
					term=spec.actor.role,
					domain=domain,
					source_jtbd_ids=[jtbd_id],
				))

			# Data-capture field IDs from extra payload (forward-compat).
			for field_id in _extract_data_capture_ids(spec):
				catalog.add_term(GlossaryTerm(
					term=field_id,
					domain=domain,
					source_jtbd_ids=[jtbd_id],
				))

			# JTBD id itself as a domain concept.
			catalog.add_term(GlossaryTerm(
				term=jtbd_id,
				domain=domain,
				source_jtbd_ids=[jtbd_id],
			))

		return catalog

	def merge(self, other: "GlossaryCatalog") -> "GlossaryCatalog":
		"""Return a new catalog that combines ``self`` and ``other``."""
		merged = GlossaryCatalog()
		for entries in self._terms.values():
			for t in entries:
				merged.add_term(t)
		for entries in other._terms.values():
			for t in entries:
				merged.add_term(t)
		return merged


# ---------------------------------------------------------------------------
# Built-in seed catalog
# ---------------------------------------------------------------------------

#: Common terms known to carry different meanings across insurance / legal /
#: healthcare / banking domains.  Authors should extend this with their own
#: library-level overrides.
BUILTIN_SEED: list[GlossaryTerm] = [
	# "claim" — classic cross-domain collision.
	GlossaryTerm(
		term="claim",
		domain="insurance",
		definition="An FNOL or formal request by a policyholder for loss recovery.",
		aliases=["fnol", "loss_claim"],
	),
	GlossaryTerm(
		term="claim",
		domain="legal",
		definition=(
			"A legal assertion or cause of action filed by a party in litigation."
		),
		aliases=["legal_claim", "cause_of_action"],
	),
	GlossaryTerm(
		term="claim",
		domain="healthcare",
		definition=(
			"A billing claim submitted to a payer for reimbursement of services."
		),
		aliases=["billing_claim", "remittance"],
	),
	# "account" — banking vs CRM.
	GlossaryTerm(
		term="account",
		domain="banking",
		definition="A deposit, loan, or transactional account held by a customer.",
		aliases=["bank_account", "deposit_account"],
	),
	GlossaryTerm(
		term="account",
		domain="crm",
		definition="A named organisation or individual tracked in the CRM.",
		aliases=["crm_account", "company"],
	),
	# "case" — legal vs gov.
	GlossaryTerm(
		term="case",
		domain="legal",
		definition="A legal matter or lawsuit managed by the legal team.",
	),
	GlossaryTerm(
		term="case",
		domain="gov",
		definition=(
			"A citizen service request or regulatory case managed by a government"
			" agency."
		),
	),
	# "party" — insurance vs banking vs legal.
	GlossaryTerm(
		term="party",
		domain="insurance",
		definition="A policyholder, claimant, or third party on a policy.",
	),
	GlossaryTerm(
		term="party",
		domain="banking",
		definition=(
			"A KYC-verified individual or legal entity that holds or is party to"
			" a financial instrument."
		),
	),
	GlossaryTerm(
		term="party",
		domain="legal",
		definition=(
			"A named participant in litigation: plaintiff, defendant, or third party."
		),
	),
	# "intake" — insurance vs hr.
	GlossaryTerm(
		term="intake",
		domain="insurance",
		definition="The first-notice-of-loss ingestion step for a new claim.",
	),
	GlossaryTerm(
		term="intake",
		domain="hr",
		definition="The onboarding intake process for a new employee or contractor.",
	),
]


def _build_builtin_catalog() -> GlossaryCatalog:
	return GlossaryCatalog(BUILTIN_SEED)


#: Ready-to-use catalog seeded with common cross-domain terms.
#: Pass to :class:`lint.glossary.GlossaryConflictRulePack` directly.
BUILTIN_CATALOG: GlossaryCatalog = _build_builtin_catalog()


def _extract_data_capture_ids(spec: JtbdLintSpec) -> list[str]:
	"""Pull ``data_capture[].id`` strings from the spec's extra payload.

	The ``JtbdLintSpec`` model uses ``extra='allow'`` so the data-capture
	list (defined in the full E-1 canonical schema) passes through as-is
	in ``model_extra``.
	"""
	extra: dict[str, Any] = spec.model_extra or {}
	raw = extra.get("data_capture") or []
	ids: list[str] = []
	if not isinstance(raw, list):
		return ids
	for item in raw:
		if isinstance(item, dict):
			field_id = item.get("id")
			if field_id and isinstance(field_id, str):
				ids.append(field_id)
	return ids


__all__ = [
	"BUILTIN_CATALOG",
	"BUILTIN_SEED",
	"GlossaryCatalog",
	"GlossaryTerm",
	"TermConflict",
]
