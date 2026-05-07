"""JTBD Recommender — embedding-based top-K cosine similarity (E-7).

Per ``framework/docs/jtbd-editor-arch.md`` §7.2 and
``framework/docs/flowforge-evolution.md`` §9.

The recommender surfaces "jobs that work well together" in the editor
sidebar by ranking the registered JTBD library against a query using
cosine similarity over embedding vectors.

Architecture
------------
The two ports (:class:`EmbeddingProvider` and :class:`EmbeddingStore`)
are intentionally thin so that the full pgvector implementation (E-15)
can drop in without touching the recommender logic.

Defaults
--------
When no :class:`EmbeddingProvider` is supplied, the recommender falls
back to :class:`BagOfWordsEmbeddingProvider` — a TF-IDF-like bag-of-words
vectoriser that works fully offline.  This provides reasonable similarity
rankings for the test suite and for host environments that have not yet
wired a real embedding model.

Usage
-----
.. code-block:: python

    from flowforge_jtbd.ai.recommender import (
        InMemoryEmbeddingStore,
        Recommender,
    )

    store = InMemoryEmbeddingStore()
    store.add("claim_intake",
              text="A policyholder files an FNOL to start a claim.",
              metadata={"domain": "insurance", "title": "File a claim"})
    store.add("account_open",
              text="A customer opens a new deposit account.",
              metadata={"domain": "banking", "title": "Open account"})

    rec = Recommender(store=store)
    results = await rec.recommend("claim payment recovery", top_k=3)
    for r in results:
        print(f"{r.jtbd_id}: {r.similarity:.0%} ({r.domain})")
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# audit-2026 J-04: warning category for default-store performance hints.
class PerformanceWarning(UserWarning):
	"""Emitted when a low-throughput default is used in a production-shaped path."""


# ---------------------------------------------------------------------------
# Protocols (ports)
# ---------------------------------------------------------------------------

@runtime_checkable
class EmbeddingProvider(Protocol):
	"""Produce a dense embedding vector for a text string.

	The default implementation (:class:`BagOfWordsEmbeddingProvider`) is
	fully offline.  The production implementation (E-15) uses Claude or a
	local Sentence-Transformers model.
	"""

	async def embed(self, text: str) -> list[float]:
		"""Return a normalised embedding vector for *text*."""
		...


@runtime_checkable
class EmbeddingStore(Protocol):
	"""Store and retrieve embedding vectors for JTBD specs.

	The default implementation (:class:`InMemoryEmbeddingStore`) uses
	a plain Python dict.  The production implementation (E-15) uses
	pgvector with ``<=>`` cosine distance index.
	"""

	async def upsert(
		self,
		jtbd_id: str,
		vector: list[float],
		*,
		metadata: dict[str, Any] | None = None,
	) -> None:
		"""Store or replace the vector for *jtbd_id*."""
		...

	async def search(
		self,
		query_vector: list[float],
		*,
		top_k: int = 10,
		exclude_ids: set[str] | None = None,
	) -> list[tuple[str, float, dict[str, Any]]]:
		"""Return top-K (jtbd_id, similarity, metadata) tuples.

		Similarities are in ``[0.0, 1.0]``.  Higher is more similar.
		"""
		...


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecommendationResult:
	"""One item in the recommendation list.

	Surfaces in the editor sidebar as:
	``• <jtbd_id>  —  <similarity %> (<domain>)``
	"""

	jtbd_id: str
	similarity: float
	"""Cosine similarity in ``[0.0, 1.0]``."""

	domain: str | None = None
	title: str | None = None
	metadata: dict[str, Any] = field(default_factory=dict)

	@property
	def similarity_pct(self) -> int:
		"""Similarity as a 0-100 integer percentage."""
		return round(self.similarity * 100)


# ---------------------------------------------------------------------------
# BagOfWordsEmbeddingProvider — offline fallback
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset(
	"a an the and or but in on at to of for with by from is are was were "
	"be been being have has had do does did will would could should may might "
	"shall can its it this that these those which who what when where how "
	"i we you they he she not no up out as if so".split()
)

_TOKEN_RE = re.compile(r"\b[a-z]{2,}\b")


def _tokenise(text: str) -> list[str]:
	return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP_WORDS]


class BagOfWordsEmbeddingProvider:
	"""Offline TF-IDF-like bag-of-words embedder.

	Produces sparse unit vectors suitable for cosine similarity. The
	vocabulary and document-frequency model can be built once via
	:meth:`fit`, then frozen so subsequent :meth:`transform` calls return
	deterministic vectors against a stable basis.

	Workflow (audit-2026 J-03)
	--------------------------
	* :meth:`fit` accepts a corpus and computes vocab + IDF in one pass.
	* :meth:`freeze` seals the model. Post-freeze, :meth:`embed` raises
	  :class:`EmbeddingProviderFrozenError` if the input introduces a
	  token not present in the frozen vocabulary; :meth:`transform`
	  silently drops unknown tokens (the deterministic-replay path).
	* Pre-freeze, :meth:`embed` lazily updates the model — backwards
	  compatible with E-7 callers that didn't separate fit / transform.

	Replay determinism: under the frozen model two ``embed("x")`` calls
	return byte-identical vectors. Under the legacy lazy mode they did
	not, because each call mutated ``_df`` and shifted the basis.

	The pgvector provider (E-15) is a drop-in replacement.
	"""

	def __init__(self) -> None:
		self._doc_count: int = 0
		self._df: Counter[str] = Counter()
		# Raw token counts per doc — kept for legacy lazy mode only.
		self._docs: list[set[str]] = []
		# audit-2026 J-03: stable vocab + freeze flag.
		self._vocab: list[str] = []
		self._frozen: bool = False

	# ------------------------------------------------------------------
	# fit / transform / freeze (audit-2026 J-03)
	# ------------------------------------------------------------------

	def fit(self, corpus: list[str]) -> "BagOfWordsEmbeddingProvider":
		"""Build vocabulary + document frequencies from *corpus* in one pass.

		Subsequent :meth:`transform` calls produce vectors over the
		fitted basis. Returns ``self`` to support chaining (
		``provider.fit(docs).freeze()``).
		"""

		assert isinstance(corpus, list)
		if self._frozen:
			raise EmbeddingProviderFrozenError(
				"BagOfWordsEmbeddingProvider is frozen — call .unfreeze() before .fit()"
			)
		self._doc_count = 0
		self._df = Counter()
		self._docs = []
		for text in corpus:
			tokens = _tokenise(text)
			if not tokens:
				continue
			self._doc_count += 1
			terms = set(tokens)
			self._docs.append(terms)
			for t in terms:
				self._df[t] += 1
		self._vocab = sorted(self._df)
		return self

	def freeze(self) -> "BagOfWordsEmbeddingProvider":
		"""Seal the vocabulary + IDF so the basis is stable for replay."""

		if not self._vocab and self._df:
			# Caller used legacy embed() to populate state — capture the
			# current vocab as the frozen basis.
			self._vocab = sorted(self._df)
		self._frozen = True
		return self

	def unfreeze(self) -> None:
		"""Test-only: lift the freeze so :meth:`fit` can rebuild the basis."""

		self._frozen = False

	def is_frozen(self) -> bool:
		return self._frozen

	def transform(self, text: str) -> list[float]:
		"""Return the TF-IDF unit vector for *text* over the fitted vocab.

		Tokens not present in the fitted vocabulary are silently
		dropped — :meth:`transform` never mutates state. If no vocab has
		been fit yet, the empty vector is returned.
		"""

		if not self._vocab:
			# Fallback: behave like the legacy lazy path on first text.
			vocab = sorted(self._df) or []
		else:
			vocab = self._vocab
		if not vocab:
			return []
		tokens = _tokenise(text)
		if not tokens:
			return [0.0] * len(vocab)
		tf = Counter(t for t in tokens if t in self._df)
		total = sum(Counter(tokens).values()) or 1
		vec: list[float] = []
		for term in vocab:
			tf_val = tf.get(term, 0) / total
			idf = math.log((1 + self._doc_count) / (1 + self._df.get(term, 0))) + 1
			vec.append(tf_val * idf)
		norm = math.sqrt(sum(v * v for v in vec))
		if norm == 0:
			return [0.0] * len(vocab)
		return [v / norm for v in vec]

	# ------------------------------------------------------------------
	# embed (back-compat surface)
	# ------------------------------------------------------------------

	async def embed(self, text: str) -> list[float]:
		"""Return a TF-IDF unit vector.

		Pre-freeze: lazily updates the vocabulary + IDF (legacy E-7
		behaviour). Post-freeze: equivalent to :meth:`transform`, except
		that introducing a never-seen token raises
		:class:`EmbeddingProviderFrozenError` so a silent vector-basis
		shift cannot occur in production replay paths.
		"""

		tokens = _tokenise(text)
		if self._frozen:
			# audit-2026 J-03: any token outside the frozen vocab → raise.
			unknown = [t for t in tokens if t not in self._df]
			if unknown:
				raise EmbeddingProviderFrozenError(
					f"embed() received {len(unknown)} unknown token(s) under a "
					f"frozen vocabulary: {sorted(set(unknown))[:5]!r}"
					"; call transform() to drop unknown tokens silently."
				)
			return self.transform(text)
		if not tokens:
			return []
		# Legacy lazy path — kept for backwards compatibility with E-7.
		tf = Counter(tokens)
		total = sum(tf.values())
		self._doc_count += 1
		terms_in_doc = set(tokens)
		for t in terms_in_doc:
			self._df[t] += 1
		self._docs.append(terms_in_doc)
		vocab = list(self._df)
		vec: list[float] = []
		for term in vocab:
			tf_val = tf.get(term, 0) / total
			idf = math.log((1 + self._doc_count) / (1 + self._df[term])) + 1
			vec.append(tf_val * idf)
		norm = math.sqrt(sum(v * v for v in vec))
		if norm == 0:
			return [0.0] * len(vocab)
		return [v / norm for v in vec]

	def vocab_size(self) -> int:
		return len(self._vocab) if self._frozen else len(self._df)


class EmbeddingProviderFrozenError(RuntimeError):
	"""Raised when ``embed()`` would mutate a frozen vocabulary (audit-2026 J-03)."""


# ---------------------------------------------------------------------------
# InMemoryEmbeddingStore
# ---------------------------------------------------------------------------

class InMemoryEmbeddingStore:
	"""Pure-Python in-memory embedding store using cosine similarity.

	Suitable for tests and small catalogs (< 10 000 JTBDs).  The
	pgvector store (E-15) is the production replacement — see
	`framework/python/flowforge-jtbd/README.md` § "Vector store
	selection".

	audit-2026 J-04: instantiation emits a one-shot
	:class:`PerformanceWarning` so production deploys that mistakenly
	wire this in get a flag in their logs / test suite. Set
	``InMemoryEmbeddingStore._warned = True`` (or filter the warning)
	to silence subsequent instantiations within a process.
	"""

	# audit-2026 J-04: process-wide latch so the warning fires once.
	_warned: bool = False

	def __init__(self) -> None:
		import warnings as _warnings

		if not type(self)._warned:
			_warnings.warn(
				"InMemoryEmbeddingStore is intended for tests and small "
				"catalogs (< 10K JTBDs). Use the pgvector store for "
				"production — see flowforge-jtbd/README.md § 'Vector store "
				"selection'.",
				category=PerformanceWarning,
				stacklevel=2,
			)
			type(self)._warned = True
		self._vectors: dict[str, list[float]] = {}
		self._meta: dict[str, dict[str, Any]] = {}

	async def upsert(
		self,
		jtbd_id: str,
		vector: list[float],
		*,
		metadata: dict[str, Any] | None = None,
	) -> None:
		self._vectors[jtbd_id] = vector
		self._meta[jtbd_id] = dict(metadata or {})

	async def search(
		self,
		query_vector: list[float],
		*,
		top_k: int = 10,
		exclude_ids: set[str] | None = None,
	) -> list[tuple[str, float, dict[str, Any]]]:
		"""Cosine similarity search over all stored vectors."""
		exclude = exclude_ids or set()
		scored: list[tuple[str, float]] = []
		for jtbd_id, vec in self._vectors.items():
			if jtbd_id in exclude:
				continue
			sim = _cosine(query_vector, vec)
			scored.append((jtbd_id, sim))

		scored.sort(key=lambda x: -x[1])
		return [
			(jid, sim, dict(self._meta.get(jid, {})))
			for jid, sim in scored[:top_k]
		]

	def add(
		self,
		jtbd_id: str,
		*,
		text: str,
		metadata: dict[str, Any] | None = None,
	) -> None:
		"""Synchronous add (no embedding — stores raw token vector inline).

		For tests only; production code should call
		:meth:`Recommender.index_jtbd` which goes through the provider.
		"""
		tokens = _tokenise(text)
		tf = Counter(tokens)
		total = sum(tf.values()) or 1
		vec = {t: c / total for t, c in tf.items()}
		all_terms = list(vec)
		raw = [vec.get(t, 0.0) for t in all_terms]
		norm = math.sqrt(sum(v * v for v in raw)) or 1.0
		self._vectors[jtbd_id] = [v / norm for v in raw]
		self._meta[jtbd_id] = dict(metadata or {})

	def size(self) -> int:
		return len(self._vectors)


# ---------------------------------------------------------------------------
# Recommender
# ---------------------------------------------------------------------------

class Recommender:
	"""JTBD similarity recommender.

	Indexes JTBDs into an :class:`EmbeddingStore` and answers top-K cosine
	similarity queries.

	Parameters
	----------
	store:
		The embedding store.  Defaults to a fresh
		:class:`InMemoryEmbeddingStore`.
	provider:
		The embedding provider.  Defaults to
		:class:`BagOfWordsEmbeddingProvider`.
	"""

	def __init__(
		self,
		*,
		store: EmbeddingStore | None = None,
		provider: EmbeddingProvider | None = None,
	) -> None:
		self._store: EmbeddingStore = store or InMemoryEmbeddingStore()
		self._provider: EmbeddingProvider = provider or BagOfWordsEmbeddingProvider()

	async def index_jtbd(
		self,
		jtbd_id: str,
		text: str,
		*,
		metadata: dict[str, Any] | None = None,
	) -> None:
		"""Embed *text* and upsert into the store under *jtbd_id*.

		Typically called once per JTBD on library load or on save in the
		editor.  ``text`` should be the concatenation of the JTBD's
		``situation``, ``motivation``, and ``outcome`` fields.
		"""
		vector = await self._provider.embed(text)
		await self._store.upsert(jtbd_id, vector, metadata=metadata)

	async def recommend(
		self,
		query: str,
		*,
		top_k: int = 5,
		exclude_ids: set[str] | None = None,
		domain_filter: str | None = None,
	) -> list[RecommendationResult]:
		"""Return top-K recommendations for *query*.

		Parameters
		----------
		query:
			Free-text description or the text of an existing JTBD.
		top_k:
			Number of results to return (before domain filtering).
		exclude_ids:
			JTBD ids to skip (e.g., the source JTBD when querying by id).
		domain_filter:
			If supplied, only return results whose metadata ``domain``
			matches this value.

		Returns
		-------
		list[RecommendationResult]
			Ranked by similarity descending; at most *top_k* items.
		"""
		assert top_k >= 1, "top_k must be at least 1"
		query_vector = await self._provider.embed(query)
		raw = await self._store.search(
			query_vector,
			top_k=top_k * 4 if domain_filter else top_k,
			exclude_ids=exclude_ids,
		)
		results: list[RecommendationResult] = []
		for jtbd_id, sim, meta in raw:
			domain = meta.get("domain")
			if domain_filter and domain != domain_filter:
				continue
			results.append(
				RecommendationResult(
					jtbd_id=jtbd_id,
					similarity=round(sim, 4),
					domain=domain,
					title=meta.get("title"),
					metadata=meta,
				)
			)
			if len(results) >= top_k:
				break
		return results

	async def recommend_for_jtbd(
		self,
		jtbd_id: str,
		jtbd_text: str,
		*,
		top_k: int = 5,
		domain_filter: str | None = None,
	) -> list[RecommendationResult]:
		"""Recommend JTBDs similar to the given JTBD (excludes itself)."""
		return await self.recommend(
			jtbd_text,
			top_k=top_k,
			exclude_ids={jtbd_id},
			domain_filter=domain_filter,
		)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def build_recommender(
	jtbd_dicts: list[dict[str, Any]],
) -> "Recommender":
	"""Build a fully-indexed :class:`Recommender` from a list of raw JTBD dicts.

	Each dict must contain at least ``id``/``jtbd_id`` and one of
	``situation``/``motivation``/``outcome`` for meaningful ranking.
	Optional ``domain`` and ``title`` keys populate the result metadata.

	This is a sync helper that uses the bag-of-words store directly for
	bootstrap convenience.  For async indexing with a real embedding model,
	use :meth:`Recommender.index_jtbd`.

	.. code-block:: python

		rec = build_recommender([
			{"id": "claim_intake", "domain": "insurance",
			 "situation": "...", "motivation": "...", "outcome": "..."},
			...
		])
		results = asyncio.run(rec.recommend("loss event FNOL"))
	"""
	store = InMemoryEmbeddingStore()
	for spec in jtbd_dicts:
		jtbd_id = str(spec.get("id") or spec.get("jtbd_id") or "unknown")
		parts = [
			str(spec.get("situation") or ""),
			str(spec.get("motivation") or ""),
			str(spec.get("outcome") or ""),
		]
		text = " ".join(p for p in parts if p).strip()
		metadata = {
			"domain": spec.get("domain"),
			"title": spec.get("title"),
		}
		store.add(jtbd_id, text=text or jtbd_id, metadata=metadata)
	return Recommender(store=store)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
	"""Cosine similarity between two vectors (may be of different lengths)."""
	if not a or not b:
		return 0.0
	# Align to shorter length.
	length = min(len(a), len(b))
	dot = sum(a[i] * b[i] for i in range(length))
	# Norms over full vectors to penalise length mismatch.
	norm_a = math.sqrt(sum(v * v for v in a))
	norm_b = math.sqrt(sum(v * v for v in b))
	if norm_a == 0 or norm_b == 0:
		return 0.0
	return max(0.0, min(1.0, dot / (norm_a * norm_b)))


__all__ = [
	"BagOfWordsEmbeddingProvider",
	"EmbeddingProvider",
	"EmbeddingStore",
	"InMemoryEmbeddingStore",
	"RecommendationResult",
	"Recommender",
	"build_recommender",
]
