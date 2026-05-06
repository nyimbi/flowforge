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
