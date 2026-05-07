# flowforge-jtbd changelog

## 0.1.0 — Unreleased

### E-47 — Intelligence quality (audit 2026)

- **J-02** — `lint/conflicts.py::_emit_pair_issues` pre-buckets writers
  by `(entity, signature)` and iterates only rule-relevant cross
  products. 10K JTBD lints under 5s on the realistic-distribution
  benchmark (was ~50s).
- **J-03** — `BagOfWordsEmbeddingProvider` exposes `fit(corpus)`,
  `transform(text)`, and `freeze()`. After `freeze()`, `embed(text)`
  raises `EmbeddingProviderFrozenError` if `text` introduces a new
  token; `transform(text)` silently drops unknown tokens for
  replay-deterministic vector basis.
- **J-04** — `InMemoryEmbeddingStore` emits a one-shot
  `PerformanceWarning` pointing to the pgvector replacement.
- **J-05** — direct prompt-injection guard test bank (50 prompts,
  ≥45 catch threshold). Residual-risk note at
  `framework/docs/security/nl-injection.md`.
- **J-06** — dead `"HIPAA, GDPR": ()` placeholder removed from
  `_COMPLIANCE_KEYWORDS`. Composite regimes still emit via union of
  single-regime hits.
- **J-07** — `nl_to_jtbd._extract_json` uses
  `json.JSONDecoder.raw_decode` instead of hand-rolled brace counting.
  Strings containing `}` no longer trip the parser.
- **J-08** — `JtbdLockfile.canonical_body()` uses an explicit
  `_BODY_KEYS` allow-list. New top-level fields require an entry —
  silent metadata bleed into `body_hash` is structurally impossible.
- **J-09** — `dsl/spec.py::_semver` backed by
  `packaging.version.Version`. Empty pre-release / build suffixes
  (`"1.0.0-"`, `"1.0.0+"`) and other malformed shapes are rejected.

### [SECURITY] E-38 — Migration RLS DDL hardening (audit 2026)

- **J-01 (P0)** — alembic ``r2_jtbd`` previously spliced module-level
  table-name constants directly into ``op.execute(f"ALTER TABLE {table}
  ...")``. Today's tuples are constants, but the f-string splice was a
  SQL-injection foothold one refactor away. Added:
  - ``_RLS_ALLOWLIST`` ``frozenset`` enumerating every table the RLS DDL
    may touch.
  - ``_assert_known_table()`` validates each spliced name against the
    allow-list **and** an identifier regex (``^[a-z_][a-z0-9_]*$``),
    returning a :class:`sqlalchemy.sql.quoted_name` with ``quote=True``
    so callers see a typed identifier rather than an untrusted ``str``.
  - Both ``_install_rls_if_postgres()`` and ``_drop_rls_if_postgres()``
    validate **all** input names before any SQL is emitted, so a
    monkey-patched malicious tuple (e.g. ``("users; DROP TABLE users; --",)``)
    raises ``ValueError`` with zero side effects.

Regression tests:
- `framework/tests/audit_2026/test_E_38_migration_rls_ddl.py` (6 tests)
- `framework/tests/conformance/test_arch_invariants.py::test_invariant_8_migration_rls_safe`

Existing alembic round-trip tests
(`framework/python/flowforge-jtbd/tests/ci/test_jtbd_alembic_upgrade.py`)
still green. F-4 mitigation (online + reversible + dry-run) covered by
the new ``test_J_01_alembic_dryrun_prod_shape`` test which upgrades and
then immediately downgrades on a SQLite stand-in for the prod-shape DB.

- E-1: canonical spec, lockfile, storage tables.
  - `flowforge_jtbd.dsl.canonical_json` (RFC-8785 byte-stable encoder)
    + `spec_hash` wrapper that emits `sha256:<64 hex>` strings.
  - Pydantic models: `JtbdSpec`, `JtbdBundle`, `JtbdProject`,
    `JtbdShared`, `JtbdField` (mandatory `pii` on sensitive kinds),
    `JtbdEdgeCase`, `JtbdDocReq`, `JtbdApproval`, `JtbdSla`,
    `JtbdNotification`, `JtbdLockfile`, `JtbdLockfilePin`,
    `JtbdComposition`.
  - SQLAlchemy 2.x ORM under `flowforge_jtbd.db`: `JtbdLibrary`,
    `JtbdDomain`, `JtbdSpecRow`, `JtbdCompositionRow`,
    `JtbdCompositionPin`, `JtbdLockfileRow`. Catalogue tier carried by
    nullable `tenant_id`.
  - Alembic revision `r2_jtbd` chained after the engine bundle
    (`r1_initial`). PostgreSQL gets RLS policies via dialect-guarded
    `op.execute`; SQLite test runs skip RLS DDL.
  - Integration test (`tests/integration/python/tests/test_jtbd_storage_e2e.py`)
    exercises alembic upgrade → write bundle + lockfile → reload →
    re-hash, pinning the dsl ↔ db boundary.
- E-4: linter core.
  - Lint-facing spec models (`JtbdLintSpec`, `JtbdBundle`, `ActorRef`,
    `RoleDef`, `StageDecl`).
  - `LifecycleAnalyzer` — completeness analysis against required stages
    with delegation via `audit_handled_by`.
  - `DependencyGraph` — Tarjan SCC cycle detection + Kahn topological
    order.
  - `ActorConsistencyAnalyzer` — capacity-conflict warning, tier
    authority error.
  - `JtbdRule` / `JtbdRulePack` protocols + `RuleRegistry`.
  - `Linter` orchestrator + `LintReport` output format.
- E-7 (production tier): pgvector embedding store + HNSW online-swap.
  - `flowforge_jtbd.ai.pgvector_store.PgVectorEmbeddingStore` —
    `EmbeddingStore` Protocol implementation backed by pgvector with
    `<=>` cosine distance ordering. DDL emitter creates extension /
    schema / table / ivfflat index idempotently. `upsert` uses
    `ON CONFLICT (jtbd_id) DO UPDATE`; `search` selects
    `1 - (vector <=> :vec)` as similarity. Optional dependencies
    (`sqlalchemy`, `asyncpg`, `pgvector`) gated via
    `PgVectorUnavailable`.
  - `flowforge_jtbd.ai.pgvector_store.HnswIndexSwapper` — online
    IVFFlat → HNSW switchover per arch §23.31. Builds the new index
    with `CREATE INDEX CONCURRENTLY` (no read downtime), runs the
    golden-query recall test, drops the old index only when recall ≥
    `min_recall` (default 0.95). `IndexSwapAborted` raised on recall
    miss; both indexes coexist on the failure path so the planner
    keeps using the old one.
  - `dry_run` toggle on `swap()` for staging-environment validation
    runs.
- E-25: Localisation layer.
  - `flowforge_jtbd.i18n.LocaleCatalog` — one language's flat
    `<jtbd_id>.<jcr_path>` → string table with merge / filter helpers.
  - `flowforge_jtbd.i18n.LocaleRegistry` — multi-language registry
    with configurable fallback chain (default `["en"]`); `get_or_key`
    shorthand returns the key itself when unresolved so the editor
    surface never goes blank.
  - `flowforge_jtbd.i18n.keys_for_spec` — derives every translatable
    catalog key from a `JtbdSpec` (Pydantic) or its dict form per the
    arch §23.17 taxonomy: title, situation, motivation, outcome,
    fields.<id>.label/help, edge_cases.<id>.message,
    notifications.<trigger>.subject/body, success_criteria[<i>].
  - `flowforge_jtbd.i18n.validate_catalog` — surfaces
    `unknown_path` errors (catalog points at a field no spec
    has) and `missing_translation` warnings (spec field not covered
    by the catalog).
  - `flowforge_jtbd.i18n.load_catalog_from_path` /
    `load_catalog_from_dir` — read `i18n/<lang>.json` files from
    library packs.
- E-15: DomainInferer.
  - `flowforge_jtbd.ai.domain_inference` — `DomainInferer` wraps the
    E-7 `Recommender` to suggest starter library JTBDs for a free-text
    description. Two modes:
      * Auto — keyword catalogue covers the 30 domains in §12; the
        inferer detects matching domains and queries the recommender
        once per domain, merging results in similarity order.
      * Targeted — caller pins one or more domains and skips
        auto-detection.
  - `DomainHit` records the matched keywords and a confidence count
    (one per matched phrase).
  - `DomainInferenceResult` carries detected hits, queried domains,
    and the dedup'd merged recommendation list.
- E-14: LlmProvider port + NL→JTBD generator.
  - `flowforge_jtbd.ports.llm` — `LlmProvider` Protocol
    (generate / embed / stream_chat) + `LlmProviderError`.
  - `flowforge_jtbd.ports.llm_claude` — `LlmProviderClaude` default
    using the official Anthropic SDK; lazy import so non-Claude hosts
    do not pay the dep cost.
  - `flowforge_jtbd.ai.nl_to_jtbd` — `NlToJtbdGenerator` pipeline:
    sanitise input → build prompt with schema + bundle context +
    examples + compliance hints → LLM call → JSON extraction
    (markdown-fence tolerant) → `JtbdSpec.model_validate` → one retry
    on validation failure with errors fed back.
  - Direct prompt-injection guard strips known role markers
    (`<|im_start|>`, `[INST]`, …); indirect guard rejects descriptions
    that match instruction-override patterns ("ignore previous
    instructions", "role: system", …) before any LLM call.
