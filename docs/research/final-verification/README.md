# Final Verification

Date: 2026-07-08

## Python Package Suites

| package | tests | status | count |
| --- | --- | --- | --- |
| flowforge-core | `python/flowforge-core/tests` | PASS | 261 passed |
| flowforge-fastapi | `python/flowforge-fastapi/tests` | PASS | 59 passed |
| flowforge-jtbd | `python/flowforge-jtbd/tests` | PASS | 713 passed, 1 skipped |
| flowforge-cli | `python/flowforge-cli/tests` | PASS | 897 passed, 1 skipped |
| flowforge-connectors | `python/flowforge-connectors/tests` | PASS | 40 passed |
| flowforge-outbox-pg | `python/flowforge-outbox-pg/tests` | PASS | 58 passed |
| flowforge-tenancy | `python/flowforge-tenancy/tests` | PASS | 22 passed |
| flowforge-signing-kms | `python/flowforge-signing-kms/tests` | PASS | 54 passed |
| flowforge-audit-pg | `python/flowforge-audit-pg/tests` | PASS | 78 passed, 2 skipped |
| flowforge-sqlalchemy | `python/flowforge-sqlalchemy/tests` | PASS | 43 passed, 1 skipped |
| audit_2026 | `tests/audit_2026/` | PASS | 331 passed |

## Pyright Status

PASS. `uv run pyright python/flowforge-core/src --pythonversion 3.11` exited 0.
The tailed output only reported an available Pyright update from 1.1.408 to
1.1.411.

## JS Status

PASS. `pnpm -r --if-present typecheck` completed for the JS workspaces.

PASS. `pnpm -r --if-present test` completed with 7 test files passed and 288
tests passed.

## Remaining Issues

None. All requested suites are green after fixes.

Warnings observed:

- `flowforge-jtbd` emitted one `PerformanceWarning` for the in-memory embedding store.
- `flowforge-cli` emitted Typer deprecation warnings.
- `audit_2026` emitted 60 Typer deprecation warnings.
- Pyright reported a newer available version.
