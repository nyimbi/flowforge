# Package readiness progress - 2026-05-20

Objective: move Flowforge toward a fully capable, secure, reliable, PyPI-ready
package with repeated design/code review, strong verification, and a detailed
progress trail.

## Slice completed

This pass closed a verified core/CLI readiness slice:

- Raised `flowforge-core` package test coverage to 100% statement and branch
  coverage.
- Fixed an i18n generator correctness bug found during code audit: when
  `project.languages` starts with a non-English locale but still declares
  `en`, `en` now remains the populated source/fallback catalog and non-English
  catalogs receive sidecar translations or empty mirrors.
- Regenerated checked-in example outputs so the deterministic regen gate stays
  byte-identical.
- Removed a dead no-op branch in the workflow validator.
- Clarified `InvalidTargetError` wording and audit-plan C-08 docs to match the
  implemented `set` target contract.
- Added `.omc/` and `.omx/` to `.gitignore` so local OMX/agent state cannot be
  accidentally committed.

## Code review audits

Code audit 1 - core engine/evaluator:

- Result: no blocking findings.
- Follow-up found: C-08 docs contradicted `_set_dotted` behavior.
- Action: fixed C-08 docs and `InvalidTargetError` wording.

Code audit 2 - adapters:

- Result: no blocking findings in the reviewed diff.
- Verification fallback used ruff/pyright because the diagnostic tool was not
  available to the reviewer.

Code audit 3 - CLI/generators:

- Result: confirmed release-relevant i18n fallback bug.
- Action: fixed source/fallback locale selection, added regression coverage,
  regenerated example outputs.

Code audit 4 - release/packaging:

- Result: one low-severity wording issue in `InvalidTargetError`.
- Action: fixed.

Code audit 5 - JS/UI/generated frontend:

- Result: no additional changed-output defect found after direct review of the
  generated `useT.ts` diff and full JS gates.
- Note: one JS/UI subagent did not return a usable report and was closed; the
  changed JS output is still covered by the broad local gate below.

## Verification evidence

- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/flowforge-core/tests -q --cov=flowforge --cov-report=term-missing --cov-fail-under=100`
  - Result: `181 passed`; required 100% coverage reached.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/flowforge-cli/tests/test_i18n_generator.py tests/property/generators/test_i18n_properties.py -q --tb=short`
  - Result: `43 passed`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-i18n-coverage`
  - Result: `0 error(s), 0 warning(s) across 3 example(s)`.
- Targeted `ruff check` and `pyright` on touched core/CLI files.
  - Result: clean; pyright `0 errors, 0 warnings`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache VISREG_ALLOW_SKIP=1 bash scripts/check_all.sh`
  - Result: `U24 gate PASSED`; 46 Python packages, 7 JS packages, 2786 total
    tests/assertions, deterministic regen byte-identical for all 3 examples.
  - DOM browser-backed cases hit the known local macOS Chromium
    `MachPortRendezvousServer` permission denial and were treated as the
    documented local visual skip; metadata DOM checks ran and passed.

## Remaining work

- Run the requested five design-review audits and close any findings.
- Continue expanding package-level 100% coverage beyond `flowforge-core`.
- Keep repeating review/fix/verify/commit cycles until package publishing
  evidence is complete.

## Design review audits

Design audit 1 - architecture and package boundaries:

- Result: no new blocker found in this slice.
- Evidence reviewed: the core remains documented as I/O-free with host-wired
  ports, the package surface stays split across 16 shipping packages plus
  workspace-only domain packages, and the conformance suite remains the
  standing architectural invariant contract.
- Note: one attempted architecture subagent lane shut down without a usable
  mailbox report; direct review supplied the evidence for this audit.

Design audit 2 - API/CLI developer experience:

- Result: no new blocker found after wheel-level CLI smoke.
- Evidence reviewed: `flowforge --help` from a clean wheel install exposes the
  scaffold, validation, simulation, audit, JTBD, pre-upgrade, migration-safety,
  bundle-diff, and tutorial surfaces without import failures.

Design audit 3 - generated app UX:

- Result: no new blocker found.
- Evidence reviewed: generated frontend design supports the legacy skeleton
  path for byte-stable old bundles and an opt-in real `FormRenderer` path with
  form specs, validators, conditional visibility, PII reveal controls, runtime
  client wiring, idempotency keys, and tenant headers. Existing tests cover both
  paths and byte determinism.

Design audit 4 - PyPI packaging and release design:

- Finding: PyPI artifact readiness was documented as a manual build/check/smoke
  sequence but was not exposed as a first-class repeatable release target.
- Action: added `scripts/audit_2026/pypi_build_smoke.py`, wired
  `make audit-2026-pypi-build`, included it in the local and external release
  gates, and updated `docs/release/PUBLISHING.md` to make the target canonical.

Design audit 5 - operations, security, and reliability:

- Result: no new blocker found in this slice.
- Evidence reviewed: the external release gate already fails closed on local
  skip escapes, visual/browser proof gaps, polish-copy sidecar gaps, optional
  UMS parity, and live Postgres checks; the new PyPI target now extends that
  release gate to package artifact build/check/smoke evidence.

## Design-audit verification evidence

- Manual package proof before adding the target:
  - Built the 16 strategic packages into
    `/private/tmp/flowforge-pypi-readiness-dist`.
  - `uv run --with twine python -m twine check ...` passed for all 16 wheels
    and all 16 sdists.
  - Clean venv install of `flowforge-cli` from the built artifacts succeeded;
    `/private/tmp/flowforge-cli-wheel-smoke/bin/flowforge --help` printed the
    CLI help without `ModuleNotFoundError`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`
  - Result: built 32 artifacts for 16 packages, `twine check` passed for all,
    clean wheel smoke installed `flowforge-cli`, and `flowforge --help` ran.
- `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`
  - Result: `16 passed`.
- `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`
  - Result: clean.

## Remaining work after design-audit slice

- Continue broader package-level coverage work beyond `flowforge-core`.
- Run additional code/design review loops as new package-surface changes land.
- External release qualification still requires a browser-capable environment
  for visual DOM/browser E2E and live Postgres checks; local macOS sandbox runs
  can document skips but cannot replace that release evidence.

## Package coverage slice - flowforge-tenancy

- Baseline measurement:
  - `flowforge-tenancy`: `11 passed`, 95% statement coverage before this slice.
  - Nearby small package baselines measured for prioritization:
    `flowforge-rbac-static` 90%, `flowforge-money` 98%, `flowforge-otel` 96%.
- Action: added focused resolver contract coverage for:
  - `NoTenancy.elevated_scope()` no-op behavior.
  - `SingleTenantGUC.current_tenant()`.
  - Duck-typed sessions that intentionally omit `in_transaction()`.
  - Async `session.execute(...)` results returned by SQLAlchemy-like sessions.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_tenancy --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-tenancy`: `14 passed`, 100% statement and branch
    coverage.
  - `uv run ruff check python/flowforge-tenancy/tests/test_resolvers.py`:
    clean.
  - `uv run pyright python/flowforge-tenancy/tests/test_resolvers.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-money

- Baseline measurement:
  - `flowforge-money`: `44 passed`, 98% statement coverage before this slice.
- Action: added focused `Money` value-object tests for:
  - Division by an unsupported non-Decimal/non-int factor.
  - Equality comparison against a non-`Money` object.
  - Cleaned existing different-currency addition assertion so pyright sees the
    raised expression as intentionally evaluated.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_money --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-money`: `45 passed`, 100% statement and branch
    coverage.
  - `uv run ruff check python/flowforge-money/tests/test_static.py`: clean.
  - `uv run pyright python/flowforge-money/tests/test_static.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-otel

- Baseline measurement:
  - `flowforge-otel`: `10 passed`, 96% statement coverage before this slice.
- Action: added focused OTel adapter tests for:
  - Lazy creation of custom histogram instruments beyond the pre-created
    standard histogram set.
  - `OpenTelemetryNotInstalled` message and `missing_module` payload.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_otel --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-otel`: `12 passed`, 100% statement and branch
    coverage.
  - `uv run ruff check python/flowforge-otel/tests/test_metrics_adapter.py`:
    clean.
  - `uv run pyright python/flowforge-otel/tests/test_metrics_adapter.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-rbac-static

- Baseline measurement:
  - `flowforge-rbac-static`: `9 passed`, 90% statement coverage before this
    slice.
- Action: added focused loader safety tests for:
  - Accepting config paths that resolve inside an explicit `allowed_root`.
  - Rejecting config paths that resolve outside `allowed_root`.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_rbac_static --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-rbac-static`: `11 passed`, 100% statement and
    branch coverage.
  - `uv run ruff check python/flowforge-rbac-static/tests/test_resolver.py`:
    clean.
  - `uv run pyright python/flowforge-rbac-static/tests/test_resolver.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-rbac-spicedb

- Baseline measurement:
  - `flowforge-rbac-spicedb`: `15 passed`, 96% statement coverage before this
    slice.
  - Larger nearby packages measured for prioritization:
    `flowforge-signing-kms` 72%, `flowforge-documents-s3` 68%, and
    `flowforge-notify-multichannel` 85%.
- Action: added focused SpiceDB adapter tests for:
  - Flat `LookupSubjects` response shapes and empty subject ids.
  - Fake client revoke/delete behavior.
  - Cached zedtoken reset and no-token write responses.
  - Duplicate and wrong-subject-type lookup suppression in the fake client.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_rbac_spicedb --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-rbac-spicedb`: `23 passed`, 100% statement and
    branch coverage.
  - `uv run ruff check python/flowforge-rbac-spicedb/tests/test_resolver.py`:
    clean.
  - `uv run pyright python/flowforge-rbac-spicedb/tests/test_resolver.py`:
    `0 errors, 0 warnings`.

## Closed-package coverage ratchet

- Action: added `scripts/audit_2026/closed_package_coverage.py` and
  `make audit-2026-closed-package-coverage`.
- Scope currently locked at 100% statement and branch coverage:
  `flowforge-tenancy`, `flowforge-rbac-static`,
  `flowforge-rbac-spicedb`, `flowforge-money`, and `flowforge-otel`.
- Release wiring: added the ratchet to `audit-2026-release-local` so completed
  package coverage cannot silently regress during local release qualification.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`
    passed for all five closed packages.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `uv run ruff check scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-signing-kms HMAC backend

- Baseline measurement:
  - `flowforge-signing-kms`: `26 passed`, 72% package coverage before this
    slice.
  - `flowforge_signing_kms.hmac_dev`: 77% coverage before this slice.
- Action: added focused HMAC signing tests for:
  - Env-secret fallback with default key id.
  - Explicit opt-in to the insecure legacy default secret, including warning
    emission and explicit key-id preservation.
  - Key-map constructor validation for empty maps, missing current key, unknown
    current key, and mixed constructor forms.
  - Sorted `known_key_ids()`.
- Verification:
  - `uv run pytest tests/test_hmac.py -q --cov=flowforge_signing_kms.hmac_dev --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-signing-kms`: `19 passed`, 100% statement and
    branch coverage for the HMAC backend.
  - `uv run pytest tests -q --cov=flowforge_signing_kms --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-signing-kms`: `32 passed`, package coverage now
    80%; remaining gaps are in cloud-KMS branches.
  - `uv run ruff check python/flowforge-signing-kms/tests/test_hmac.py`:
    clean.
  - `uv run pyright python/flowforge-signing-kms/tests/test_hmac.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-signing-kms cloud KMS

- Baseline after HMAC slice:
  - `flowforge-signing-kms`: `32 passed`, 80% package coverage.
- Action: added live-cloud-free AWS/GCP KMS adapter tests for:
  - AWS HMAC and asymmetric sign/verify through injected stub clients.
  - AWS transient, unknown-key, permanent-invalid, and already-domain-error
    classification paths.
  - AWS import-guard and endpoint-url constructor wiring.
  - GCP injected-client and imported-client constructor paths.
  - GCP transient, unknown-key, permanent-invalid, unclassified, and
    already-domain-error paths.
- Result: `flowforge-signing-kms` now reaches 100% statement and branch
  coverage and has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_signing_kms --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-signing-kms`: `48 passed`.
  - `uv run ruff check python/flowforge-signing-kms/tests/test_kms.py python/flowforge-signing-kms/tests/test_hmac.py`:
    clean.
  - `uv run pyright python/flowforge-signing-kms/tests/test_kms.py python/flowforge-signing-kms/tests/test_hmac.py`:
    `0 errors, 0 warnings`.

## Package coverage slice - flowforge-outbox-pg

- Baseline measurement:
  - `flowforge-outbox-pg`: `38 passed`, 90% package coverage.
  - Remaining uncovered risk was concentrated in PostgreSQL-native worker
    helpers, reconnect logging branches, rare UUID fallback, row parsing edges,
    and duplicate backend introspection.
- Action: added focused tests for:
  - PostgreSQL `FOR UPDATE SKIP LOCKED` claim SQL and native asyncpg-style
    execute/fetch helpers without needing a live database.
  - Mapping-row parsing, naive datetime normalization, invalid datetime
    fallback, and non-string UTF-8 truncation inputs.
  - `DispatchError` after a handler disappears between `has_handler` and
    dispatch.
  - Failed reconnect logging and non-reconnect run-loop error logging.
  - Duplicate backend suppression in registry introspection.
- Result: `flowforge-outbox-pg` now reaches 100% statement and branch coverage
  and has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_outbox_pg --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-outbox-pg`: `47 passed`.
  - `uv run ruff check python/flowforge-outbox-pg/tests/test_worker.py python/flowforge-outbox-pg/tests/test_registry.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-outbox-pg/tests/test_worker.py python/flowforge-outbox-pg/tests/test_registry.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all seven closed packages.
