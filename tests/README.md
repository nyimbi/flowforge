# framework/tests — layered audit-2026 test suites

This directory holds the cross-package test suites that exercise the
flowforge framework as a whole. Per-package unit tests live alongside
their source under `framework/python/<pkg>/tests/`. The lint at
`tests/audit_2026/test_E_68_test_location_convention.py` enforces both
conventions; CI runs it as part of `make audit-2026-unit`.

## The convention (E-68 / IT-05)

A `test_*.py` file under `framework/` must live in exactly one of:

| Root | Purpose | Example |
|---|---|---|
| `framework/tests/<layer>/` | Cross-package layered suite. Layer is one of the 8 listed below. | `framework/tests/audit_2026/test_C_01_*.py` |
| `framework/python/<pkg>/tests/[<subdir>/]` | Per-package suite. Subdir ∈ `unit / ci / integration / property / fixtures`, or files directly in `tests/`. | `framework/python/flowforge-core/tests/unit/test_engine_fire.py` |
| `framework/examples/<example>/tests/` | Host-project test under an example project. | `framework/examples/insurance_claim/tests/test_e2e.py` |

Anything else fails CI. The `templates/`, `generated/`, `__pycache__/`,
`.venv/`, `node_modules/` segments are explicitly skipped (third-party
or scaffolded code that the framework ships TO host apps).

## The 8 audit-2026 layers

Each layer corresponds to one entry in `make audit-2026-*`
(see `framework/docs/audit-fix-plan.md` §5.2):

| Layer | Make target | Purpose |
|---|---|---|
| `audit_2026` | `make audit-2026-unit` | Per-finding regression tests named `test_<FINDING_ID>_<short>.py`; one file per audit finding (C-01, T-02, JH-04, …). Every audit finding lands its acceptance test here. |
| `conformance` | `make audit-2026-conformance` | The 8 architectural invariants of arch §17. Tests carry the `@invariant_p0` / `@invariant_p1` markers; `make audit-2026-conformance-p0` runs only the P0 set. Required-green on every PR. |
| `property` | `make audit-2026-property` | Hypothesis property tests — round-trip / commutativity / determinism invariants. 5 properties shipped per E-44. |
| `integration` | `make audit-2026-integration` | Cross-package integration tests using real Postgres / SQLite via testcontainers. Runs the full fire→audit→outbox→saga path. |
| `integration/e2e` | `make audit-2026-e2e` | End-to-end suites covering the 3 ship-blocker flows: fire→audit→verify, fire→outbox→ack, fork→migrate→replay (E-45). |
| `edge_cases` | `make audit-2026-edge` | The 9 edge-case bank classes (empty bundle, max-size lockfile, year-boundary timezone, hash-chain bit-flip, …) per E-64. |
| `cross_runtime` | `make audit-2026-cross-runtime` | TS↔Python evaluator parity fixture (200 inputs); paired with `framework/js/flowforge-integration-tests/expr-parity.test.ts`. Pins architecture invariant 5. |
| `chaos` | `make audit-2026-chaos` | Fault-injection suites — crash mid-fire, crash mid-outbox, crash mid-compensation. Wires `flowforge-jtbd` fault injector. |
| `observability` | `make audit-2026-observability` | Synthetic metric injection + `promtool test rules`; PromQL alert-rule self-tests live under `tests/observability/promql/`. |

## Per-package conventions

Each `framework/python/<pkg>/tests/` contains:

| Subdir | Convention |
|---|---|
| `tests/` (bare) | Mixed unit / integration tests when the package is small. |
| `tests/unit/` | Fast unit tests, no external services. |
| `tests/ci/` | Subset autodiscovered by repo-wide CI (per project CLAUDE.md: "Move passing tests to `tests/ci/` for CI autodiscovery"). |
| `tests/integration/` | Tests that need testcontainers / pgvector / real adapters. |
| `tests/property/` | Per-package hypothesis properties (rare; most live at `tests/property/` repo-level). |
| `tests/fixtures/` | Shared test fixtures (golden bytes, sample bundles). |

## Adding a new test

1. Decide whether your test is per-package (touches one workspace pkg)
   or cross-package (exercises the framework as a whole).
2. Per-package → drop in the matching `framework/python/<pkg>/tests/`
   subdir. Cross-package → drop in the matching `framework/tests/<layer>/`.
3. Run `make audit-2026-unit` (or just
   `uv run pytest framework/tests/audit_2026/test_E_68_test_location_convention.py`)
   to confirm the lint accepts the location.
4. If you genuinely need a new layer, extend `_AUDIT_2026_LAYERS` in the
   lint AND add a row to the table above. New layers need a `make
   audit-2026-<name>` target in the repo root Makefile.
