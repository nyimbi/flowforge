# flowforge-jtbd

JTBD (Jobs-To-Be-Done) spec model, lockfile, storage tables, and linter
core for the flowforge framework. Implements tickets **E-1** (canonical
spec + lockfile + storage) and **E-4** (linter core) of the JTBD Editor
evolution plan (see `framework/docs/flowforge-evolution.md` §3-§4 and
`framework/docs/jtbd-editor-arch.md` §13).

## E-1 — canonical spec + lockfile + storage

- `flowforge_jtbd.dsl.canonical_json(obj) -> bytes` and
  `flowforge_jtbd.dsl.spec_hash(obj) -> str` — RFC-8785-aligned canonical
  JSON encoder + sha256 wrapper that anchors content addressing. Two
  CLIs hashing the same logical bundle MUST produce byte-identical
  output; the `tests/ci/test_canonical_json.py` fixture matrix pins
  the property.
- `flowforge_jtbd.dsl.JtbdSpec`, `JtbdBundle`, `JtbdProject`,
  `JtbdShared`, plus the supporting `JtbdField`, `JtbdEdgeCase`,
  `JtbdDocReq`, `JtbdApproval`, `JtbdSla`, `JtbdNotification` shapes —
  pydantic v2 models with `extra='forbid'`. `JtbdField` enforces
  mandatory `pii` on sensitive kinds at validation time.
- `flowforge_jtbd.dsl.JtbdLockfile`, `JtbdLockfilePin`,
  `JtbdComposition` — frozen pin table for a composition. `body_hash`
  computes through the same canonical-JSON helper as `spec_hash`;
  `generated_at` / `generated_by` are metadata, not part of the body.
- `flowforge_jtbd.db` — SQLAlchemy 2.x ORM for `jtbd_libraries`,
  `jtbd_domains`, `jtbd_specs`, `jtbd_compositions`,
  `jtbd_compositions_pins`, `jtbd_lockfiles`. Catalogue-tier rows
  (`tenant_id IS NULL`) cohabit with tenant-scoped rows; RLS isolates
  on the `app.tenant_id` GUC.
- `flowforge_jtbd.db.alembic_bundle` — Alembic revision `r2_jtbd`
  chained after `flowforge_sqlalchemy`'s `r1_initial`. Dialect-aware:
  PostgreSQL gets `JSONB` + RLS policies; SQLite (test harness) skips
  RLS DDL.

## E-4 — linter core

- `flowforge_jtbd.spec` — lint-facing Pydantic models (`JtbdLintSpec`,
  lint-side `JtbdBundle`, `ActorRef`, `RoleDef`, `StageDecl`). Distinct
  from `flowforge_jtbd.dsl.JtbdSpec` (E-1's canonical model); the lint
  surface keeps `extra='allow'` so it rides forward through schema
  churn while the canonical layer rejects unknown keys.
- `flowforge_jtbd.lint.lifecycle` — `LifecycleAnalyzer`: completeness
  analysis. Required default stages: `discover`, `execute`,
  `error_handle`, `report`, `audit`. `undo` is optional. Per-domain
  rule packs may add gating (e.g., `undo` for `compliance: [SOX]`).
- `flowforge_jtbd.lint.dependencies` — `DependencyGraph`: builds a
  directed graph from `requires` edges, detects cycles via Tarjan's
  SCC, and emits a topological order.
- `flowforge_jtbd.lint.actors` — `ActorConsistencyAnalyzer`: detects
  the same role acting in conflicting capacities (creator + approver
  on one entity → warning) and insufficient authority tier (spec
  requires tier N, role default-tier < N → error).
- `flowforge_jtbd.lint.registry` — `JtbdRule` / `JtbdRulePack`
  protocols and a `RuleRegistry` for pluggable per-domain rules.
- `flowforge_jtbd.lint.linter` — top-level `Linter` orchestrator that
  runs every analyzer + every registered rule and aggregates results
  into a `LintReport` (see `flowforge_jtbd.lint.results`).

## Out of scope

- Conflict solver (timing × data × consistency, Z3 / pairs fallback)
  ships in **E-5**.
- Glossary / ontology cross-bundle conflict detection ships in **E-8**.
- Domain rule packs (banking, healthcare, …) ship in **E-5** /
  **E-17**.
- The `flowforge jtbd lint` CLI subcommand ships in **E-9** alongside
  pre-commit and GitHub Actions templates.

## Quick example

```python
from flowforge_jtbd.lint import Linter
from flowforge_jtbd.spec import (
	ActorRef, JtbdBundle, JtbdLintSpec, RoleDef, StageDecl,
)

bundle = JtbdBundle(
	bundle_id="acme-banking",
	jtbds=[
		JtbdLintSpec(
			jtbd_id="account_open",
			version="1.0.0",
			actor=ActorRef(role="banker", tier=2),
			requires=["party_kyc"],
			stages=[
				StageDecl(name="discover"),
				StageDecl(name="execute"),
				StageDecl(name="error_handle"),
				StageDecl(name="report"),
				StageDecl(name="audit"),
			],
		),
		JtbdLintSpec(
			jtbd_id="party_kyc",
			version="1.0.0",
			actor=ActorRef(role="clerk", tier=1),
			stages=[
				StageDecl(name="discover"),
				StageDecl(name="execute"),
				StageDecl(name="error_handle"),
				StageDecl(name="report"),
				StageDecl(name="audit"),
			],
		),
	],
	shared_roles={
		"banker": RoleDef(name="banker", default_tier=2),
		"clerk": RoleDef(name="clerk", default_tier=1),
	},
)

report = Linter().lint(bundle)
assert report.ok
```

## Tests

```
uv run pytest -vxs framework/python/flowforge-jtbd/tests
```
