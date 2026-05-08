# flowforge-jtbd

JTBD canonical spec models, lockfile, SQLAlchemy storage tables, and linter core for the flowforge framework.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-jtbd
```

## What it does

`flowforge-jtbd` covers two evolution tickets. E-1 delivers the canonical wire format: `JtbdSpec` and `JtbdBundle` pydantic v2 models with `extra='forbid'`, an RFC-8785-aligned canonical JSON encoder, a `spec_hash()` helper, and a lockfile (`JtbdLockfile`, `JtbdLockfilePin`) that pins bundle compositions by content hash. Two processes hashing the same logical bundle produce byte-identical output; the CI fixture matrix in `tests/ci/test_canonical_json.py` pins this property.

E-4 delivers the linter: `Linter` wires together `LifecycleAnalyzer` (completeness — required stages `discover`, `execute`, `error_handle`, `report`, `audit`), `DependencyGraph` (cycle detection via Tarjan's SCC, topological ordering), `ActorConsistencyAnalyzer` (creator/approver conflict detection, authority-tier checks), and a pluggable `RuleRegistry` for per-domain rule packs. The linter-facing models (`JtbdLintSpec`, lint-side `JtbdBundle`) live in `flowforge_jtbd.spec` and use `extra='allow'` so they tolerate schema churn; the canonical models in `flowforge_jtbd.dsl` reject unknown keys.

The SQLAlchemy 2.x ORM in `flowforge_jtbd.db` covers `jtbd_libraries`, `jtbd_domains`, `jtbd_specs`, `jtbd_compositions`, `jtbd_compositions_pins`, and `jtbd_lockfiles`. The Alembic bundle at `flowforge_jtbd.db.alembic_bundle` chains after `flowforge_sqlalchemy`'s `r1_initial`; on PostgreSQL it applies RLS policies, on SQLite (test harness) it skips them.

The conflict solver (E-5), glossary cross-bundle detection (E-8), and domain rule packs (banking, healthcare) are out of scope for this package.

## Quick start

```python
from flowforge_jtbd.lint import Linter
from flowforge_jtbd.spec import ActorRef, JtbdBundle, JtbdLintSpec, RoleDef, StageDecl

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

## Public API

The package intentionally does not re-export names at the top level (the two namespaces share names like `JtbdBundle`). Import the sub-namespace you need:

**`flowforge_jtbd.dsl`** (canonical wire format, E-1)
- `JtbdSpec`, `JtbdBundle`, `JtbdProject`, `JtbdShared`
- `JtbdField`, `JtbdEdgeCase`, `JtbdDocReq`, `JtbdApproval`, `JtbdSla`, `JtbdNotification`
- `JtbdLockfile`, `JtbdLockfilePin`, `JtbdComposition`
- `canonical_json(obj) -> bytes`, `spec_hash(obj) -> str`

**`flowforge_jtbd.spec`** (lint-facing models, E-4)
- `JtbdLintSpec`, `JtbdBundle` (lint-side), `ActorRef`, `RoleDef`, `StageDecl`
- `coerce_bundle(obj)` — accepts dict or `JtbdBundle`

**`flowforge_jtbd.lint`** (linter, E-4)
- `Linter` — top-level orchestrator; `.lint(bundle) -> LintReport`
- `LifecycleAnalyzer`, `DependencyGraph`, `ActorConsistencyAnalyzer`
- `JtbdRule`, `JtbdRulePack`, `RuleRegistry`
- `LintReport`, `JtbdResult`, `Issue`

**`flowforge_jtbd.db`** (SQLAlchemy ORM)
- `JtbdLibrary`, `JtbdDomain`, `JtbdSpecRow`, `JtbdCompositionRow`, `JtbdLockfileRow`
- `alembic_bundle` — Alembic env for running migrations

## Audit-2026 hardening

- **J-01** (E-38): Alembic migration for `r2_jtbd` uses a DDL allowlist for RLS policy statements. Raw `EXECUTE` calls that reference tables outside the allowlist are rejected at migration runtime, preventing a misconfigured migration from granting unintended RLS policies.
- **J-02** (E-47): `DependencyGraph.build()` uses a single-pass adjacency build rather than repeated list scans; lint time on a 100-JTBD bundle is now O(n) not O(n²).
- **J-03** (E-47): `LifecycleAnalyzer` supports `fit()` / `transform()` / `freeze()` methods so callers can pre-compile stage rules once and apply them to many bundles without re-parsing per call.
- **J-04** (E-47): Bundles exceeding 200 JTBDs emit a structured `WARNING` log line with the bundle id and count; no hard cap is imposed.
- **J-05** (E-47): `flowforge_jtbd.ai.nl_to_jtbd` validates natural-language input against a length guard before sending to the LLM port, preventing runaway token spend on malformed requests.
- **J-06** (E-47): Dead-code paths in `flowforge_jtbd.exporters` removed.
- **J-07** (E-47): JSON decoding in `flowforge_jtbd.ai` uses `json.loads()` rather than the deprecated `JSONDecoder.raw_decode()` fallback.
- **J-08** (E-47): The lockfile allowlist for pin sources is validated at `JtbdLockfilePin` construction time rather than at resolution time.
- **J-09** (E-47): `packaging.version.Version` used for semver comparisons in migration helpers; plain string comparison removed.
- **J-10** (E-59): `JtbdManifest` in `flowforge_jtbd.registry.manifest` narrows the `tags` field from `list[Any]` to `list[str]`.
- **J-11** (E-59): Dead-code branches in `flowforge_jtbd.registry.signing` removed.
- **J-12** (E-59): Mention regex in `flowforge_jtbd.glossary` is pre-compiled at module load rather than per-call.

## Compatibility

- Python 3.11+
- `pydantic>=2`
- `sqlalchemy>=2`
- `alembic`
- `packaging`

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-cli`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-cli) — `flowforge jtbd-generate` and `flowforge jtbd lint` consume this package
- [`flowforge-jtbd-hub`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-jtbd-hub) — registry service that publishes and installs JTBD packages built on this spec
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
