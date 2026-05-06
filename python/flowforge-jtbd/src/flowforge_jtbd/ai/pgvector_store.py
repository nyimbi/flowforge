"""pgvector-backed :class:`EmbeddingStore` + HNSW online-swap (E-7).

Per ``framework/docs/jtbd-editor-arch.md`` §13.7 and §23.31. The
:class:`InMemoryEmbeddingStore` shipped earlier in E-7 stays the
default for tests and small libraries; this module is the production
adapter that hosts wire up when their JTBD library outgrows a Python
dict.

DDL (mirrors arch §13.7 + §23.22):

```sql
create extension if not exists vector;

create table flowforge.jtbd_embeddings (
    jtbd_id    text primary key,
    vector     vector(N) not null,
    metadata   jsonb not null default '{}',
    updated_at timestamptz not null default now()
);

-- Default index — fine up to ~10k rows.
create index jtbd_embeddings_ivfflat_idx
  on flowforge.jtbd_embeddings using ivfflat (vector vector_cosine_ops)
  with (lists = 100);
```

Online HNSW switch (per §23.31): build the new index with
``CREATE INDEX CONCURRENTLY``, validate recall ≥ 0.95 on a golden
query set, drop the old index. The cutover causes no failed reads —
both indexes coexist while the recall test runs.

Lazy SQL imports
----------------
``sqlalchemy[asyncio]`` is a hard dep of the package, but the pgvector
extension and the ``asyncpg`` driver are not. Hosts opt in with the
``flowforge-jtbd[postgres]`` extra. Construction validates that
prerequisites are present and raises :class:`PgVectorUnavailable` with
a remediation hint when they are not.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Sequence


_log = logging.getLogger(__name__)


DEFAULT_SCHEMA = "flowforge"
DEFAULT_TABLE = "jtbd_embeddings"
DEFAULT_IVFFLAT_INDEX = "jtbd_embeddings_ivfflat_idx"
DEFAULT_HNSW_INDEX = "jtbd_embeddings_hnsw_idx"


class PgVectorUnavailable(RuntimeError):
	"""Raised when SQLAlchemy / asyncpg / pgvector cannot be imported."""


# ---------------------------------------------------------------------------
# Session factory protocol
# ---------------------------------------------------------------------------


# A session factory is anything that returns an async context manager
# yielding an object with ``execute(sql, params)`` and
# ``commit() / rollback()``. The narrow shape lets tests pass a fake
# without bringing real SQLAlchemy.
SessionFactory = Callable[[], "AsyncSessionLike"]


class AsyncSessionLike:
	"""Type hint for the subset of AsyncSession we use.

	Tests pass a fake conforming to this shape; production wires
	:class:`sqlalchemy.ext.asyncio.AsyncSession`.
	"""

	async def execute(self, sql: Any, params: Any | None = None) -> Any: ...
	async def commit(self) -> None: ...
	async def rollback(self) -> None: ...


# ---------------------------------------------------------------------------
# DDL emitter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableSpec:
	"""DDL parameters for the ``jtbd_embeddings`` table."""

	dim: int
	schema: str = DEFAULT_SCHEMA
	table: str = DEFAULT_TABLE
	ivfflat_lists: int = 100

	def __post_init__(self) -> None:
		assert self.dim >= 1, "vector dim must be ≥ 1"
		assert self.schema, "schema must be non-empty"
		assert self.table, "table must be non-empty"
		assert self.ivfflat_lists >= 1, "ivfflat lists must be ≥ 1"

	@property
	def qualified(self) -> str:
		return f"{self.schema}.{self.table}"

	def create_extension_sql(self) -> str:
		return "create extension if not exists vector;"

	def create_schema_sql(self) -> str:
		return f"create schema if not exists {self.schema};"

	def create_table_sql(self) -> str:
		return (
			f"create table if not exists {self.qualified} ("
			f" jtbd_id text primary key,"
			f" vector vector({self.dim}) not null,"
			f" metadata jsonb not null default '{{}}'::jsonb,"
			f" updated_at timestamptz not null default now()"
			f");"
		)

	def create_ivfflat_index_sql(
		self,
		*,
		index_name: str = DEFAULT_IVFFLAT_INDEX,
	) -> str:
		return (
			f"create index if not exists {index_name}"
			f" on {self.qualified}"
			f" using ivfflat (vector vector_cosine_ops)"
			f" with (lists = {self.ivfflat_lists});"
		)

	def create_hnsw_index_sql(
		self,
		*,
		index_name: str = DEFAULT_HNSW_INDEX,
		m: int = 16,
		ef_construction: int = 64,
		concurrently: bool = True,
	) -> str:
		concurrent = "concurrently " if concurrently else ""
		return (
			f"create index {concurrent}if not exists {index_name}"
			f" on {self.qualified}"
			f" using hnsw (vector vector_cosine_ops)"
			f" with (m = {m}, ef_construction = {ef_construction});"
		)

	def drop_index_sql(self, index_name: str) -> str:
		assert index_name, "index_name must be non-empty"
		return f"drop index if exists {self.schema}.{index_name};"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


@dataclass
class PgVectorEmbeddingStore:
	"""pgvector-backed :class:`EmbeddingStore`.

	Construction does not touch the database. Call :meth:`initialize`
	once at startup to create the schema / extension / table /
	ivfflat index.

	The class implements the same ``upsert`` / ``search`` Protocol as
	:class:`flowforge_jtbd.ai.recommender.InMemoryEmbeddingStore` so
	the recommender swaps adapters without touching its own logic.
	"""

	spec: TableSpec
	session_factory: SessionFactory

	@classmethod
	def from_extras(cls, *, dim: int, session_factory: SessionFactory,
					schema: str = DEFAULT_SCHEMA, table: str = DEFAULT_TABLE,
					) -> "PgVectorEmbeddingStore":
		"""Construct after verifying optional dependencies are present."""
		_require_pgvector_extras()
		return cls(
			spec=TableSpec(dim=dim, schema=schema, table=table),
			session_factory=session_factory,
		)

	async def initialize(self, *, with_extension: bool = True) -> None:
		"""Create extension + table + default ivfflat index if missing.

		``with_extension=False`` skips ``CREATE EXTENSION vector`` for
		hosts that gate extension creation behind a privileged migration
		account.
		"""
		statements: list[str] = []
		if with_extension:
			statements.append(self.spec.create_extension_sql())
		statements.append(self.spec.create_schema_sql())
		statements.append(self.spec.create_table_sql())
		statements.append(self.spec.create_ivfflat_index_sql())
		await self._execute_many(statements)

	async def upsert(
		self,
		jtbd_id: str,
		vector: Sequence[float],
		*,
		metadata: dict[str, Any] | None = None,
	) -> None:
		assert jtbd_id, "jtbd_id must be non-empty"
		assert len(vector) == self.spec.dim, (
			f"vector dim mismatch: expected {self.spec.dim}, got {len(vector)}"
		)
		from sqlalchemy import text  # type: ignore[import-not-found]

		sql = text(
			f"insert into {self.spec.qualified}"
			f" (jtbd_id, vector, metadata, updated_at)"
			f" values (:jtbd_id, :vec, cast(:metadata as jsonb), now())"
			f" on conflict (jtbd_id) do update set"
			f" vector = excluded.vector,"
			f" metadata = excluded.metadata,"
			f" updated_at = excluded.updated_at;"
		)
		params = {
			"jtbd_id": jtbd_id,
			"vec": _format_vector(vector),
			"metadata": _format_metadata(metadata),
		}
		async with self._scope() as session:
			await session.execute(sql, params)
			await session.commit()

	async def search(
		self,
		query_vector: Sequence[float],
		*,
		top_k: int = 10,
		exclude_ids: set[str] | None = None,
	) -> list[tuple[str, float, dict[str, Any]]]:
		assert len(query_vector) == self.spec.dim, (
			f"query vector dim mismatch: expected {self.spec.dim}, "
			f"got {len(query_vector)}"
		)
		assert top_k >= 1, "top_k must be ≥ 1"
		from sqlalchemy import text  # type: ignore[import-not-found]

		# `<=>` is the pgvector cosine distance operator. Similarity =
		# 1 - distance. We sort by distance ASC and let the caller cap.
		exclude_clause = ""
		params: dict[str, Any] = {
			"vec": _format_vector(query_vector),
			"limit": top_k,
		}
		if exclude_ids:
			placeholders = ", ".join(f":x{i}" for i in range(len(exclude_ids)))
			exclude_clause = f" where jtbd_id not in ({placeholders})"
			for i, jid in enumerate(sorted(exclude_ids)):
				params[f"x{i}"] = jid

		sql = text(
			f"select jtbd_id, 1 - (vector <=> :vec) as similarity, metadata"
			f" from {self.spec.qualified}"
			f"{exclude_clause}"
			f" order by vector <=> :vec asc"
			f" limit :limit;"
		)

		async with self._scope() as session:
			result = await session.execute(sql, params)
			rows = result.fetchall() if not _is_awaitable(result.fetchall) else await result.fetchall()  # type: ignore[truthy-function]

		out: list[tuple[str, float, dict[str, Any]]] = []
		for row in rows:
			jtbd_id, similarity, metadata = _row_tuple(row)
			out.append((jtbd_id, float(similarity), dict(metadata or {})))
		return out

	async def list_indexes(self) -> list[str]:
		from sqlalchemy import text  # type: ignore[import-not-found]

		sql = text(
			"select indexname from pg_indexes"
			" where schemaname = :schema and tablename = :table"
			" order by indexname;"
		)
		params = {"schema": self.spec.schema, "table": self.spec.table}
		async with self._scope() as session:
			result = await session.execute(sql, params)
			rows = result.fetchall() if not _is_awaitable(result.fetchall) else await result.fetchall()  # type: ignore[truthy-function]
		return [row[0] for row in rows]

	async def drop_index(self, index_name: str) -> None:
		await self._execute_many([self.spec.drop_index_sql(index_name)])

	# ------------------------------------------------------------------
	# Internal
	# ------------------------------------------------------------------

	async def _execute_many(self, statements: list[str]) -> None:
		from sqlalchemy import text  # type: ignore[import-not-found]

		async with self._scope() as session:
			for stmt in statements:
				await session.execute(text(stmt))
			await session.commit()

	@asynccontextmanager
	async def _scope(self) -> AsyncIterator[Any]:
		ctx: Any = self.session_factory()
		# Support both ``async with`` context managers and bare
		# session objects (helpful in tests).
		aenter = getattr(ctx, "__aenter__", None)
		aexit = getattr(ctx, "__aexit__", None)
		if aenter is not None and aexit is not None:
			session = await aenter()
			try:
				yield session
			finally:
				await aexit(None, None, None)
		else:
			yield ctx


# ---------------------------------------------------------------------------
# HNSW online-swap algorithm (§23.31)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenQuery:
	"""One golden-set query: vector + the expected top-K jtbd_ids."""

	vector: tuple[float, ...]
	expected: tuple[str, ...]


@dataclass(frozen=True)
class SwapReport:
	"""Outcome of an HNSW switch attempt."""

	new_index: str
	old_index_dropped: str | None
	recall: float
	queries_tested: int
	dry_run: bool


class IndexSwapAborted(RuntimeError):
	"""Raised when recall does not clear the configured threshold."""


@dataclass
class HnswIndexSwapper:
	"""Online IVFFlat → HNSW switchover per arch §23.31.

	The algorithm:

	1. Build the new HNSW index with ``CREATE INDEX CONCURRENTLY`` —
	   reads continue against the old IVFFlat index throughout.
	2. Run the recall test: re-execute every query in the golden set
	   and compare top-K against ``expected``. Recall = avg overlap
	   ratio across the set.
	3. If recall < ``min_recall``, abort and leave both indexes in
	   place. The query planner will keep using the old index.
	4. On pass, drop the IVFFlat index. The HNSW index now serves all
	   reads.

	``dry_run=True`` runs steps 1 + 2 but skips the drop, useful for
	staging-environment validation runs.
	"""

	store: PgVectorEmbeddingStore
	golden: tuple[GoldenQuery, ...]
	min_recall: float = 0.95
	hnsw_index_name: str = DEFAULT_HNSW_INDEX
	old_index_name: str = DEFAULT_IVFFLAT_INDEX
	hnsw_m: int = 16
	hnsw_ef_construction: int = 64

	def __post_init__(self) -> None:
		assert self.golden, "golden query set must be non-empty"
		assert 0 < self.min_recall <= 1, "min_recall must be in (0, 1]"

	async def build_hnsw(self) -> None:
		"""Create the HNSW index alongside the existing IVFFlat one.

		Uses ``CREATE INDEX CONCURRENTLY`` so reads continue while the
		index is being built. Postgres requires this to run outside a
		transaction; the caller is responsible for setting the session
		isolation level appropriately.
		"""
		sql = self.store.spec.create_hnsw_index_sql(
			index_name=self.hnsw_index_name,
			m=self.hnsw_m,
			ef_construction=self.hnsw_ef_construction,
			concurrently=True,
		)
		await self.store._execute_many([sql])

	async def measure_recall(self, *, top_k: int | None = None) -> float:
		"""Run every golden query and return the average top-K recall."""
		recalls: list[float] = []
		k = top_k or max(len(q.expected) for q in self.golden)
		for query in self.golden:
			results = await self.store.search(query.vector, top_k=k)
			retrieved = {jtbd_id for jtbd_id, _, _ in results}
			expected = set(query.expected)
			if not expected:
				continue
			recalls.append(len(retrieved & expected) / len(expected))
		return sum(recalls) / len(recalls) if recalls else 0.0

	async def switch(self, *, dry_run: bool = False) -> SwapReport:
		await self.build_hnsw()
		recall = await self.measure_recall()
		if recall < self.min_recall:
			raise IndexSwapAborted(
				f"recall {recall:.3f} below threshold "
				f"{self.min_recall:.3f}; leaving both indexes in place "
				f"(new HNSW index {self.hnsw_index_name!r} preserved "
				f"for inspection)",
			)
		dropped: str | None = None
		if not dry_run:
			await self.store.drop_index(self.old_index_name)
			dropped = self.old_index_name
		return SwapReport(
			new_index=self.hnsw_index_name,
			old_index_dropped=dropped,
			recall=recall,
			queries_tested=len(self.golden),
			dry_run=dry_run,
		)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_vector(vector: Sequence[float]) -> str:
	"""Render *vector* in pgvector's text format (``[v1,v2,...]``)."""
	parts = ",".join(f"{float(v):.7g}" for v in vector)
	return f"[{parts}]"


def _format_metadata(metadata: dict[str, Any] | None) -> str:
	import json

	return json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))


def _row_tuple(row: Any) -> tuple[Any, Any, Any]:
	"""Coerce a SQLAlchemy Row / tuple / dict / mapping to a 3-tuple."""
	if isinstance(row, dict):
		return row["jtbd_id"], row["similarity"], row.get("metadata")
	# Row supports tuple unpack and __getitem__ by name; tuple form is
	# safest for our duck-typed fakes.
	if hasattr(row, "_mapping"):
		mapping = row._mapping
		return mapping["jtbd_id"], mapping["similarity"], mapping.get("metadata")
	return row[0], row[1], row[2] if len(row) > 2 else None


def _is_awaitable(obj: Any) -> bool:
	# fetchall() may be sync (most drivers) or async (some). Detect at
	# call time. We type-narrow at the call site via this helper.
	return isinstance(obj, Awaitable) or callable(getattr(obj, "__await__", None))


def _require_pgvector_extras() -> None:
	"""Validate that SQLAlchemy + asyncpg + pgvector packages are importable."""
	missing: list[str] = []
	try:
		import sqlalchemy  # noqa: F401
	except ModuleNotFoundError:
		missing.append("sqlalchemy")
	try:
		import asyncpg  # noqa: F401
	except ModuleNotFoundError:
		missing.append("asyncpg")
	try:
		import pgvector  # noqa: F401
	except ModuleNotFoundError:
		# pgvector-python is not strictly required for our adapter
		# (we use raw SQL for the vector ops) but we surface it as a
		# soft hint so hosts get clean import errors elsewhere.
		_log.debug("pgvector-python not installed; raw-SQL path active")
	if missing:
		raise PgVectorUnavailable(
			"PgVectorEmbeddingStore requires "
			f"{', '.join(missing)}. Install via "
			"`pip install flowforge-jtbd[postgres]`.",
		)


__all__ = [
	"DEFAULT_HNSW_INDEX",
	"DEFAULT_IVFFLAT_INDEX",
	"DEFAULT_SCHEMA",
	"DEFAULT_TABLE",
	"GoldenQuery",
	"HnswIndexSwapper",
	"IndexSwapAborted",
	"PgVectorEmbeddingStore",
	"PgVectorUnavailable",
	"SwapReport",
	"TableSpec",
]
