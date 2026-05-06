"""DomainInferer — recommend starter library JTBDs from an NL description.

Per ``framework/docs/jtbd-editor-arch.md`` §4.2 and
``framework/docs/flowforge-evolution.md`` §6.3 (E-15). Sits on top of
the recommender shipped in E-7:

```
description ──► EmbeddingProvider.embed ──► EmbeddingStore.search(top_k=10)
              │                                                   │
              └─► detect_domains() ──► filter by domain match ◄────┘
                                                │
                                                ▼
                                        ranked starter JTBDs
```

Two modes
---------

* **Targeted** — caller pins one or more domains (``domains=['banking']``)
  and the recommender's ``domain_filter`` returns only library JTBDs
  tagged with that domain in their metadata.
* **Auto** — caller leaves ``domains`` unset; the inferer scans the
  description for known domain keywords and runs the recommender once
  per detected domain, then merges results in similarity order.

The keyword catalogue covers the 30 domain libraries enumerated in
``flowforge-evolution.md`` §12 — extensible via the ``domain_keywords``
constructor argument.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .recommender import RecommendationResult, Recommender


# ---------------------------------------------------------------------------
# Domain keyword catalogue
# ---------------------------------------------------------------------------

# Maps domain name → keyword list. The keys MUST match the ``domain``
# tag the library packs stamp on each JTBD's metadata so the recommender's
# ``domain_filter`` matches by string equality. Subdomains live alongside
# their parent — e.g., a "kanban" keyword detection routes to the
# "project_mgmt" domain.
#
# When extending, prefer multi-word phrases over single ambiguous words
# ("loan origination" over "loan") so the inferer does not over-match.
_DEFAULT_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
	"accounting": (
		"accounts payable", "ap invoice", "ar receivable", "general ledger",
		"payroll", "tax filing", "journal entry", "reconciliation",
	),
	"corp_finance": (
		"treasury", "budget forecast", "cash forecast", "fp&a",
		"financial planning",
	),
	"project_mgmt": (
		"kanban", "scrum", "waterfall", "sprint", "milestone", "deliverable",
		"project charter", "rfc",
	),
	"hr": (
		"hiring", "candidate", "applicant", "onboarding", "leave request",
		"performance review", "kpi review", "termination",
	),
	"crm": (
		"lead", "opportunity", "deal", "pipeline", "quote", "renewal",
		"churn", "upsell",
	),
	"banking": (
		"account open", "deposit account", "loan origination", "card issue",
		"kyc", "aml", "wire transfer",
	),
	"insurance": (
		"policy", "underwrite", "fnol", "claim", "adjuster",
		"premium", "policyholder",
	),
	"healthcare": (
		"patient", "diagnosis", "clinical", "medical record", "prescription",
		"referral", "appointment",
	),
	"gov": (
		"permit", "license", "citizen", "council", "tribunal",
		"public records",
	),
	"legal": (
		"contract", "litigation", "case file", "discovery",
		"settlement",
	),
	"education": (
		"enrolment", "transcript", "grade book", "course offering",
		"student record",
	),
	"manufacturing": (
		"work order", "bom", "bill of materials", "production schedule",
		"shop floor",
	),
	"supply_chain": (
		"purchase order", "po approval", "shipment", "receipt",
		"inventory", "stock take",
	),
	"retail": (
		"sales order", "refund", "return merchandise", "rma",
		"loyalty",
	),
	"hospitality": (
		"booking", "reservation", "check-in", "check-out", "front desk",
	),
	"real_estate": (
		"listing", "showing", "lease", "rental application",
		"property valuation",
	),
	"construction": (
		"building permit", "rfi", "punch list", "submittal",
		"change order",
	),
	"transport": (
		"delivery route", "shipment", "dispatch", "load planning",
		"freight",
	),
	"media": (
		"editorial", "content review", "publication", "ad approval",
	),
	"nonprofit": (
		"grant application", "donation", "donor", "fundraising",
	),
	"sports": (
		"match fixture", "roster", "league standings",
	),
	"agriculture": (
		"crop plan", "harvest", "farm input", "yield report",
	),
	"energy": (
		"meter read", "outage", "service connection",
	),
	"telecom": (
		"trouble ticket", "service activation", "porting",
	),
	"saas": (
		"subscription", "trial", "feature flag",
	),
	"compliance": (
		"audit finding", "control test", "risk assessment", "soc2",
	),
	"security": (
		"incident response", "vulnerability", "penetration test",
		"ioc",
	),
	"it_ops": (
		"change request", "rfc approval", "cmdb",
	),
	"research": (
		"experiment", "trial protocol", "lab notebook",
	),
	"travel": (
		"itinerary", "expense report", "trip approval",
	),
}


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainHit:
	"""One detected domain + the keyword that triggered it.

	``confidence`` counts how many distinct keyword phrases matched —
	useful for the editor to show "high / medium / low" badges next to
	suggested starter packs.
	"""

	domain: str
	matched_keywords: tuple[str, ...]
	confidence: int


@dataclass(frozen=True)
class DomainInferenceResult:
	"""Aggregated result of a single :meth:`DomainInferer.infer` call."""

	hits: tuple[DomainHit, ...]
	recommendations: tuple[RecommendationResult, ...]
	# Echoed for transparency: domains the inferer queried (auto- or
	# user-pinned).
	queried_domains: tuple[str, ...]


# ---------------------------------------------------------------------------
# Inferer
# ---------------------------------------------------------------------------


@dataclass
class DomainInferer:
	"""Recommend starter library JTBDs for a free-text description.

	Wires together domain detection (keyword catalogue) and the E-7
	:class:`Recommender` (embedding cosine search). When run in auto
	mode, queries the recommender once per detected domain and merges
	results in similarity-descending order.
	"""

	recommender: Recommender
	domain_keywords: dict[str, tuple[str, ...]] = field(
		default_factory=lambda: dict(_DEFAULT_DOMAIN_KEYWORDS),
	)

	def detect_domains(self, description: str) -> tuple[DomainHit, ...]:
		"""Return the domains whose keywords appear in *description*.

		Order is by confidence (highest first); ties broken
		alphabetically by domain name for deterministic output.
		"""
		assert description is not None, "description must not be None"
		lowered = description.lower()
		hits: list[DomainHit] = []
		for domain in sorted(self.domain_keywords):
			matched = tuple(
				keyword
				for keyword in self.domain_keywords[domain]
				if keyword.lower() in lowered
			)
			if matched:
				hits.append(DomainHit(
					domain=domain,
					matched_keywords=matched,
					confidence=len(matched),
				))
		hits.sort(key=lambda hit: (-hit.confidence, hit.domain))
		return tuple(hits)

	async def infer(
		self,
		description: str,
		*,
		top_k: int = 5,
		domains: Iterable[str] | None = None,
	) -> DomainInferenceResult:
		"""Return ranked starter library JTBDs for *description*.

		* ``top_k`` is the per-domain ceiling. Auto mode totals up to
		  ``top_k * len(detected_domains)`` results.
		* ``domains`` pins the search; auto-detection is skipped.
		* When neither auto-detection nor user pin produces a domain,
		  the inferer falls back to a single domain-less recommend
		  call (whatever the embedding store ranks highest).
		"""
		assert description, "description must not be empty"
		assert top_k >= 1, "top_k must be ≥ 1"

		if domains is not None:
			pinned = tuple(domains)
			assert pinned, "domains, if provided, must not be empty"
			detected: tuple[DomainHit, ...] = ()
			queried = pinned
		else:
			detected = self.detect_domains(description)
			queried = tuple(hit.domain for hit in detected)

		if not queried:
			# Fallback: no domain context. Return whatever the recommender
			# ranks highest from the whole library.
			results = await self.recommender.recommend(
				description,
				top_k=top_k,
			)
			return DomainInferenceResult(
				hits=(),
				recommendations=tuple(results),
				queried_domains=(),
			)

		merged: dict[str, RecommendationResult] = {}
		for domain in queried:
			results = await self.recommender.recommend(
				description,
				top_k=top_k,
				domain_filter=domain,
			)
			for result in results:
				existing = merged.get(result.jtbd_id)
				if existing is None or result.similarity > existing.similarity:
					merged[result.jtbd_id] = result

		ranked = sorted(
			merged.values(),
			key=lambda r: (-r.similarity, r.jtbd_id),
		)
		return DomainInferenceResult(
			hits=detected,
			recommendations=tuple(ranked[:top_k * max(1, len(queried))]),
			queried_domains=queried,
		)


__all__ = [
	"DomainHit",
	"DomainInferenceResult",
	"DomainInferer",
]
