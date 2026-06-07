# Session Handover — flowforge (2026-06-07)

## What flowforge is

flowforge is a portable, portable-by-design workflow framework extracted from the UMS project. It provides a JSON DSL, a two-phase fire engine (guard evaluation then atomic commit), a hash-chained audit trail, multi-tenancy, and 14 port ABCs that host applications wire to their own infrastructure. The core is I/O-free — no database drivers, no web frameworks, no cloud SDKs touch `flowforge-core`. UMS is a consumer of flowforge; nothing under this tree imports from UMS. The JTBD (jobs-to-be-done) authoring layer sits above the DSL: you write a YAML/JSON bundle describing actors, stages, requirements, and lifecycle; the CLI generator emits ~12-15 files per JTBD into a host project with byte-identical output across runs.

## Current version: v0.5.0

All 16 strategic packages are at `0.5.0`. The 30 domain `flowforge-jtbd-*` packages remain at `0.0.1` with `[tool.uv] package = false` until they pass E-48a (rebrand to `*-starter`) or E-48b (named-SME content review).

Tags on `origin/main`: `v0.1.0`, `v0.2.0`, `v0.3.0`, `v0.3.0-engr`, `v0.4.0`, `v0.5.0`.

## What was completed (v0.2.0 through v0.5.0)

### v0.2.0 — engineering foundations (audit-2026 follow-on)

Closed the audit-2026 sprint. Shipped the fork engine (E-74 parallel-fork wiring, E-81 join barrier, E-82 fork PromQL alerts), instance token snapshot (E-74p1), full conformance suite green (8 P0+P1 invariants), soak script `--forks-enabled` flag, Makefile `v020` targets, and complete signoff checklist. All 16 strategic packages bumped to `0.2.0`. `forks_enabled` shipped default-off with a layered flag (global + per-workflow `engine_features: [parallel_fork]`).

### v0.3.0-engineering — 22 generation-pipeline improvements

Six-wave execution plan. Shipped: OpenAPI generation, real form renderer (feature-flagged), state-machine diagram, OTel adapter (`flowforge-otel` package), idempotency keys, restore drill, admin console, analytics taxonomy, multi-frontend, bundle-diff, lineage, design tokens, visual regression (DOM-snapshot), property tests, reachability (z3 opt-in), SLA stress, Faker seed data, i18n scaffolding, operator manual MDX, LLM polish sidecar. Cross-runtime fixture extended to 250 cases. Tag `v0.3.0-engr` at commit `e065e77`.

### v0.3.0 (E1) — JTBD authoring CLI + forks default-on

- `flowforge jtbd lint <bundle_path>` — full linter, `--strict`, `--domain`, `--format json|text`, exit 0/1/2.
- `flowforge jtbd lock --init|--verify <bundle_path>` — generate/verify `bundle.lock.json` via `JtbdLockfile`.
- `flowforge jtbd bundle-fork <source> <target> [--out]` — fork bundle with `parent_version_id` provenance.
- `fork_config.forks_enabled()` flipped to default-on (`FLOWFORGE_FORKS_ENABLED=0` to disable).
- 19 acceptance tests in `tests/audit_2026/test_E1_jtbd_lint_cli.py`, all green.

### v0.4.0 (E2) — AI draft, quality scorer, compliance linter, CI hooks

- `flowforge jtbd ai-draft` — NL → JTBD draft via `LlmProviderClaude`; prompt-injection guarded; runs `JtbdLinter` on draft before write; fails closed without `ANTHROPIC_API_KEY`.
- `flowforge jtbd quality-score` — deterministic 4-dimension rubric (clarity, actionability, solution-decoupling, measurable-outcome); `--json`, `--threshold`.
- `flowforge jtbd compliance-lint` — `ComplianceLinterPack` (sensitivity → regime + regime → required-job); `--regime`, `--strict`.
- `scripts/ci/jtbd-precommit.sh` — git pre-commit hook linting staged bundle files.
- `.github/workflows/jtbd-lint.yml` — quality-score + compliance-lint advisory steps.
- `js/flowforge-designer`: `JobMap` swimlane component + `JtbdSummary` TypeScript types.
- 9 acceptance tests in `tests/audit_2026/test_E2_python_features.py`, all green.

### v0.5.0 (E3) — FaultInjector, WorkflowDiffer, tutorial --domain

- `fault.py`: `FaultSpec.target_transition_id`, `FaultInjector.register()`, `should_inject(state, transition_id)`, `apply_to_context(ctx, fault)`.
- `simulator.py`: `simulate()` extended with `faults: list[FaultSpec] | None`.
- `simulate` CLI: `--fault <mode>:<state>` flag (repeatable, 7 modes).
- `tutorial` CLI: `--domain <domain>` loads `flowforge-jtbd-<domain>.load_bundle()`.
- 11 acceptance tests in `tests/audit_2026/test_E3_debugger.py`, all green.

### v0.2.x rolling JTBD content drops

Committed 30-domain JTBD bundle batches across six `feat(v0.2.x)` commits covering: PM, platform-eng, utilities, real-estate, CRM, procurement, legal, e-commerce, logistics, media, SaaS-ops, telco, agritech, construction, corp-finance, nonprofit, manufacturing, education, gaming, travel, restaurants, retail, insurance, healthcare, banking, HR, government, accounting. All in `examples/` subdirectory. Domain packages remain `package=false`.

### Ongoing audit hardening (post v0.5.0 commits)

- `e4cb27c` Keep HMAC signing validation active under optimized Python
- `00aaafa` Keep manifest signing checks active under optimized Python
- `cb64671` Keep Claude validation active under optimized Python
- `7bbfc36` Unify quality scorer with canonical LLM port
- `e688b9b` Keep release-local DNS risk current

## What is next

In priority order:

1. **v0.2.x JTBD content top-up (insurance ≥30 JTBDs, other Tier-A verticals ≥30).** Insurance has the most mature citation library (deepest audit-2026 baseline). Tier-A verticals (insurance, healthcare, banking, HR, government) need ≥30 JTBDs each before v0.2.0 PyPI release. Tier-B domains need ≥10 each.
2. **24h soak gate.** Per plan F-2 / P-4 hard gate: 24h soak with `forks_enabled=True` AND a literal `parallel_fork` workflow active must pass before `forks_enabled` flag is committed default-on for v0.3.0 GA. The soak script is `scripts/ops/audit-2026-soak.sh --forks-enabled`.
3. **v0.2.0 PyPI release.** First PyPI cut for the 16 strategic packages. Per-domain `package=false → package=true` flips cap at 5 domains per v0.2.x minor (ratchet `uv_lock_diff_size.sh` enforces this). Engineering ships first; content rolls through v0.2.x independently.
4. **`scripts/check_all.sh` step 10 layout fix.** Step 10 (UMS parity) hardcodes `cd $REPO_ROOT/../backend` and halts on standalone flowforge checkouts. Add skip-with-reason when `$BACKEND_ROOT` is absent (mirrors step 9's pattern).
5. **Visual-regression dev-server harness (carry-forward #2 from v0.3.0-engr close-out).** The W3 visual-regression runner is structurally complete. `VISREG_DEV_SERVER_URL` env var is the integration point; needs a Vite dev server harness against the generated frontend.

## Key files to read first

| File | Why |
|---|---|
| `CLAUDE.md` | Repo-specific guidance: commands, architecture, conventions, routing table |
| `README.md` | Project overview |
| `CHANGELOG.md` | `[0.2.0]` through `[0.5.0]` headings — per-version feature inventory |
| `docs/v0.2.0-plan.md` | The RALPLAN-DR v2.1.1 plan. Tier-A/B split, staged release shape, 8 risk mitigations, sprint roadmap |
| `docs/audit-fix-plan.md` | Finding index — E-nn ticket → file map |
| `docs/jtbd-grammar.md` | Authoritative JTBD bundle schema reference |
| `docs/jtbd-generation.md` | Generator pipeline: parse → normalize → 15+ generators → write |
| `docs/flowforge-handbook.md` | Comprehensive system overview updated to v0.5.0 |
| `docs/llm.txt` | LLM-readable summary updated to v0.5.0 |
| `python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py` | Generator orchestrator (`_PER_JTBD_GENERATORS` + `_PER_BUNDLE_GENERATORS`) |
| `python/flowforge-core/src/flowforge/ports/` | 14 + 3 port ABCs — I/O-free |
| `tests/conformance/test_arch_invariants.py` | 11 architectural invariants; P0 = {1, 5, 10, 11} must stay green |
| `scripts/ci/ratchets/check.sh` | 7 ratchet scripts — non-negotiable on every PR |
| `scripts/ops/audit-2026-soak.sh` | Soak script; `--forks-enabled` flag required for the v0.3.0 GA gate |

## Do/don't conventions

### DO

- **Tabs, not spaces** in Python. Project-wide, enforced by editorconfig.
- **Async throughout** — engine, fire, ports, CLI commands are all async.
- **Pydantic v2** with `model_config = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)` for canonical models. Lint-side `JtbdLintSpec` uses `extra='allow'` — keep the split.
- **UUID7 string IDs** via the local shim: `from flowforge._uuid7 import uuid7str`. `uuid_extensions` is not on PyPI; use `uuid6`.
- **No mocks except LLMs** — use `flowforge.testing.port_fakes` (real in-memory implementations). Postgres-backed tests use testcontainers.
- **Async tests** — plain `async def`, no `@pytest.mark.asyncio`. `asyncio_mode = "auto"` set at package level.
- **Per-finding test in `tests/audit_2026/test_<FINDING>_<short>.py`** with a corresponding row in `docs/audit-2026/signoff-checklist.md`. `make audit-2026-signoff` enforces this.
- **For new generators**: per-JTBD in `flowforge_cli/jtbd/generators/`, register in `pipeline.py`, declare `CONSUMES` in module + `_fixture_registry.py`, add unit tests, verify byte-identical regen via `scripts/check_all.sh` step 8.
- **Cap `package=true` flips at 5 domains per v0.2.x minor** (ratchet `uv_lock_diff_size.sh` warns on >5 in one PR).
- **Add ADRs before touching load-bearing surfaces** — 4 v0.3.0-engineering ADRs under `docs/v0.3.0-engineering/adr/` are a template.
- **Both sides for new expr operators** — Python `flowforge.expr` + TypeScript `@flowforge/renderer` + extend the 250-case `expr_parity_v2.json` fixture in the same PR.

### DON'T

- **Don't add I/O dependencies to `flowforge-core`.** Conformance invariant enforces I/O-free. Adapters go in separate packages.
- **Don't modify `flowforge.expr`** without updating the cross-runtime fixture. Invariant 5 + ratchet `no_unparried_expr_in_step_template` will fail.
- **Don't put authoring overrides in `JtbdBundle`** — ADR-002 mandates the sidecar pattern (`flowforge_cli.jtbd.overrides`, `<bundle_path>.overrides.json`); `spec_hash` must remain untouched.
- **Don't use `@hypothesis.settings(seed=N)`** — that's not a real API. Use `@hypothesis.seed(N)` as a separate decorator stacked above `@settings(...)` (ADR-003).
- **Don't add `z3-solver` to runtime deps** — opt-in extra `flowforge-cli[reachability]` only, hard pin `z3-solver==4.13.4.0` (ADR-004).
- **Don't flip a domain package to `package=true`** without E-48a (rebrand to `*-starter`) or E-48b (named-SME content review) passing.
- **Don't bypass the regen-diff gate** (`check_all.sh` step 8). Silent determinism drift only shows there.
- **Don't introduce LLM calls in the generation pipeline.** `flowforge jtbd ai-draft` is the only LLM touchpoint, scoped as a pre-generation authoring sidecar. Determinism of `regen` is non-negotiable.
- **Don't commit `.omc/` or any local agent state.** Gitignored; never add.
- **Don't skip the 24h soak gate** before flipping `forks_enabled` default-on for v0.3.0 GA. Plan risk F-2 makes this a hard exit gate, not advisory.
- **Don't expect `check_all.sh` to fully pass on a standalone flowforge checkout** — step 10 (UMS parity) requires `../backend/` adjacent. Fix or skip-with-reason pending.
