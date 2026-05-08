# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`flowforge` is a portable workflow framework extracted from the UMS project. It is a **multi-language uv + pnpm monorepo** producing 45 Python packages and 7 npm packages. UMS is a *consumer* of flowforge — nothing under this tree imports from UMS, and the boundary is enforced by tests.

Source spec: `docs/workflow-framework-portability.md`. Build plan: `docs/workflow-framework-plan.md`. Comprehensive system overview: `docs/flowforge-handbook.md`. The current sprint plan is `docs/v0.2.0-plan.md` (audit-2026 follow-on).

## Workspaces

Two coexistent workspace tools — never mix them:

- **Python** — `uv` workspace rooted at `pyproject.toml`. Members under `python/`. The 15 *strategic* packages (`flowforge`, `flowforge-fastapi`, `flowforge-sqlalchemy`, `flowforge-tenancy`, the two `*-pg` adapters `flowforge-audit-pg` + `flowforge-outbox-pg`, `flowforge-rbac-{static,spicedb}`, `flowforge-documents-s3`, `flowforge-money`, `flowforge-signing-kms`, `flowforge-notify-multichannel`, `flowforge-cli`, `flowforge-jtbd`, `flowforge-jtbd-hub`) ship; the 30 `flowforge-jtbd-<domain>/` packages are registered with `[tool.uv] package = false` until they pass E-48a (rebrand to `*-starter`) or E-48b (real-content review by named SME). Don't flip a domain package to `package = true` without that gate.
- **JS** — `pnpm` workspace rooted at `js/pnpm-workspace.yaml`. Seven packages: `flowforge-types`, `flowforge-renderer`, `flowforge-runtime-client`, `flowforge-step-adapters`, `flowforge-designer`, `flowforge-jtbd-editor`, `flowforge-integration-tests`. Run pnpm commands from inside `js/`.

## Commands

All commands run from repo root unless noted.

```bash
# install / sync
uv sync                                  # python workspace
(cd js && pnpm install --frozen-lockfile)  # js workspace

# quality gate (single source of truth — what CI runs)
bash scripts/check_all.sh                # full U24 gate: uv sync, pnpm install,
                                          # workspace check, pyright + pytest per pkg,
                                          # pnpm typecheck + build + test, JTBD regen
                                          # determinism, UMS parity, integration

# audit-2026 layered suites (Makefile)
make audit-2026                          # everything below
make audit-2026-unit                     # tests/audit_2026/test_<FINDING>_*.py
make audit-2026-conformance              # tests/conformance — arch §17 invariants
make audit-2026-conformance-p0           # P0 invariants only
make audit-2026-property                 # tests/property (hypothesis)
make audit-2026-integration              # tests/integration/python
make audit-2026-e2e                      # tests/integration/e2e
make audit-2026-cross-runtime            # TS↔Python expr parity (200-tuple fixture)
make audit-2026-edge                     # tests/edge_cases (9 classes)
make audit-2026-chaos                    # crash mid-fire / mid-outbox / mid-compensation
make audit-2026-observability            # promtool check rules + synthetic metrics
make audit-2026-ratchets                 # bash scripts/ci/ratchets/check.sh
make audit-2026-signoff                  # scripts/ci/check_signoff.py

# narrower loops
uv run pytest python/flowforge-core/tests -q                # one package
uv run pytest tests/audit_2026/test_C_04_*.py -v            # one finding
uv run pytest tests/conformance/ -m invariant_p0            # P0 invariants
uv run pytest -k "test_name_substring"                      # one test
uv run pyright python/flowforge-core/src --pythonversion 3.11

(cd js && pnpm -r build)                  # build all js pkgs
(cd js && pnpm -r --if-present typecheck)
(cd js && pnpm -r test)                   # vitest suites
(cd js && pnpm -F @flowforge/designer test)  # one package
```

The CLI is `uv run flowforge ...`. It's a Typer app with three sub-apps: `flowforge audit <cmd>` (currently `verify`), `flowforge jtbd <cmd>` (`fork`, `lint`, `migrate`), and `flowforge audit-2026 <cmd>` (currently `health`). Top-level commands are hyphenated: `validate`, `simulate`, `replay`, `new`, `add-jtbd`, `regen-catalog`, `jtbd-generate`, `pre-upgrade-check`, `migrate-fork`, `tutorial`, `diff`, `ai-assist`, `generate-llmtxt`, `upgrade-deps`. Run `flowforge --help` to enumerate; wiring is in `python/flowforge-cli/src/flowforge_cli/main.py`, sources in `commands/` and `jtbd/`.

## Architecture (the parts you can't read off the file tree)

### Hexagonal core, 14 ports

`flowforge-core` (PyPI name `flowforge`) is **I/O-free**. It defines 14 port ABCs that host applications wire to their own infrastructure: `TenancyResolver`, `RbacResolver`, `AuditSink`, `OutboxRegistry`, `DocumentPort`, `MoneyPort`, `SettingsPort`, `SigningPort`, `NotificationPort`, `RlsBinder`, `EntityAdapter`, `MetricsPort`, `TaskTrackerPort`, `AccessGrantPort`. The core never imports a database driver, web framework, or cloud SDK — those live in the `flowforge-<adapter>` sibling packages. **Don't add I/O dependencies to `flowforge-core`** — conformance test `tests/conformance/` enforces this as one of the 8 architectural invariants.

Wiring happens through the mutable global registry `flowforge.config`. Tests use `flowforge.config.reset_to_fakes()` and the in-memory implementations under `flowforge.testing.port_fakes`.

### Two-phase fire engine

`flowforge.engine.fire(instance, event, payload, wf)` is the single mutation entry point. **Phase 1** evaluates guards through the whitelisted `flowforge.expr` evaluator (no `eval`, no arbitrary Python — operator registry frozen at module-init per E-35) and picks one transition. **Phase 2** commits effects, appends saga steps, dispatches outbox envelopes, and records audit events. The engine is **per-instance serialised**; a concurrent fire raises `ConcurrentFireRejected` (E-32 / C-04). Outbox or audit failure restores the pre-fire snapshot. The snapshot store is copy-on-read (E-61). Don't relax any of this without an audit reference.

### JTBD authoring & generation pipeline

`flowforge-jtbd` defines the canonical JTBD spec (Pydantic v2, `extra='forbid'`, RFC-8785 canonical JSON). A bundle hashes deterministically (`spec_hash()`) and is pinned by `JtbdLockfile`. The CLI's `flowforge jtbd-generate --jtbd <bundle>.json --out <dir>` emits ~12-15 files per JTBD into a host project (alembic migration, SQLAlchemy model, FastAPI router, EntityAdapter, workflow_def.json, form_spec.json, React step component, Playwright spec). **Regen output must be byte-identical** — `scripts/check_all.sh` step 8 diffs `examples/<example>/generated/` against a fresh regen and fails on drift.

`flowforge-jtbd` (canonical models, `extra='forbid'`) and the lint-side `JtbdLintSpec` (`extra='allow'`, tolerates schema churn) are deliberately separate — keep that split.

### Audit hardening: ratchets, invariants, signoff

Three CI gates are non-negotiable on every PR (`audit-2026.yml`):

1. **Ratchets** (`scripts/ci/ratchets/check.sh`) — grep gates: no `FLOWFORGE_SIGNING_SECRET` defaults (SK-01), no f-string/`.format()`/`%` SQL (T-01/J-01/OB-01), no `==` on HMAC digests — must use `hmac.compare_digest` (NM-01), no `except Exception: pass` (J-10/JH-06/CL-04). Legitimate exceptions go in `scripts/ci/ratchets/baseline.txt` and require security-team review in the same PR.
2. **Conformance** (`tests/conformance/`) — 8 architectural invariants tagged `@invariant_p0` / `@invariant_p1`. P0 set must stay green.
3. **Signoff** (`scripts/ci/check_signoff.py`) — every audit finding (C-01 etc.) must have its acceptance test in `tests/audit_2026/test_<FINDING>_*.py` and a row in `docs/audit-2026/signoff-checklist.md`.

### Cross-runtime parity

The expression evaluator runs in both Python (`flowforge-core/src/flowforge/expr/`) and TS (`js/flowforge-renderer`). A 200-tuple fixture under `tests/cross_runtime/` is evaluated by both runtimes; any divergence fails `make audit-2026-cross-runtime`. Architecture invariant 5 pins this. Adding an expression operator means adding it on both sides plus extending the fixture.

### Test layout (E-68 / IT-05 — enforced by lint)

A `test_*.py` file lives in exactly one of:

- `tests/<layer>/` — cross-package layered suite. Layer is one of: `audit_2026`, `conformance`, `property`, `integration` (Python under `tests/integration/python/`, JS under `tests/integration/js/`), `integration/e2e`, `edge_cases`, `cross_runtime`, `chaos`, `observability`.
- `python/<pkg>/tests/[<subdir>/]` — per-package; allowed subdirs are `unit`, `ci`, `integration`, `property`, `fixtures` (most packages don't yet have all of them). **Move passing tests to `tests/ci/` for CI autodiscovery.**
- `examples/<example>/tests/` — host-project test under an example.

Anything else fails CI (`tests/audit_2026/test_E_68_test_location_convention.py`).

### Versioning (E-69 / DOC-05)

- Tier-1 (15 strategic packages): `0.1.x`, patch bump per audit-fix release; `0.2.0` reserved for the post-audit GA. Public API stable within `0.1.x`. Any SECURITY-flagged removal follows the F-7 two-version deprecation rule.
- Tier-2 (30 domain `flowforge-jtbd-*`): pinned at `0.0.1` until it flips to `package = true`, then jumps to `0.1.0` in lockstep with tier-1.

`tests/audit_2026/test_E_69_evolution_reconciliation.py` enforces both rules.

## Conventions specific to this repo

- **Tabs, not spaces** in Python (per parent project rules).
- **Async throughout** Python — engine, fire, ports are all async.
- **Pydantic v2** with `model_config = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)` for canonical models; lint-side / wire-tolerant models use `extra='allow'`.
- **UUID7 string IDs** via `uuid7str` (the local shim re-exports from `uuid6`; package `uuid_extensions` is *not* on PyPI — don't add it).
- **No mocks except for LLMs** — use `flowforge.testing.port_fakes` (real in-memory implementations) and pytest-httpserver. Postgres-backed tests use testcontainers.
- **Async tests** — plain `async def` test functions, no `@pytest.mark.asyncio` decorator. `asyncio_mode = "auto"` is set at the package `pyproject.toml` level.

## When fixing or adding to the framework

1. Find the audit finding ID (C-01, T-02, JH-04, …) if there is one — `docs/audit-fix-plan.md` is the index.
2. Per-finding test goes in `tests/audit_2026/test_<FINDING>_<short>.py` and the corresponding row in `docs/audit-2026/signoff-checklist.md` must be updated; `make audit-2026-signoff` enforces this.
3. New architectural invariant → add a marker (`@invariant_p0` or `@invariant_p1`) in `tests/conformance/`.
4. Touching the expression evaluator → update the cross-runtime fixture and both runtimes.
5. Touching JTBD generation → regenerate `examples/*/generated/` and verify byte-identical output via `scripts/check_all.sh` step 8.
6. New ratchet → add script under `scripts/ci/ratchets/`, append to `RATCHETS=()` in `check.sh`, document in `scripts/ci/ratchets/README.md`.
