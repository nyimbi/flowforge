# Raw Audit Findings

Generated: 2026-07-08

## Requested Commands

### 1. `uv run pytest python/flowforge-core/tests -q --tb=no 2>&1 | tail -5`

Initial exact command result:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
```

Rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`:

```text
........................................................................ [ 27%]
........................................................................ [ 55%]
........................................................................ [ 82%]
.............................................                            [100%]
261 passed in 0.56s
__exit_status=0
```

### 2. `uv run pytest python/flowforge-fastapi/tests -q --tb=no 2>&1 | tail -5`

Initial exact command result:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
```

Rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`:

```text
........................................................                 [100%]
56 passed in 0.63s
__exit_status=0
```

### 3. `uv run pytest python/flowforge-jtbd/tests -q --tb=no 2>&1 | tail -5`

Initial exact command result:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
```

Rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`:

```text
  /Users/nyimbiodero/src/pjs/flowforge/python/flowforge-jtbd/src/flowforge_jtbd/ai/recommender.py:565: PerformanceWarning: InMemoryEmbeddingStore is intended for tests and small catalogs (< 10K JTBDs). Use the pgvector store for production - see flowforge-jtbd/README.md § 'Vector store selection'.
    store = InMemoryEmbeddingStore()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
677 passed, 1 skipped, 1 warning in 1.49s
__exit_status=0
```

### 4. `uv run pytest python/flowforge-connectors/tests -q --tb=no 2>&1 | tail -5`

Initial exact command result:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
```

Rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`:

```text
........................................                                 [100%]
40 passed in 0.17s
__exit_status=0
```

### 5. `uv run pytest python/flowforge-outbox-pg/tests -q --tb=no 2>&1 | tail -5`

Initial exact command result:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
```

Rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`:

```text
..........................................................               [100%]
58 passed in 0.50s
__exit_status=0
```

### 6. `(cd js && pnpm -r --if-present typecheck 2>&1 | tail -10)`

```text
Scope: 7 of 8 workspace projects
flowforge-designer typecheck$ tsc --noEmit
flowforge-jtbd-editor typecheck$ tsc --noEmit
flowforge-jtbd-editor typecheck: Done
flowforge-designer typecheck: Done
flowforge-renderer typecheck$ tsc -p tsconfig.json --noEmit
flowforge-renderer typecheck: Done
flowforge-integration-tests typecheck$ tsc --noEmit
flowforge-integration-tests typecheck: Done
__exit_status=0
```

### 7. `(cd js && pnpm -r test --if-present 2>&1 | tail -10)`

Requested command:

```text
flowforge-runtime-client test:     at file:///Users/nyimbiodero/src/pjs/flowforge/js/node_modules/.pnpm/vitest@2.1.9_@types+node@22.19.17_happy-dom@20.9.0_jsdom@25.0.1_msw@2.14.3_@types+node@_e8456c9bb92a7dd7e0802844c92bf865/node_modules/vitest/dist/cli.js:8:13
flowforge-runtime-client test:     at ModuleJob.run (node:internal/modules/esm/module_job:447:25)
flowforge-runtime-client test:     at async node:internal/modules/esm/loader:646:26
flowforge-runtime-client test:     at async asyncRunEntryPointWithESMLoader (node:internal/modules/run_main:101:5)
flowforge-runtime-client test: Node.js v26.4.0
flowforge-jtbd-editor test: Failed
/Users/nyimbiodero/src/pjs/flowforge/js/flowforge-jtbd-editor:
[ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL] @flowforge/jtbd-editor@0.1.0 test: `vitest run --if-present`
Exit status 1
flowforge-designer test: Failed
__exit_status=1
```

Focused follow-up from the full output:

```text
flowforge-jtbd-editor test: CACError: Unknown option `--ifPresent`
flowforge-runtime-client test: CACError: Unknown option `--ifPresent`
flowforge-designer test: CACError: Unknown option `--ifPresent`
[ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL] @flowforge/designer@0.1.0 test: `vitest run --if-present`
__exit_status=1
```

Supporting corrected command, not one of the requested commands:

```text
(cd js && pnpm -r --if-present test)
flowforge-integration-tests test:  Test Files  7 passed (7)
flowforge-integration-tests test:       Tests  288 passed (288)
flowforge-integration-tests test: Done
__exit_status=0
```

### 8. `uv run pyright python/flowforge-core/src --pythonversion 3.11 2>&1 | tail -5`

Initial exact command result:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
```

Rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`:

```text
    "None" is not assignable to "int" (reportArgumentType)
2 errors, 0 warnings, 0 informations
WARNING: there is a new pyright version available (v1.1.408 -> v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

__exit_status=1
```

Line details from `check_all.sh` tail:

```text
/Users/nyimbiodero/src/pjs/flowforge/python/flowforge-core/src/flowforge/engine/sla_scheduler.py:125:20 - error: Argument of type "int | None" cannot be assigned to parameter "breach_seconds" of type "int" in function "__init__"
/Users/nyimbiodero/src/pjs/flowforge/python/flowforge-core/src/flowforge/engine/sla_scheduler.py:138:20 - error: Argument of type "int | None" cannot be assigned to parameter "breach_seconds" of type "int" in function "__init__"
```

### 9. `bash scripts/check_all.sh 2>&1 | tail -30`

Run with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache` and a 120s timeout:

```text
==> 4/19  pyright on each Python package
    pyright: flowforge-core
/Users/nyimbiodero/src/pjs/flowforge/python/flowforge-core/src/flowforge/engine/sla_scheduler.py
  /Users/nyimbiodero/src/pjs/flowforge/python/flowforge-core/src/flowforge/engine/sla_scheduler.py:125:20 - error: Argument of type "int | None" cannot be assigned to parameter "breach_seconds" of type "int" in function "__init__"
    Type "int | None" is not assignable to type "int"
      "None" is not assignable to "int" (reportArgumentType)
  /Users/nyimbiodero/src/pjs/flowforge/python/flowforge-core/src/flowforge/engine/sla_scheduler.py:138:20 - error: Argument of type "int | None" cannot be assigned to parameter "breach_seconds" of type "int" in function "__init__"
    Type "int | None" is not assignable to type "int"
      "None" is not assignable to "int" (reportArgumentType)
2 errors, 0 warnings, 0 informations
    pyright: flowforge-audit-pg
0 errors, 0 warnings, 0 informations
    pyright: flowforge-cli
0 errors, 0 warnings, 0 informations
    pyright: flowforge-connectors
0 errors, 0 warnings, 0 informations
[FAIL] pyright failed for one or more packages in batch: flowforge-core flowforge-audit-pg flowforge-cli flowforge-connectors
__exit_status=1
__timeout=false
```

Initial exact command without redirected `UV_CACHE_DIR` failed at `uv sync` with the same default-cache permission error:

```text
==> 1/19  uv sync (framework workspace)
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
__exit_status=2
__timeout=false
```

## Documentation Checks

### 10. `docs/flowforge-handbook.md`

```text
docs/flowforge-handbook.md: exists non-empty
93452 docs/flowforge-handbook.md
```

### 11. `docs/audit-2026/signoff-checklist.md`

Command:

```text
grep -nE "TODO|PENDING|\[ \]" docs/audit-2026/signoff-checklist.md
```

Output: no matches.

## Python Test File Counts

Command shape:

```text
for pkg in python/*; do
  if [ -d "$pkg/tests" ]; then
    find "$pkg/tests" -type f -name "test_*.py" | wc -l
  else
    echo 0
  fi
done
```

Counts:

```text
python/flowforge-audit-pg 5
python/flowforge-cli 49
python/flowforge-connectors 2
python/flowforge-core 17
python/flowforge-documents-s3 1
python/flowforge-fastapi 3
python/flowforge-jtbd 34
python/flowforge-jtbd-accounting 1
python/flowforge-jtbd-agritech 1
python/flowforge-jtbd-banking 1
python/flowforge-jtbd-compliance 1
python/flowforge-jtbd-construction 1
python/flowforge-jtbd-corp-finance 1
python/flowforge-jtbd-crm 1
python/flowforge-jtbd-ecom 1
python/flowforge-jtbd-edu 1
python/flowforge-jtbd-gaming 1
python/flowforge-jtbd-gov 1
python/flowforge-jtbd-healthcare 1
python/flowforge-jtbd-hr 1
python/flowforge-jtbd-hub 4
python/flowforge-jtbd-insurance 1
python/flowforge-jtbd-legal 1
python/flowforge-jtbd-logistics 1
python/flowforge-jtbd-media 1
python/flowforge-jtbd-mfg 1
python/flowforge-jtbd-municipal 1
python/flowforge-jtbd-nonprofit 1
python/flowforge-jtbd-platformeng 1
python/flowforge-jtbd-pm 1
python/flowforge-jtbd-procurement 1
python/flowforge-jtbd-realestate 1
python/flowforge-jtbd-restaurants 1
python/flowforge-jtbd-retail 1
python/flowforge-jtbd-saasops 1
python/flowforge-jtbd-telco 1
python/flowforge-jtbd-travel 1
python/flowforge-jtbd-utilities 1
python/flowforge-money 2
python/flowforge-notify-multichannel 2
python/flowforge-otel 3
python/flowforge-outbox-pg 3
python/flowforge-rbac-spicedb 1
python/flowforge-rbac-static 1
python/flowforge-signing-kms 2
python/flowforge-sqlalchemy 3
python/flowforge-tenancy 1
```

Zero-test packages: none.

One-test-file packages: `34`.
