# flowforge-jtbd

JTBD (Jobs-To-Be-Done) spec model and linter core for the flowforge
framework. Implements ticket **E-4** of the JTBD Editor evolution plan
(see `framework/docs/flowforge-evolution.md` §4 and
`framework/docs/jtbd-editor-arch.md` §2).

## What's in here

- `flowforge_jtbd.spec` — lint-facing Pydantic models (`JtbdLintSpec`,
  `JtbdBundle`, `ActorRef`, `RoleDef`, `StageDecl`). The full
  `JtbdSpec` schema lives elsewhere (E-1); this module defines the
  subset the linter needs and acts as a stable contract for adapters.
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
