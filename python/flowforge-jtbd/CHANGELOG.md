# flowforge-jtbd changelog

## 0.1.0 — Unreleased

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
