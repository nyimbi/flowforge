# Flowforge Audit 2026 Status

Generated: 2026-07-08  
Working directory: `/Users/nyimbiodero/src/pjs/flowforge`

## Environment Note

The first exact `uv run ...` invocations failed in this managed sandbox before tests could start:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

To get package-level audit evidence, the same `uv` commands were rerun with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`. The status below uses that rerun and calls out the environment issue separately.

## Summary

- Python pytest status: all five requested package suites passed under the writable `UV_CACHE_DIR` rerun, with `1092 passed` and `1 skipped` total.
- JS typecheck: passed for the workspace packages reached by `pnpm -r --if-present typecheck`.
- Requested JS test command: failed because `pnpm -r test --if-present` forwarded `--if-present` to Vitest as `--ifPresent`.
- Supporting JS test rerun with corrected flag order, `pnpm -r --if-present test`, passed `288` tests.
- Pyright findings: `2` errors, both in `python/flowforge-core/src/flowforge/engine/sla_scheduler.py`.
- `scripts/check_all.sh`: completed before 120s but failed at the pyright batch because of the same core pyright errors.
- Audit checklist: no `TODO`, `PENDING`, or unchecked `- [ ]` items found.
- Python packages with zero `test_*.py` files: none.

## Python Test Results

| Package command | Status | Count | Notes |
| --- | --- | ---: | --- |
| `uv run pytest python/flowforge-core/tests -q --tb=no` | Pass | 261 passed | Exact command hit sandbox `uv` cache permission first; rerun used writable cache. |
| `uv run pytest python/flowforge-fastapi/tests -q --tb=no` | Pass | 56 passed | Rerun used writable cache. |
| `uv run pytest python/flowforge-jtbd/tests -q --tb=no` | Pass | 677 passed, 1 skipped | One `PerformanceWarning` from `InMemoryEmbeddingStore`. |
| `uv run pytest python/flowforge-connectors/tests -q --tb=no` | Pass | 40 passed | Rerun used writable cache. |
| `uv run pytest python/flowforge-outbox-pg/tests -q --tb=no` | Pass | 58 passed | Rerun used writable cache. |

## JS Status

| Command | Status | Evidence |
| --- | --- | --- |
| `(cd js && pnpm -r --if-present typecheck)` | Pass | `flowforge-designer`, `flowforge-jtbd-editor`, `flowforge-renderer`, and `flowforge-integration-tests` reported `Done`; exit status `0`. |
| `(cd js && pnpm -r test --if-present)` | Fail | Vitest received `--ifPresent` and errored with `CACError: Unknown option --ifPresent`; exit status `1`. |
| `(cd js && pnpm -r --if-present test)` | Pass | Supporting rerun passed `7` JS test files and `288` tests; exit status `0`. |

No separate JS build command was part of this audit.

## Pyright

`uv run pyright python/flowforge-core/src --pythonversion 3.11` found `2` errors:

- `python/flowforge-core/src/flowforge/engine/sla_scheduler.py:125`: `int | None` passed where `int` is required for `breach_seconds`.
- `python/flowforge-core/src/flowforge/engine/sla_scheduler.py:138`: `int | None` passed where `int` is required for `breach_seconds`.

## Check All

`bash scripts/check_all.sh` was run with a 120 second cap and did not time out. It failed at step `4/19`, the pyright batch. The tail showed the same two `flowforge-core` pyright errors, followed by zero-error pyright results for `flowforge-audit-pg`, `flowforge-cli`, and `flowforge-connectors`.

## Documentation And Checklist

- `docs/flowforge-handbook.md`: exists and is non-empty (`93452` bytes).
- `docs/audit-2026/signoff-checklist.md`: no outstanding `TODO`, `PENDING`, or unchecked `- [ ]` matches found.

## Python Test File Coverage

Every package under `python/*` has at least one `test_*.py` file under its `tests` directory. Zero-test packages found: none.

Coverage depth remains uneven: `34` Python packages have exactly one `test_*.py` file. Full counts are in `thinking.md`.

## Top 5 Priority Gaps

1. Fix the two `flowforge-core` pyright errors in `sla_scheduler.py` so `breach_seconds` cannot be `None` at the typed constructor boundary.
2. Correct JS recursive test invocation in audit/CI usage to `pnpm -r --if-present test`; the requested ordering fails before Vitest can run tests.
3. Re-run `scripts/check_all.sh` after the pyright fix and confirm all `19` stages complete, since this audit only got as far as the pyright batch.
4. Make `uv` cache location explicit for sandboxed or managed runners, or document the required writable cache setup, because the exact `uv run` commands failed against the default user cache here.
5. Raise coverage depth for the `34` Python packages that currently have only one `test_*.py`, prioritizing shared adapters, catalog/domain packages, and authorization/tenancy surfaces.
