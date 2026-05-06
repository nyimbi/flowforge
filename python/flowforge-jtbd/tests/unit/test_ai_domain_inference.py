"""DomainInferer — keyword detection + per-domain recommendation merge."""

from __future__ import annotations

import pytest

from flowforge_jtbd.ai.domain_inference import (
	DomainInferenceResult,
	DomainInferer,
)
from flowforge_jtbd.ai.recommender import (
	InMemoryEmbeddingStore,
	Recommender,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_inferer() -> DomainInferer:
	"""Build a fully populated inferer over a 9-spec library spanning 3 domains."""
	store = InMemoryEmbeddingStore()
	rec = Recommender(store=store)

	specs = [
		# Banking
		("account_open", "A customer opens a new deposit account with KYC.", "banking"),
		("loan_origination", "A bank originates a consumer loan after underwriting.", "banking"),
		("card_issue", "Bank issues a new payment card.", "banking"),
		# Insurance
		("claim_intake", "A claimant files an FNOL to start a claim.", "insurance"),
		("policy_underwrite", "Underwrite a new auto insurance policy.", "insurance"),
		("renewal_intake", "Renew an existing insurance policy.", "insurance"),
		# Healthcare
		("appointment_book", "A patient books a clinical appointment.", "healthcare"),
		("prescription_issue", "A clinician issues a prescription for a patient.", "healthcare"),
		("referral_create", "Refer a patient to a specialist.", "healthcare"),
	]

	for jtbd_id, text, domain in specs:
		await rec.index_jtbd(
			jtbd_id,
			text=text,
			metadata={"domain": domain, "title": jtbd_id.replace("_", " ").title()},
		)

	return DomainInferer(recommender=rec)


# ---------------------------------------------------------------------------
# detect_domains
# ---------------------------------------------------------------------------


def test_detect_domains_picks_single_match() -> None:
	rec = Recommender(store=InMemoryEmbeddingStore())
	inferer = DomainInferer(recommender=rec)
	hits = inferer.detect_domains(
		"A bank runs KYC checks before opening a deposit account.",
	)
	# 'kyc' + 'deposit account' both match banking.
	assert any(h.domain == "banking" for h in hits)


def test_detect_domains_orders_by_confidence() -> None:
	rec = Recommender(store=InMemoryEmbeddingStore())
	inferer = DomainInferer(recommender=rec)
	# Description hits multiple banking phrases and one insurance phrase.
	desc = (
		"After KYC and underwriting, the bank handles loan origination "
		"and processes wire transfers; meanwhile insurance underwrites "
		"a policy."
	)
	hits = inferer.detect_domains(desc)
	# Banking should outrank insurance — three keywords vs one.
	by_domain = {h.domain: h for h in hits}
	assert "banking" in by_domain
	assert "insurance" in by_domain
	assert hits[0].domain == "banking"
	assert by_domain["banking"].confidence > by_domain["insurance"].confidence


def test_detect_domains_returns_empty_when_no_keywords_match() -> None:
	rec = Recommender(store=InMemoryEmbeddingStore())
	inferer = DomainInferer(recommender=rec)
	hits = inferer.detect_domains("an ops engineer triages a noisy alert")
	# 'ops engineer' is not in any catalogue entry.
	assert all(h.domain != "banking" for h in hits)


def test_detect_domains_is_deterministic_across_runs() -> None:
	rec = Recommender(store=InMemoryEmbeddingStore())
	inferer = DomainInferer(recommender=rec)
	desc = "the patient books an appointment for a prescription refill"
	first = inferer.detect_domains(desc)
	second = inferer.detect_domains(desc)
	assert first == second


def test_detect_domains_keyword_returned_in_match_list() -> None:
	rec = Recommender(store=InMemoryEmbeddingStore())
	inferer = DomainInferer(recommender=rec)
	hits = inferer.detect_domains("kanban sprint deliverable on the team board")
	pm = next((h for h in hits if h.domain == "project_mgmt"), None)
	assert pm is not None
	assert "kanban" in pm.matched_keywords
	assert "sprint" in pm.matched_keywords


# ---------------------------------------------------------------------------
# infer (auto mode)
# ---------------------------------------------------------------------------


async def test_infer_auto_mode_uses_detected_domains() -> None:
	inferer = await _build_inferer()
	result = await inferer.infer(
		"A bank originates a consumer loan after underwriting and KYC.",
		top_k=3,
	)
	assert isinstance(result, DomainInferenceResult)
	assert "banking" in result.queried_domains
	# Every recommendation comes from the banking pack.
	for rec in result.recommendations:
		assert rec.domain == "banking", rec


async def test_infer_auto_mode_merges_multiple_domains() -> None:
	inferer = await _build_inferer()
	result = await inferer.infer(
		"After the bank's kyc check the clinical staff book an "
		"appointment for the patient.",
		top_k=3,
	)
	domains_in_results = {r.domain for r in result.recommendations}
	# Both banking + healthcare libraries should surface.
	assert "banking" in domains_in_results
	assert "healthcare" in domains_in_results


async def test_infer_falls_back_when_no_domain_detected() -> None:
	inferer = await _build_inferer()
	result = await inferer.infer(
		"Some completely unrelated description without keyword matches.",
		top_k=3,
	)
	# No domains queried, but the recommender still returns something
	# from the whole library (or empty if the embedder produces zero
	# similarity, which it usually does not for a non-trivial query).
	assert result.queried_domains == ()
	assert result.hits == ()
	assert isinstance(result.recommendations, tuple)


# ---------------------------------------------------------------------------
# infer (targeted mode)
# ---------------------------------------------------------------------------


async def test_infer_targeted_skips_auto_detection() -> None:
	inferer = await _build_inferer()
	# Description doesn't trigger any banking keyword, but the caller
	# pinned banking explicitly.
	result = await inferer.infer(
		"alpha beta gamma delta",
		top_k=3,
		domains=["banking"],
	)
	assert result.queried_domains == ("banking",)
	# Auto-detection skipped → no hits surfaced.
	assert result.hits == ()
	for rec in result.recommendations:
		assert rec.domain == "banking"


async def test_infer_targeted_multiple_domains() -> None:
	inferer = await _build_inferer()
	result = await inferer.infer(
		"a generic process description",
		top_k=2,
		domains=["banking", "healthcare"],
	)
	assert set(result.queried_domains) == {"banking", "healthcare"}
	for rec in result.recommendations:
		assert rec.domain in {"banking", "healthcare"}


async def test_infer_dedupes_per_jtbd_id() -> None:
	"""When the same jtbd_id legitimately surfaces from multiple domain
	queries (theoretically possible if the catalogue tags multi-domain),
	the inferer keeps the highest-similarity entry."""
	inferer = await _build_inferer()
	result = await inferer.infer(
		"customer opens an account",
		top_k=5,
		domains=["banking", "banking"],  # duplicate query — identity output
	)
	# Output should not contain the same jtbd_id twice.
	ids = [r.jtbd_id for r in result.recommendations]
	assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


async def test_infer_rejects_empty_description() -> None:
	inferer = await _build_inferer()
	with pytest.raises(AssertionError):
		await inferer.infer("", top_k=3)


async def test_infer_rejects_zero_top_k() -> None:
	inferer = await _build_inferer()
	with pytest.raises(AssertionError):
		await inferer.infer("description", top_k=0)


async def test_infer_rejects_empty_domains_list() -> None:
	inferer = await _build_inferer()
	with pytest.raises(AssertionError):
		await inferer.infer("description", top_k=3, domains=[])


# ---------------------------------------------------------------------------
# Custom keyword catalogue
# ---------------------------------------------------------------------------


def test_custom_keyword_catalogue_extends_detection() -> None:
	rec = Recommender(store=InMemoryEmbeddingStore())
	inferer = DomainInferer(
		recommender=rec,
		domain_keywords={"music": ("setlist", "rehearsal")},
	)
	hits = inferer.detect_domains("the band plans a setlist for rehearsal")
	assert any(h.domain == "music" for h in hits)
	# Default banking / insurance no longer exist in this catalogue.
	assert all(h.domain not in {"banking", "insurance"} for h in hits)
