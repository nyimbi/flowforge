# flowforge integration tests

Cross-package integration tests that prove all 18 flowforge packages (13 PyPI + 5 npm) work together end-to-end.

## Test count summary

| Category | Tests | Status |
|---|---|---|
| Backend Python (pytest) | 24 | passing |
| Frontend JS (vitest) | 16 | passing |
| Playwright e2e | — | deferred (see below) |
| **Total** | **40** | **passing** |

## Layout

```
framework/tests/integration/
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
└── js/
    ├── README.md  (this file)
    └── (source files — tests run from js/flowforge-integration-tests/ in workspace)

framework/js/flowforge-integration-tests/    # actual pnpm workspace member
    ├── package.json
    ├── vitest.config.ts
    ├── vitest.setup.ts
    ├── designer-runtime-integration.spec.ts  #12 designer + runtime-client (msw)
    ├── renderer-form-flow.spec.tsx           #13 renderer FormRenderer + buildValidator
    └── step-adapter-runtime.spec.tsx         #14 step-adapters + client spy
```

## Running

```bash
# All integration tests (Python + JS):
bash framework/scripts/run_integration.sh

# Python only:
cd framework/tests/integration/python
uv run pytest tests/ -q

# JS only:
cd framework/js/flowforge-integration-tests
pnpm test
```

The `run_integration.sh` script is wired into `framework/scripts/check_all.sh` as **Step 10/11**.

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

### Test #15: Playwright e2e full-stack (`e2e-full-stack.spec.ts`)

**Deferred** — requires docker-compose with PostgreSQL + the Next.js dev server running simultaneously. The test scenario is documented and `run_integration.sh` detects docker-compose availability and skips cleanly when absent.

To enable in CI: add a `docker-compose.yml` under `framework/tests/integration/` that spins up `postgres:16`, runs Alembic migrations, starts the FastAPI backend, and starts the Next.js frontend. Then set `SKIP_E2E=0` in the CI environment.

Placeholder spec location: `framework/tests/integration/js/e2e-full-stack.spec.ts` (not yet created — tracked as a follow-up).

### Project-level Playwright runner (resolved in v0.3.0 W3)

The Playwright runner is now wired up under `tests/visual_regression/` per ADR-001 (`docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md`). It serves the visual regression CI gate (item 21) — DOM-snapshot byte-equality as the CI-blocking artifact and pixel SSIM as a nightly advisory.

The runner is structurally complete but skip-with-clear-reason while `pnpm install` is blocked on the pre-existing pnpm-ignored-builds issue. Once that lands, baseline files seed via `pnpm --filter @flowforge/visual-regression update-baselines`. See `tests/visual_regression/README.md` for the full status.
