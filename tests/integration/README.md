# flowforge integration tests

Cross-package integration tests that prove the Python packages, JS workspace packages, and audit e2e flows work together end-to-end.

## Test count summary

| Category | Tests | Status |
|---|---|---|
| Backend Python (pytest) | discovered by `tests/integration/python` | passing |
| Frontend JS (vitest) | discovered by `js/flowforge-integration-tests` | passing |
| Audit e2e pytest flows | 4 | passing |
| Browser Playwright full-stack | 1 | implemented; requires browser-capable CI |

## Layout

```
tests/integration/
├── python/                        # pytest package (uv standalone)
│   ├── pyproject.toml
│   └── tests/
│       ├── conftest.py
│       ├── test_engine_to_storage.py         #1  engine + sqlalchemy storage
│       ├── test_engine_outbox_audit.py       #2  engine + outbox-pg + audit-pg
│       ├── test_fastapi_full_stack.py        #3  FastAPI HTTP + WS + all adapters
│       ├── test_jtbd_to_runtime.py           #4  JTBD bundle → engine runtime
│       ├── test_designer_authoring.py        #5  designer authoring round-trip
│       ├── test_rbac_gate_integration.py     #6  RBAC static + spicedb-fake
│       ├── test_form_spec_validation.py      #7  form_spec ajv validation
│       ├── test_replay_determinism.py        #8  lookup snapshot replay determinism
│       ├── test_saga_compensation.py         #9  saga ledger + outbox compensation
│       ├── test_parallel_regions.py          #10 fork/join token table
│       ├── test_ums_parity_via_runtime.py    #11 UMS def twins via live runtime
│       └── test_cli_pipeline.py             #16 CLI new→validate→simulate pipeline
├── e2e/
│   └── test_IT_02_e2e_three_suites.py        # fire→audit, fire→outbox, fork→replay
├── browser/
│   └── generated_backend_server.py           # stdlib HTTP bridge into generated FastAPI router
├── postgres/
│   └── test_live_postgres_fire_and_drain.py  # live PG contention/drain/audit release checks
└── js/
    └── (legacy source files — tests run from js/flowforge-integration-tests/ in workspace)

js/flowforge-integration-tests/    # actual pnpm workspace member
    ├── package.json
    ├── vitest.config.ts
    ├── vitest.setup.ts
    ├── designer-runtime-integration.spec.ts  #12 designer + runtime-client (msw)
    ├── renderer-form-flow.spec.tsx           #13 renderer FormRenderer + buildValidator
    └── step-adapter-runtime.spec.tsx         #14 step-adapters + client spy
```

## Running

```bash
# All integration tests (Python + JS + audit e2e):
bash scripts/run_integration.sh

# Python only:
cd tests/integration/python
uv run pytest tests/ -q

# JS only:
cd js/flowforge-integration-tests
pnpm test

# Audit e2e only:
uv run pytest tests/integration/e2e -q

# Browser full-stack only:
make audit-2026-browser-e2e

# UMS workflow-def parity only:
BACKEND_ROOT=/path/to/backend make audit-2026-ums-parity

# Include the browser lane in the integration runner:
RUN_BROWSER_E2E=1 bash scripts/run_integration.sh

# Live Postgres release checks:
FLOWFORGE_TEST_PG_URL=postgresql://... make audit-2026-live-postgres

# All external release checks:
BACKEND_ROOT=/path/to/backend \
FLOWFORGE_TEST_PG_URL=postgresql://... \
make audit-2026-release-external
```

The `run_integration.sh` script is wired into `scripts/check_all.sh` as Step 13.

## Adapter strategy

Every test runs against **real adapters** — no mocks of the thing under test:

| Adapter | Test strategy |
|---|---|
| flowforge-sqlalchemy | aiosqlite in-memory (dialect-agnostic) |
| flowforge-audit-pg | aiosqlite in-memory (same PgAuditSink code path) |
| flowforge-outbox-pg | aiosqlite + `sqlite_compat=True` DrainWorker |
| flowforge-rbac-static | real StaticRbac in-process |
| flowforge-rbac-spicedb | FakeSpiceDBClient (in-memory, same Protocol) |
| flowforge-tenancy | SingleTenantGUC (no GUC issued on sqlite) |
| flowforge-money | StaticMoneyPort + StaticRateProvider |
| flowforge-signing-kms | HmacDevSigning (dev-hmac, no KMS) |
| flowforge-documents-s3 | NoopDocumentPort |
| flowforge-notify-multichannel | FakeInAppAdapter |
| @flowforge/runtime-client (JS) | msw v2 node handler (test #12) / vi.spyOn (test #14) |

## Deferred items

### Test #15: Playwright e2e full-stack (`e2e_full_stack.spec.ts`)

Implemented as a browser-capable release lane. `scripts/run_browser_full_stack.sh`
starts:

- the generated insurance-claim FastAPI router through `tests/integration/browser/generated_backend_server.py`;
- the generated frontend Vite harness with `NEXT_PUBLIC_FLOWFORGE_API_BASE_URL`
  pointing at that backend; and
- Playwright Chromium via the `browser-full-stack` project in
  `tests/visual_regression/playwright.config.ts`.

The spec location is `tests/visual_regression/tests/e2e_full_stack.spec.ts`.
It fills the generated claim-intake form in a real browser, posts `submit`
and `approve` over HTTP, and verifies the generated router received
`Idempotency-Key`, `X-Tenant-Id`, the expected event bodies, and the
`review` -> `done` state responses.

This lane still requires a Chromium-capable environment. It does not replace
the separate live-Postgres release check, which must run against the durable
database stack.

### UMS parity release check

`make audit-2026-ums-parity` is a fail-closed external release target for
adjacent UMS checkouts. It requires `BACKEND_ROOT` to point at the UMS
`backend/` directory and runs `uv run pytest tests/test_workflow_def_parity.py
-v --tb=short` there. Standalone `scripts/check_all.sh` still skips UMS parity
with an explicit reason when `BACKEND_ROOT` is absent; release qualification
must use this Make target instead.

### Live Postgres release checks

`make audit-2026-live-postgres` is a fail-closed external release target. It
requires `FLOWFORGE_TEST_PG_URL` (or `FLOWFORGE_LIVE_PG_URL`) pointing at a
disposable Postgres database. The test fixture creates a unique temporary
schema and drops only that schema at teardown.

Coverage:

- stale multi-session snapshot writes raise `SnapshotConflict`;
- rows produced by `SqlAlchemySnapshotStore.fire_and_commit(...)` drain through
  the Postgres `FOR UPDATE SKIP LOCKED` worker path; and
- interleaved audit rows across tenants verify through the Postgres audit sink;
  and
- tenant audit reads can use the `(tenant_id, ordinal)` index under a live
  Postgres query plan.

### External release bundle

`make audit-2026-release-external` runs the browser-backed release checks that
cannot be honestly completed in a standalone, browser-sandboxed checkout:
DOM visual baselines, browser Playwright full-stack, UMS workflow-def parity,
and live Postgres contention/drain/audit verification. It rejects
`VISREG_ALLOW_SKIP=1` and `BROWSER_E2E_ALLOW_SKIP=1`.

### Project-level Playwright runner (resolved in v0.3.0 W3)

The Playwright runner is now wired up under `tests/visual_regression/` per ADR-001 (`docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md`). It serves the visual regression CI gate (item 21) — DOM-snapshot byte-equality as the CI-blocking artifact and pixel SSIM as a nightly advisory.

The runner is structurally complete and fail-closed by default when DOM baselines are missing. Baseline generation still requires an environment where Playwright can launch Chromium. See `tests/visual_regression/README.md` for the full status.
