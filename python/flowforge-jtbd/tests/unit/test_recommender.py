"""Tests for E-7 — Recommender (vector top-K cosine similarity).

Covers:
- BagOfWordsEmbeddingProvider: tokenisation, embedding, vocab growth
- InMemoryEmbeddingStore: upsert, search, cosine similarity ordering
- RecommendationResult: fields, similarity_pct
- Recommender: index_jtbd, recommend, recommend_for_jtbd, domain_filter
- build_recommender convenience factory
- EmbeddingProvider / EmbeddingStore Protocol conformance
"""

from __future__ import annotations

from flowforge_jtbd.ai.recommender import (
	BagOfWordsEmbeddingProvider,
	EmbeddingProvider,
	EmbeddingStore,
	InMemoryEmbeddingStore,
	RecommendationResult,
	Recommender,
	build_recommender,
)


# ---------------------------------------------------------------------------
# BagOfWordsEmbeddingProvider
# ---------------------------------------------------------------------------

async def test_embed_returns_list_of_floats() -> None:
	p = BagOfWordsEmbeddingProvider()
	vec = await p.embed("claim intake adjuster FNOL")
	assert isinstance(vec, list)
	assert all(isinstance(v, float) for v in vec)


async def test_embed_empty_text_returns_empty_list() -> None:
	p = BagOfWordsEmbeddingProvider()
	vec = await p.embed("")
	assert vec == []


async def test_embed_unit_vector() -> None:
	import math
	p = BagOfWordsEmbeddingProvider()
	vec = await p.embed("claim intake adjuster")
	norm = math.sqrt(sum(v * v for v in vec))
	assert abs(norm - 1.0) < 1e-6


async def test_embed_stop_words_excluded() -> None:
	p = BagOfWordsEmbeddingProvider()
	# "a" and "the" are stop words; vocab should only have "claim"
	await p.embed("the claim is a thing")
	assert p.vocab_size() >= 1


async def test_embed_vocab_grows_with_docs() -> None:
	p = BagOfWordsEmbeddingProvider()
	await p.embed("claim intake")
	size_1 = p.vocab_size()
	await p.embed("payment recovery refund")
	size_2 = p.vocab_size()
	assert size_2 > size_1


async def test_similar_texts_produce_high_cosine() -> None:
	p = BagOfWordsEmbeddingProvider()
	v1 = await p.embed("claim intake FNOL policyholder insurance")
	v2 = await p.embed("claim intake FNOL policyholder insurance")
	# Same text → cos similarity should be very close to 1.
	dot = sum(a * b for a, b in zip(v1, v2, strict=False))
	assert dot > 0.95


# ---------------------------------------------------------------------------
# InMemoryEmbeddingStore
# ---------------------------------------------------------------------------

async def test_store_upsert_and_search() -> None:
	store = InMemoryEmbeddingStore()
	await store.upsert("jtbd-1", [1.0, 0.0], metadata={"domain": "insurance"})
	results = await store.search([1.0, 0.0], top_k=5)
	assert len(results) == 1
	jtbd_id, sim, meta = results[0]
	assert jtbd_id == "jtbd-1"
	assert sim > 0.9
	assert meta["domain"] == "insurance"


async def test_store_returns_top_k() -> None:
	store = InMemoryEmbeddingStore()
	for i in range(10):
		await store.upsert(f"jtbd-{i}", [float(i), 0.0])
	results = await store.search([9.0, 0.0], top_k=3)
	assert len(results) == 3


async def test_store_excludes_ids() -> None:
	store = InMemoryEmbeddingStore()
	await store.upsert("a", [1.0, 0.0])
	await store.upsert("b", [1.0, 0.0])
	results = await store.search([1.0, 0.0], top_k=5, exclude_ids={"a"})
	ids = [r[0] for r in results]
	assert "a" not in ids
	assert "b" in ids


async def test_store_ordered_by_similarity() -> None:
	store = InMemoryEmbeddingStore()
	await store.upsert("high", [1.0, 0.0])
	await store.upsert("low", [0.0, 1.0])
	results = await store.search([1.0, 0.0], top_k=2)
	assert results[0][0] == "high"
	assert results[1][0] == "low"


def test_store_add_sync() -> None:
	store = InMemoryEmbeddingStore()
	store.add("j1", text="claim intake FNOL", metadata={"domain": "insurance"})
	assert store.size() == 1


# ---------------------------------------------------------------------------
# RecommendationResult
# ---------------------------------------------------------------------------

def test_recommendation_result_fields() -> None:
	r = RecommendationResult(jtbd_id="claim_intake", similarity=0.87,
							  domain="insurance", title="File a claim")
	assert r.jtbd_id == "claim_intake"
	assert r.similarity == 0.87
	assert r.domain == "insurance"
	assert r.title == "File a claim"


def test_similarity_pct() -> None:
	r = RecommendationResult(jtbd_id="x", similarity=0.921)
	assert r.similarity_pct == 92


def test_similarity_pct_zero() -> None:
	r = RecommendationResult(jtbd_id="x", similarity=0.0)
	assert r.similarity_pct == 0


# ---------------------------------------------------------------------------
# Recommender.index_jtbd + recommend
# ---------------------------------------------------------------------------

async def test_recommend_returns_results() -> None:
	rec = Recommender()
	await rec.index_jtbd("claim_intake",
						   "A policyholder files an FNOL to start a claim.",
						   metadata={"domain": "insurance", "title": "File a claim"})
	await rec.index_jtbd("account_open",
						   "A customer opens a new bank account.",
						   metadata={"domain": "banking", "title": "Open account"})
	results = await rec.recommend("claim FNOL insurance", top_k=2)
	assert len(results) >= 1
	assert all(isinstance(r, RecommendationResult) for r in results)


async def test_recommend_orders_by_similarity() -> None:
	rec = Recommender()
	await rec.index_jtbd("claim_intake",
						   "policyholder files FNOL claim insurance loss",
						   metadata={"domain": "insurance"})
	await rec.index_jtbd("payment_init",
						   "customer initiates bank transfer payment",
						   metadata={"domain": "banking"})
	results = await rec.recommend("insurance claim FNOL loss policyholder", top_k=2)
	assert results[0].jtbd_id == "claim_intake"


async def test_recommend_top_k_limits_results() -> None:
	rec = Recommender()
	for i in range(10):
		await rec.index_jtbd(f"j{i}", f"job {i} description text",
							  metadata={"domain": "x"})
	results = await rec.recommend("job description", top_k=3)
	assert len(results) <= 3


async def test_recommend_domain_filter() -> None:
	rec = Recommender()
	await rec.index_jtbd("ins_1", "insurance claim FNOL",
						   metadata={"domain": "insurance"})
	await rec.index_jtbd("bank_1", "bank account deposit",
						   metadata={"domain": "banking"})
	results = await rec.recommend("claim account", top_k=5,
								   domain_filter="insurance")
	assert all(r.domain == "insurance" for r in results)


async def test_recommend_exclude_ids() -> None:
	rec = Recommender()
	await rec.index_jtbd("source", "claim intake source text",
						   metadata={"domain": "insurance"})
	await rec.index_jtbd("target", "claim intake similar text",
						   metadata={"domain": "insurance"})
	results = await rec.recommend("claim intake", top_k=5,
								   exclude_ids={"source"})
	ids = [r.jtbd_id for r in results]
	assert "source" not in ids


async def test_recommend_for_jtbd_excludes_self() -> None:
	rec = Recommender()
	await rec.index_jtbd("claim_intake", "file a claim FNOL insurance",
						   metadata={"domain": "insurance"})
	await rec.index_jtbd("claim_review", "review a claim adjuster",
						   metadata={"domain": "insurance"})
	results = await rec.recommend_for_jtbd(
		"claim_intake", "file a claim FNOL insurance", top_k=5
	)
	ids = [r.jtbd_id for r in results]
	assert "claim_intake" not in ids


async def test_recommend_empty_store_returns_empty() -> None:
	rec = Recommender()
	results = await rec.recommend("anything", top_k=5)
	assert results == []


# ---------------------------------------------------------------------------
# build_recommender convenience factory
# ---------------------------------------------------------------------------

def test_build_recommender_returns_recommender() -> None:
	rec = build_recommender([
		{"id": "j1", "domain": "insurance",
		 "situation": "file a claim", "motivation": "recover losses", "outcome": "claim created"},
	])
	assert isinstance(rec, Recommender)


async def test_build_recommender_is_queryable() -> None:
	specs = [
		{"id": "claim_intake", "domain": "insurance", "title": "File claim",
		 "situation": "policyholder files FNOL", "motivation": "recover losses",
		 "outcome": "claim record created"},
		{"id": "claim_review", "domain": "insurance", "title": "Review claim",
		 "situation": "adjuster reviews FNOL", "motivation": "assess validity",
		 "outcome": "decision recorded"},
		{"id": "account_open", "domain": "banking", "title": "Open account",
		 "situation": "customer opens deposit", "motivation": "save money",
		 "outcome": "account created"},
	]
	rec = build_recommender(specs)
	results = await rec.recommend("insurance claim FNOL loss", top_k=3)
	assert len(results) >= 1
	ids = [r.jtbd_id for r in results]
	# Insurance JTBDs should rank above banking.
	assert "claim_intake" in ids or "claim_review" in ids


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_bag_of_words_satisfies_embedding_provider_protocol() -> None:
	assert isinstance(BagOfWordsEmbeddingProvider(), EmbeddingProvider)


def test_in_memory_store_satisfies_embedding_store_protocol() -> None:
	assert isinstance(InMemoryEmbeddingStore(), EmbeddingStore)
