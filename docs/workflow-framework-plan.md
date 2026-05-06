# Flowforge Build Plan — Topological DAG

Companion to `docs/workflow-framework-plan.json` (machine-readable). Source spec:
`docs/workflow-framework-portability.md`. Build target: `framework/` subtree
inside the UMS repo (no PyPI/npm publish in this iteration).

## Constraints

- Total agent invocation cap: **25** across the full pipeline (planner + executors + critics + commits combined where possible).
- Do not modify existing UMS code outside the explicit migration unit (U23). Audit-remediation work in flight stays untouched.
- Default adapter implementations may reference `backend/app/...` for shape, but the framework lives entirely under `framework/`.
- Every public ABC ships with docstring, full type hints, default impl, and at least one test.
- Every package ships a README + CHANGELOG.
- The 3 worked JTBD examples (claim, hiring, permit) must be generated and execute their tests green.

## Layer-by-layer execution order

| Layer | Parallel | Units | Notes |
|---|---|---|---|
| L0 | no | U00 | Workspace skeleton (uv + pnpm). Solo, fast. |
| L1 | no | U01 | **flowforge-core** — port ABCs locked first; everything depends on it. |
| L2 | yes | U02 U03 U04 U05 U06 U07 | First adapter wave. Hits FastAPI, SQLAlchemy, tenancy, audit-pg, outbox-pg, rbac-static. |
| L3 | yes | U08 U09 U10 U11 U12 U13 | Second adapter wave + CLI shell. rbac-spicedb, documents-s3, money, signing-kms, notify-multichannel, cli. |
| L4 | yes | U14 U15 U16 U17 U18 | npm packages. types -> renderer/runtime-client -> step-adapters -> designer. |
| L5 | no | U19 | JTBD generator (bundled into flowforge-cli; depends on CLI shell from U13). |
| L6 | yes | U20 U21 U22 | Three worked examples — claim, hiring, permit. |
| L7 | no | U23 | UMS migration: reflect 23 Python defs to JSON DSL with parity tests. |
| L8 | no | U24 | End-to-end check_all.sh gate. |

## Unit summary table

| ID | Title | Tier | Deps |
|---|---|---|---|
| U00 | framework/ skeleton + uv/pnpm workspaces | haiku | — |
| U01 | flowforge-core (ports + DSL + engine + simulator + tests) | opus | U00 |
| U02 | flowforge-fastapi | sonnet | U01 |
| U03 | flowforge-sqlalchemy | sonnet | U01 |
| U04 | flowforge-tenancy | haiku | U01 |
| U05 | flowforge-audit-pg | sonnet | U01 U03 |
| U06 | flowforge-outbox-pg | sonnet | U01 U03 |
| U07 | flowforge-rbac-static | haiku | U01 |
| U08 | flowforge-rbac-spicedb | sonnet | U01 |
| U09 | flowforge-documents-s3 (+ noop) | sonnet | U01 |
| U10 | flowforge-money | haiku | U01 |
| U11 | flowforge-signing-kms (+ hmac dev) | haiku | U01 |
| U12 | flowforge-notify-multichannel | sonnet | U01 |
| U13 | flowforge-cli (typer shell) | opus | U01 |
| U14 | @flowforge/types | haiku | U01 |
| U15 | @flowforge/renderer | sonnet | U14 |
| U16 | @flowforge/runtime-client | sonnet | U14 |
| U17 | @flowforge/step-adapters | haiku | U15 U16 |
| U18 | @flowforge/designer | opus | U15 U16 U17 |
| U19 | JTBD generator (parse + normalize + 14 generators) | opus | U13 |
| U20 | Worked example A — claims-intake-demo | sonnet | U19 |
| U21 | Worked example B — ats-lite | sonnet | U19 |
| U22 | Worked example C — permits | sonnet | U19 |
| U23 | UMS migration: 23 Python defs -> JSON DSL + parity | opus | U01 U13 |
| U24 | check_all.sh gate (pytest + pyright + pnpm test + pnpm lint) | haiku | all |

## Invocation budget plan (cap 25)

The 25-cap is tight for 25 units. Practical strategy:

1. **Bundle parallel adapter waves into single Task() calls.** Each Task can be told to build N small packages (haiku-tier ones especially) since they share a template. L2 fires as 1 sonnet Task (U02+U03+U05+U06) + 1 haiku Task (U04+U07). L3 fires as 1 sonnet Task (U08+U09+U12) + 1 haiku Task (U10+U11) + 1 opus Task (U13). L4 fires as 1 haiku Task (U14+U17) + 1 sonnet Task (U15+U16) + 1 opus Task (U18). L6 fires as 1 sonnet Task (U20+U21+U22).
2. **In-line easy units.** U00 and U24 are scripts/scaffolding; the orchestrator does them directly without spawning.
3. **Critic passes are batched.** One critic run per layer covers all units in that layer.

Resulting estimate:

| Stage | Tasks |
|---|---|
| U00 (in-line) | 0 |
| U01 (executor + critic) | 2 |
| L2 (executor x2 + critic x1) | 3 |
| L3 (executor x3 + critic x1) | 4 |
| L4 (executor x3 + critic x1) | 4 |
| U19 (executor + critic) | 2 |
| L6 (executor x1 + critic x1) | 2 |
| U23 (executor + critic) | 2 |
| U24 (in-line) | 0 |
| **Total** | **19** |

Buffer of 6 invocations for re-work when a critic rejects.

## Quality gates per unit

- `pytest` runs at unit boundary for that package.
- `pyright` runs at unit boundary for that package.
- For npm units: `pnpm --filter <pkg> test` + `pnpm --filter <pkg> lint`.
- Critic verifies every acceptance criterion before commit.
- Each unit produces exactly one commit, prefixed `feat(<pkg>):` or `test(<pkg>):` per the user's brief.
- Push after each commit (origin/main).

## Stop conditions

- All 25 DAG units complete with critic approval -> run U24, push final, report.
- 25-invocation cap reached -> stop, report which units remain.
- Blocker requires user input -> stop, report.

## Risk register

- **R-A** flowforge-core (U01) is the load-bearing unit. If it slips, every downstream Task is blocked. Mitigation: written first, single agent, opus tier, with the option to split.
- **R-B** Designer (U18) and CLI (U13) and JTBD generator (U19) each hit the 4-6h split threshold. Each carries an explicit split rule.
- **R-C** UMS migration (U23) parity is brittle — 23 defs include sagas + subworkflows. Failure mode is logged as KNOWN_GAPS rather than blocking the framework.
