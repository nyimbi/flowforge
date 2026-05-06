"""PgVectorEmbeddingStore + HnswIndexSwapper unit tests (E-7).

These tests do not touch a real Postgres. They exercise the SQL
emitter and the algorithm logic via a fake AsyncSession that records
every executed statement and returns canned results. An integration
test gated on ``FLOWFORGE_PG_DSN`` exists in
``tests/integration/test_ai_pgvector_e2e.py`` (out of scope for this
unit run).
"""

from __future__ import annotations

import pytest

from flowforge_jtbd.ai.pgvector_store import (
	GoldenQuery,
	HnswIndexSwapper,
	IndexSwapAborted,
	PgVectorEmbeddingStore,
	SwapReport,
	TableSpec,
	_format_metadata,
	_format_vector,
)


# ---------------------------------------------------------------------------
# Fake async session
# ---------------------------------------------------------------------------


class _FakeResult:
	def __init__(self, rows: list[tuple]) -> None:
		self._rows = rows

	def fetchall(self) -> list[tuple]:
		return list(self._rows)


class _FakeSession:
	"""Records every (sql, params) pair executed and returns canned rows.

	A fresh instance is used per test; ``responses`` queues canned
	``_FakeResult`` payloads keyed by the predicate the SQL must
	match. The default behaviour returns an empty result.
	"""

	def __init__(self) -> None:
		self.calls: list[tuple[str, dict | None]] = []
		self.commits = 0
		self.responses: list[tuple[Callable[[str], bool], _FakeResult]] = []  # type: ignore[name-defined]

	async def execute(self, sql, params=None):  # type: ignore[no-untyped-def]
		text = str(getattr(sql, "text", sql)).lower().strip()
		self.calls.append((text, dict(params) if params else None))
		for predicate, result in self.responses:
			if predicate(text):
				return result
		return _FakeResult([])

	async def commit(self) -> None:
		self.commits += 1

	async def rollback(self) -> None:
		self.commits -= 1


# Late binding for the type hint inside _FakeSession.
from typing import Callable  # noqa: E402


def _factory(session: _FakeSession):
	return lambda: session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(*, dim: int = 3) -> TableSpec:
	return TableSpec(dim=dim)


# ---------------------------------------------------------------------------
# DDL emitter
# ---------------------------------------------------------------------------


def test_table_spec_qualifies_name() -> None:
	s = _spec()
	assert s.qualified == "flowforge.jtbd_embeddings"


def test_create_table_sql_uses_dim() -> None:
	sql = _spec(dim=384).create_table_sql()
	assert "vector(384)" in sql
	assert "jtbd_id text primary key" in sql
	assert "metadata jsonb" in sql


def test_create_ivfflat_index_sql_carries_lists() -> None:
	s = TableSpec(dim=4, ivfflat_lists=200)
	assert "with (lists = 200)" in s.create_ivfflat_index_sql()
	assert "vector_cosine_ops" in s.create_ivfflat_index_sql()


def test_create_hnsw_index_sql_carries_m_and_ef() -> None:
	sql = _spec().create_hnsw_index_sql(m=12, ef_construction=128)
	assert "using hnsw" in sql
	assert "with (m = 12, ef_construction = 128)" in sql
	assert "concurrently" in sql


def test_create_hnsw_index_sql_can_omit_concurrently() -> None:
	sql = _spec().create_hnsw_index_sql(concurrently=False)
	assert "concurrently" not in sql


def test_drop_index_sql_qualifies_schema() -> None:
	assert "drop index if exists flowforge.foo;" == _spec().drop_index_sql("foo")


def test_drop_index_sql_rejects_empty_name() -> None:
	with pytest.raises(AssertionError):
		_spec().drop_index_sql("")


def test_table_spec_validates_dim() -> None:
	with pytest.raises(AssertionError):
		TableSpec(dim=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_format_vector_renders_pgvector_literal() -> None:
	assert _format_vector([1.0, 2.5, -3.25]) == "[1,2.5,-3.25]"


def test_format_metadata_serialises_sorted_json() -> None:
	out = _format_metadata({"b": 2, "a": 1})
	assert out == '{"a":1,"b":2}'


def test_format_metadata_handles_none() -> None:
	assert _format_metadata(None) == "{}"


# ---------------------------------------------------------------------------
# Store init / upsert / search
# ---------------------------------------------------------------------------


async def test_initialize_emits_extension_schema_table_index() -> None:
	session = _FakeSession()
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	await store.initialize()
	statements = " ".join(call[0] for call in session.calls)
	assert "create extension if not exists vector" in statements
	assert "create schema if not exists flowforge" in statements
	assert "create table if not exists flowforge.jtbd_embeddings" in statements
	assert "using ivfflat" in statements
	assert session.commits >= 1


async def test_initialize_can_skip_extension() -> None:
	session = _FakeSession()
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	await store.initialize(with_extension=False)
	statements = " ".join(call[0] for call in session.calls)
	assert "create extension" not in statements


async def test_upsert_emits_on_conflict_clause() -> None:
	session = _FakeSession()
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	await store.upsert("a", [0.1, 0.2, 0.3], metadata={"domain": "banking"})
	last_sql, params = session.calls[-1]
	assert "insert into flowforge.jtbd_embeddings" in last_sql
	assert "on conflict (jtbd_id) do update" in last_sql
	assert params is not None
	assert params["jtbd_id"] == "a"
	assert params["vec"] == "[0.1,0.2,0.3]"
	assert '"domain":"banking"' in params["metadata"]


async def test_upsert_rejects_dim_mismatch() -> None:
	session = _FakeSession()
	store = PgVectorEmbeddingStore(spec=_spec(dim=3), session_factory=_factory(session))
	with pytest.raises(AssertionError):
		await store.upsert("a", [0.1, 0.2])


async def test_search_orders_by_cosine_distance() -> None:
	session = _FakeSession()
	session.responses.append((
		lambda sql: "from flowforge.jtbd_embeddings" in sql,
		_FakeResult([
			("a", 0.95, {"domain": "banking"}),
			("b", 0.80, {"domain": "insurance"}),
		]),
	))
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	results = await store.search([0.1, 0.2, 0.3], top_k=2)
	assert results == [
		("a", 0.95, {"domain": "banking"}),
		("b", 0.80, {"domain": "insurance"}),
	]
	last_sql, params = session.calls[-1]
	assert "order by vector <=> :vec asc" in last_sql
	assert "1 - (vector <=> :vec)" in last_sql
	assert params is not None
	assert params["limit"] == 2


async def test_search_excludes_ids() -> None:
	session = _FakeSession()
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	await store.search([0.1, 0.2, 0.3], top_k=3, exclude_ids={"a", "b"})
	last_sql, params = session.calls[-1]
	assert "where jtbd_id not in" in last_sql
	assert params is not None
	# Excluded ids land under x0/x1 keys in alphabetical order.
	assert params["x0"] == "a"
	assert params["x1"] == "b"


async def test_list_indexes_returns_index_names() -> None:
	session = _FakeSession()
	session.responses.append((
		lambda sql: "from pg_indexes" in sql,
		_FakeResult([("jtbd_embeddings_pkey",), ("jtbd_embeddings_ivfflat_idx",)]),
	))
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	out = await store.list_indexes()
	assert out == ["jtbd_embeddings_pkey", "jtbd_embeddings_ivfflat_idx"]


async def test_drop_index_emits_drop_sql() -> None:
	session = _FakeSession()
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	await store.drop_index("foo_idx")
	last_sql, _ = session.calls[-1]
	assert "drop index if exists flowforge.foo_idx;" == last_sql


# ---------------------------------------------------------------------------
# HnswIndexSwapper
# ---------------------------------------------------------------------------


def _golden(*pairs: tuple[tuple[float, ...], tuple[str, ...]]) -> tuple[GoldenQuery, ...]:
	return tuple(GoldenQuery(vector=vec, expected=exp) for vec, exp in pairs)


async def test_swap_happy_path_drops_old_index() -> None:
	session = _FakeSession()
	# Every search returns the expected jtbd_ids → recall = 1.
	session.responses.append((
		lambda sql: "order by vector <=> :vec asc" in sql,
		_FakeResult([("a", 0.99, {})]),
	))
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	swapper = HnswIndexSwapper(
		store=store,
		golden=_golden(((0.1, 0.2, 0.3), ("a",))),
	)
	report = await swapper.switch()
	assert isinstance(report, SwapReport)
	assert report.recall == 1.0
	assert report.old_index_dropped == "jtbd_embeddings_ivfflat_idx"
	statements = [call[0] for call in session.calls]
	assert any("using hnsw" in s for s in statements)
	assert any("drop index if exists flowforge.jtbd_embeddings_ivfflat_idx" in s for s in statements)


async def test_swap_dry_run_skips_drop() -> None:
	session = _FakeSession()
	session.responses.append((
		lambda sql: "order by vector <=> :vec asc" in sql,
		_FakeResult([("a", 0.99, {})]),
	))
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	swapper = HnswIndexSwapper(
		store=store,
		golden=_golden(((0.1, 0.2, 0.3), ("a",))),
	)
	report = await swapper.switch(dry_run=True)
	assert report.dry_run is True
	assert report.old_index_dropped is None
	statements = [call[0] for call in session.calls]
	assert any("using hnsw" in s for s in statements)
	assert all("drop index" not in s for s in statements)


async def test_swap_aborts_when_recall_below_threshold() -> None:
	session = _FakeSession()
	# Search returns a *different* jtbd_id → recall = 0.
	session.responses.append((
		lambda sql: "order by vector <=> :vec asc" in sql,
		_FakeResult([("wrong", 0.99, {})]),
	))
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	swapper = HnswIndexSwapper(
		store=store,
		golden=_golden(((0.1, 0.2, 0.3), ("a",))),
		min_recall=0.95,
	)
	with pytest.raises(IndexSwapAborted) as info:
		await swapper.switch()
	assert "below threshold" in str(info.value)
	# Old index NOT dropped.
	statements = [call[0] for call in session.calls]
	assert all("drop index" not in s for s in statements)


async def test_measure_recall_partial_overlap() -> None:
	# Two queries: first has exact match (recall=1), second has 1/2 overlap.
	session = _FakeSession()
	calls_made = {"n": 0}

	def _result(sql: str) -> bool:
		return "order by vector <=> :vec asc" in sql

	# Two responses, each used once — round-robin via list-pop.
	responses_queue = [
		_FakeResult([("a", 0.99, {})]),
		_FakeResult([("c", 0.85, {}), ("d", 0.83, {})]),
	]

	async def execute(sql, params=None):  # type: ignore[no-untyped-def]
		text = str(getattr(sql, "text", sql)).lower().strip()
		session.calls.append((text, dict(params) if params else None))
		if "order by vector <=> :vec asc" in text:
			calls_made["n"] += 1
			return responses_queue.pop(0) if responses_queue else _FakeResult([])
		return _FakeResult([])

	session.execute = execute  # type: ignore[method-assign]

	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(session))
	swapper = HnswIndexSwapper(
		store=store,
		golden=_golden(
			((0.1, 0.2, 0.3), ("a",)),         # full match
			((0.4, 0.5, 0.6), ("c", "x")),     # only c retrieved (1/2)
		),
	)
	recall = await swapper.measure_recall()
	# (1.0 + 0.5) / 2 == 0.75
	assert recall == pytest.approx(0.75)


def test_swapper_validates_inputs() -> None:
	store = PgVectorEmbeddingStore(spec=_spec(), session_factory=_factory(_FakeSession()))
	with pytest.raises(AssertionError):
		HnswIndexSwapper(store=store, golden=())
	with pytest.raises(AssertionError):
		HnswIndexSwapper(
			store=store,
			golden=_golden(((0.1, 0.2, 0.3), ("a",))),
			min_recall=0,
		)
	with pytest.raises(AssertionError):
		HnswIndexSwapper(
			store=store,
			golden=_golden(((0.1, 0.2, 0.3), ("a",))),
			min_recall=1.5,
		)
