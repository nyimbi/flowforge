# flowforge

A portable workflow framework. JSON DSL, two-phase fire engine, hash-chained audit trail, multi-tenant by default, 14 port ABCs that host applications wire to their own infrastructure. Extracted from the UMS project, which consumes flowforge but does not appear in its dependency graph; nothing under this tree imports from UMS.

> **v0.1.0 shipped 2026-05-08 — audit-2026 release.** Closes 77 audit findings, 9 architectural invariants conformance-tested, 4 security ratchets enforced in CI. Includes one **SECURITY-BREAKING** change (E-34: HMAC default secret removed; opt-in bridge available for one minor). Read [`docs/audit-2026/SECURITY-NOTE.md`](docs/audit-2026/SECURITY-NOTE.md) and run `flowforge pre-upgrade-check` against every host before upgrading. Upgrade checklist: [`docs/release/v0.1.0-upgrade.md`](docs/release/v0.1.0-upgrade.md). Close-out report: [`docs/audit-2026/close-out.md`](docs/audit-2026/close-out.md).

## What it is

A workflow definition is a single JSON document with a canonical schema. The compiler validates topology at load time (unreachable states, dead-end transitions, duplicate priorities, sub-workflow cycles) so you can't ship a definition that runs differently than it diff-reads. The expression evaluator is a whitelisted operator registry, frozen at module init: no `eval`, no arbitrary Python, byte-identical results between the Python core and the TypeScript designer/renderer. A 200-input parity fixture is run on every PR.

The engine is two-phase. Phase 1 evaluates guards and picks one transition. Phase 2 commits effects, appends saga steps, dispatches outbox envelopes, and records audit events. Per-instance fire is serialised; a concurrent fire for the same instance raises `ConcurrentFireRejected`. If outbox or audit dispatch fails, the engine restores the pre-fire snapshot. The audit chain is hash-linked under a per-tenant advisory lock with a `UNIQUE(tenant_id, ordinal)` constraint, so 100 concurrent records per tenant produce zero forks.

The core is I/O-free. It defines 14 port ABCs (tenancy, RBAC, audit, outbox, documents, money, settings, signing, notifications, RLS, entity registry, metrics, tasks, grants) that host applications wire to their own infrastructure. SQLAlchemy, FastAPI, KMS, S3, SpiceDB, Mailgun all live in separate adapter packages. A conformance test fails the build if the core ever takes an I/O dependency.

JTBD (jobs-to-be-done) is the authoring layer above the DSL. You write a bundle (YAML or JSON) describing actors, stages, requirements, glossary, and lifecycle. The CLI generator emits ~12-15 files per JTBD into a host project: alembic migration with RLS policy, SQLAlchemy model, FastAPI router, EntityAdapter, workflow definition, form spec, React step component, Playwright happy-path. Output is byte-identical across runs; CI diffs `examples/*/generated/` against a fresh regen on every PR. A bundle hash (RFC-8785-aligned canonical JSON) makes two processes agree on the bundle bytes regardless of dict ordering.

## Quick start

```python
from flowforge import config
from flowforge.dsl import WorkflowDef, State, Transition, Effect
from flowforge.engine import fire, new_instance

config.reset_to_fakes()  # in-memory ports — sufficient for tests and local dev

wf = WorkflowDef(
	key="claim",
	version="1",
	initial_state="draft",
	states=[
		State(id="draft", kind="manual_review", label="Draft"),
		State(id="submitted", kind="terminal_success", label="Submitted"),
	],
	transitions=[
		Transition(
			id="t1",
			from_state="draft",
			to_state="submitted",
			on_event="submit",
			priority=0,
			effects=[Effect(kind="notify", target="ops", template="claim_submitted")],
		),
	],
)

instance = new_instance(wf)
result = await fire(instance, event="submit", payload={}, wf=wf)
print(result.new_state)  # "submitted"
```

For a real deployment, wire the production ports (Postgres-backed snapshot store, hash-chain audit, outbox worker, KMS signing, S3 documents) through their adapter packages. See `python/flowforge-fastapi/README.md` for the HTTP surface and `python/flowforge-sqlalchemy/README.md` for durable storage.

### From a JTBD bundle

```bash
# Scaffold a new project from a domain JTBD bundle
flowforge new my-app --jtbd flowforge-jtbd-banking

# Add another bundle into an existing project (idempotent)
flowforge add-jtbd flowforge-jtbd-hr

# Lint a bundle file
flowforge jtbd lint --def bundle.yaml

# Run the deterministic generator (12+ files per JTBD)
flowforge jtbd-generate --jtbd ./bundle.yaml --out ./generated

# Walk the generated workflow with events
flowforge simulate --def workflows/account_open/definition.json
```

## Architecture

Three layers, kept clean by tests:

- **Core** (`flowforge-core`) — DSL, compiler, expression evaluator, engine, simulator, replay, port ABCs, in-memory port fakes. Pure Python, no I/O dependencies.
- **Adapters** — one package per port implementation. Picked à la carte at host startup via `flowforge.config`.
- **JTBD** (`flowforge-jtbd`, `flowforge-jtbd-hub`, 30 domain libraries) — authoring layer that generates host-app code from a bundle.

```
JTBDEditor  ──▶  bundle.yaml  ──▶  flowforge-cli ──▶  workflow_def.json + form_spec.json + ...
                                                               │
Designer    ──▶  workflow_def.json  ─────────────────────────▶│
                                                               ▼
                                                        flowforge-fastapi
                                                               │
                                                               ▼
                                                          flowforge-core (engine)
                                                          /         \
                                                  flowforge-          flowforge-
                                                  audit-pg            outbox-pg
                                                  (hash chain)        (dramatiq)
                                                          │
                                                          ▼
                                                     Postgres
```

### The 14 ports

| # | Port | Purpose | Default impl |
|---|---|---|---|
| 1 | `TenancyResolver` | Resolve current tenant, bind session GUCs, elevation scope | `flowforge-tenancy` (`SingleTenantGUC`, `MultiTenantGUC`, `NoTenancy`) |
| 2 | `RbacResolver` | `has_permission`, `list_principals_with`, `register_permission`, `assert_seed` | `flowforge-rbac-static`, `flowforge-rbac-spicedb` |
| 3 | `AuditSink` | `record`, `verify_chain`, `redact` | `flowforge-audit-pg` (hash chain, per-tenant advisory lock) |
| 4 | `OutboxRegistry` | `register(kind, handler, backend)`, `dispatch(envelope)` | `flowforge-outbox-pg` (dramatiq) |
| 5 | `DocumentPort` | `list_for_subject`, `attach`, `get_classification`, `freshness_days` | `flowforge-documents-s3` |
| 6 | `MoneyPort` | `convert`, `format` | `flowforge-money` |
| 7 | `SettingsPort` | `get`, `set`, `register` | host-supplied |
| 8 | `SigningPort` | `sign_payload`, `verify`, `current_key_id` | `flowforge-signing-kms` (AWS KMS, GCP KMS, HMAC dev) |
| 9 | `NotificationPort` | `render`, `send`, `register_template` | `flowforge-notify-multichannel` (email/Slack/SMS/in-app) |
| 10 | `RlsBinder` | `bind(session, ctx)`, `elevated(session)` | `flowforge-sqlalchemy.PgRlsBinder` (GUC-based) |
| 11 | `EntityAdapter` | `create`, `update`, `lookup`, `compensations` | host-supplied (generated by JTBD) |
| 12 | `MetricsPort` | `emit(name, value, labels)` | host-supplied |
| 13 | `TaskTrackerPort` | `create_task(kind, ref, note)` | host-supplied |
| 14 | `AccessGrantPort` | `grant(rel, until)`, `revoke(rel)` | host-supplied |

Tests use the in-memory fakes under `flowforge.testing.port_fakes`. Production wires whichever adapters you need.

## Repository layout

This is a `uv` + `pnpm` monorepo: 45 Python workspace members, 7 npm workspace members.

```
flowforge/
├── python/                          # uv workspace (45 packages)
│   │
│   │ # Strategic / shipping packages (15, package=true)
│   ├── flowforge-core/               # DSL, compiler, engine, simulator, port ABCs
│   ├── flowforge-fastapi/            # HTTP/WS adapter
│   ├── flowforge-sqlalchemy/         # snapshot store, saga ledger, RLS binder, alembic bundle
│   ├── flowforge-tenancy/            # SingleTenantGUC / MultiTenantGUC / NoTenancy
│   ├── flowforge-audit-pg/           # hash-chain audit sink
│   ├── flowforge-outbox-pg/          # outbox + dramatiq worker
│   ├── flowforge-rbac-{static,spicedb}/
│   ├── flowforge-documents-s3/
│   ├── flowforge-money/
│   ├── flowforge-signing-kms/
│   ├── flowforge-notify-multichannel/
│   ├── flowforge-cli/                # `flowforge` typer CLI
│   ├── flowforge-jtbd/               # canonical spec, lockfile, linter
│   ├── flowforge-jtbd-hub/           # registry, mirroring, signing, per-user RBAC
│   │
│   │ # Domain JTBD libraries (30, package=false until E-48a/b)
│   └── flowforge-jtbd-{accounting, agritech, banking, compliance, construction,
│       corp-finance, crm, ecom, edu, gaming, gov, healthcare, hr, insurance,
│       legal, logistics, media, mfg, municipal, nonprofit, platformeng, pm,
│       procurement, realestate, restaurants, retail, saasops, telco, travel,
│       utilities}/
├── js/                              # pnpm workspace (7 packages)
│   ├── flowforge-types/              # TS types generated from core JSON schemas
│   ├── flowforge-renderer/           # FormRenderer + TS expr evaluator (parity-tested)
│   ├── flowforge-runtime-client/     # REST + WS client (reconnect, collab conflict)
│   ├── flowforge-step-adapters/      # generic step components
│   ├── flowforge-designer/           # canvas, property panel, simulator UI, diff viewer
│   ├── flowforge-jtbd-editor/        # JTBD authoring IDE
│   └── flowforge-integration-tests/  # cross-runtime parity, WS reconnect, collab conflict
├── examples/                        # JTBD worked examples
│   ├── insurance_claim/
│   ├── hiring-pipeline/
│   └── building-permit/
├── tests/                           # cross-package layered suites
│   ├── audit_2026/                   # one regression test per audit finding
│   ├── conformance/                  # 9 architectural invariants
│   ├── property/                     # hypothesis property tests
│   ├── chaos/                        # crash mid-fire / mid-outbox / mid-compensation
│   ├── cross_runtime/                # 200-input TS↔Python expr parity fixture
│   ├── edge_cases/                   # 9-class edge-case bank
│   ├── observability/                # promtool + synthetic metric injection
│   └── integration/{python,js,e2e}/
├── docs/
│   ├── flowforge-handbook.md         # comprehensive system overview
│   ├── workflow-framework-portability.md  # source spec
│   ├── workflow-framework-plan.md    # build plan
│   ├── audit-fix-plan.md             # audit-2026 ticket index
│   ├── audit-2026/                   # SECURITY-NOTE, signoff-checklist, close-out, backlog
│   ├── ops/                          # runbooks (soak test, etc.)
│   └── v0.2.0-plan.md                # next-milestone plan
└── scripts/
    ├── check_all.sh                  # full developer gate (≈10 min)
    ├── ci/ratchets/                  # 4 grep gates
    ├── ci/check_signoff.py           # signoff-checklist gate
    └── ops/audit-2026-soak.sh        # 24h soak runner
```

The 30 `flowforge-jtbd-<domain>/` packages are registered with `[tool.uv] package = false` per package until they pass either E-48a (rebrand to `*-starter` with scaffold-only classifier) or E-48b (real-content review by a named domain SME). Five strategic verticals carry real content today: banking, gov, healthcare, hr, insurance.

## What gets generated

For one JTBD `claim_intake`, the generator emits ~12-15 files (≈600 LOC of host code):

| File | Purpose |
|---|---|
| `alembic/versions/000N_jtbd_<id>.py` | Entity table migration + RLS policy |
| `backend/src/<pkg>/<entity>/models.py` | SQLAlchemy model with `WorkflowExposed` mixin |
| `backend/src/<pkg>/<entity>/views.py` | Pydantic v2 models for HTTP/CLI |
| `backend/src/<pkg>/<entity>/service.py` | Business logic |
| `backend/src/<pkg>/<entity>/router.py` | FastAPI router |
| `backend/src/<pkg>/<entity>/workflow_adapter.py` | `EntityAdapter` impl + compensations map |
| `backend/src/<pkg>/<entity>/tests/test_workflow_adapter.py` | Unit tests |
| `backend/src/<pkg>/workflows/<id>/definition.json` | Workflow DSL |
| `backend/src/<pkg>/workflows/<id>/form_spec.<form_id>.json` | Form spec |
| `backend/src/<pkg>/workflows/<id>/tests/test_simulation.py` | Auto-generated simulator tests |
| `frontend/src/components/<entity>/<Entity>Step.tsx` | React step wrapper |
| `tests/e2e/<id>.spec.ts` | Playwright happy-path |

A bundle of N JTBDs additionally emits 4-6 cross-cutting files: permission seeds, RBAC seed test, navigation index, JTBD glossary, audit taxonomy enum, frontend wiring.

## Examples

Three end-to-end bundles live under `examples/`. Each ships its `jtbd-bundle.json` and a `generated/` tree that CI diffs byte-for-byte against a fresh regen.

| Example | Demonstrates |
|---|---|
| `insurance_claim/` | Claim intake → triage → adjudication → payout, with documents, signing, audit chain. |
| `hiring-pipeline/` | Candidate sourcing → screen → interview loop → offer, with multi-stage approvals. |
| `building-permit/` | Permit application → review → inspection → issuance, with RLS-scoped tenant data. |

## Development

You need `uv ≥ 0.4`, `pnpm ≥ 9`, Python 3.11, Node 20.

```bash
uv sync                                     # install Python workspace
(cd js && pnpm install --frozen-lockfile)   # install JS workspace

bash scripts/check_all.sh                   # full local gate (≈10 min)
make audit-2026                             # layered audit-2026 suites
```

Narrower loops:

```bash
uv run pytest python/flowforge-core/tests -q       # one package
uv run pytest tests/audit_2026/test_C_04_*.py -v   # one finding
uv run pytest tests/conformance/ -m invariant_p0   # P0 invariants only
uv run pyright python/flowforge-core/src --pythonversion 3.11

(cd js && pnpm -r test)                             # all JS packages
(cd js && pnpm -F @flowforge/designer test)         # one package
```

CI runs three independent gates on every PR, each blocking merge to `main`:

- `flowforge-gate.yml` — wraps `scripts/check_all.sh` (sync, typecheck, per-package pytest, JS build, JTBD regen determinism, UMS parity, integration). Single source of truth for local-vs-CI parity.
- `audit-2026.yml` — six-target matrix over `make audit-2026-{unit,conformance,property,edge,cross-runtime,e2e}` plus the ratchet and signoff gates.
- `jtbd-lint.yml` — runs `flowforge jtbd lint` against every `jtbd-bundle.{json,yaml}` in the tree. Set `JTBD_LINT_STRICT=true` to treat warnings as errors.

### CLI

The `flowforge` CLI is a Typer app with three sub-apps:

- `flowforge audit verify` — verify the audit hash chain against a saved checkpoint (skeleton).
- `flowforge jtbd {fork,lint,migrate}` — JTBD lifecycle commands.
- `flowforge audit-2026 health --prom-url <prom>` — query Prometheus for the audit-2026 release-health SLIs; exits non-zero on any required-probe failure.

Top-level commands: `validate`, `simulate`, `replay`, `new`, `add-jtbd`, `regen-catalog`, `jtbd-generate`, `pre-upgrade-check`, `migrate-fork`, `tutorial`, `diff`, `ai-assist`, `generate-llmtxt`, `upgrade-deps`. Run `flowforge --help` for the live list.

## Security posture

Three CI gates are non-negotiable for merge to `main`:

1. **Ratchets** — four grep-based regression gates under `scripts/ci/ratchets/`:
   - `no_default_secret.sh` — bans `FLOWFORGE_SIGNING_SECRET` defaults and dev-secret literals (SK-01).
   - `no_string_interp_sql.sh` — bans f-string / `.format()` / `%` SQL (T-01, J-01, OB-01).
   - `no_eq_compare_hmac.sh` — bans `==` on HMAC digests; mandates `hmac.compare_digest` (NM-01).
   - `no_except_pass.sh` — bans `except Exception: pass` swallow (J-10, JH-06, CL-04).

   Legitimate exceptions go in `scripts/ci/ratchets/baseline.txt` with security-team review in the same PR.

2. **Conformance** — nine architectural invariants tagged `@invariant_p0` / `@invariant_p1`:
   1. Tenant isolation (T-01..T-03)
   2. Engine fire two-phase atomicity (C-01, C-04)
   3. Replay determinism (C-06, C-07)
   4. Snapshot isolation (C-12)
   5. Cross-runtime expression parity (JS-01..JS-03)
   6. RBAC seed integrity
   7. Audit-chain monotonicity (AU-01..AU-03)
   8. Migration RLS DDL safety (J-01)
   9. Parallel-fork token primitives (E-74)

   P0 must stay green on every PR.

3. **Signoff** — every audit finding has its acceptance test in `tests/audit_2026/test_<FINDING>_*.py` and a row in `docs/audit-2026/signoff-checklist.md`. `make audit-2026-signoff` enforces the mapping; `python scripts/ci/check_signoff.py --strict` fails if any P0/P1 row is missing evidence.

A 24-hour soak runner lives at `scripts/ops/audit-2026-soak.sh`; the runbook is at `docs/ops/audit-2026-soak-test.md`. Release health is queryable from any host without Grafana via `flowforge audit-2026 health`, which probes Prometheus directly and is intended as a post-deploy gate or periodic ops cron.

## Versioning

Two tiers, both enforced by `tests/audit_2026/test_E_69_evolution_reconciliation.py`:

- **Tier 1** — engine and adapters (15 packages). Pinned at `0.1.x`; patch bump per audit-fix release; `0.2.0` reserved for the post-audit GA. Public APIs stable within `0.1.x`. Any SECURITY-flagged removal follows the F-7 two-version deprecation rule with an opt-in bridge env-var (e.g. `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` for E-34).
- **Tier 2** — domain JTBD libraries (30 packages). Pinned at `0.0.1` until the package flips to `[tool.uv] package = true`, at which point it jumps to `0.1.0` in lockstep with tier 1.

## Conventions

- **Async throughout.** Engine, fire, all ports.
- **Pydantic v2** with `model_config = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)` for canonical models. The lint-side `JtbdLintSpec` uses `extra='allow'` to tolerate schema churn.
- **Tabs, not spaces** in Python.
- **UUID7 string IDs** via the local `uuid6`-backed shim (`uuid_extensions` is *not* on PyPI; don't add it as a dependency).
- **No mocks except for LLMs.** Tests use `flowforge.testing.port_fakes` (real in-memory implementations). Postgres-backed tests use testcontainers.

## Status

`v0.1.0` shipped. Path-dependency only; not yet on PyPI. The framework is in active build; the next milestone is `v0.2.0` (post-audit GA), planned in [`docs/v0.2.0-plan.md`](docs/v0.2.0-plan.md). The architecturally deferred items live in [`docs/audit-2026/backlog.md`](docs/audit-2026/backlog.md).

## Documentation

- [`docs/flowforge-handbook.md`](docs/flowforge-handbook.md) — comprehensive system overview (ADRs, data model, request lifecycle, runbook hooks)
- [`docs/workflow-framework-portability.md`](docs/workflow-framework-portability.md) — source spec
- [`docs/workflow-framework-plan.md`](docs/workflow-framework-plan.md) — build plan
- [`docs/jtbd-editor-arch.md`](docs/jtbd-editor-arch.md) — JTBD authoring IDE design
- [`docs/flowforge-evolution.md`](docs/flowforge-evolution.md) — forward roadmap
- [`docs/audit-fix-plan.md`](docs/audit-fix-plan.md) — audit-2026 ticket index
- [`docs/audit-2026/SECURITY-NOTE.md`](docs/audit-2026/SECURITY-NOTE.md) — operator-action notes per security-impacting change
- [`docs/llm.txt`](docs/llm.txt) — AI quickstart
- [`CLAUDE.md`](CLAUDE.md) — guidance for Claude Code instances entering this repo

Per-package READMEs live alongside their `pyproject.toml` (e.g. `python/flowforge-core/README.md`).

## License

Apache-2.0. A dual-license commercial track is planned per the portability spec §11 R14.
