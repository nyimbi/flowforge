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

## Package coverage slice - flowforge-documents-s3

- Baseline measurement:
  - `flowforge-documents-s3`: `23 passed`, 68% package coverage.
  - Remaining uncovered risk was concentrated in document id rejection,
    Office ZIP structural sniffing, SQLite index persistence branches,
    presigned POST policy limits, lazy boto3 client construction, and legacy
    alias warning paths.
- Action: added focused tests for:
  - Invalid `doc_id` shapes, deprecated alias warnings, and unknown attribute
    failures.
  - DOCX/XLSX/PPTX/generic ZIP sniffing, invalid ZIP handling, libmagic
    success/empty-result fallbacks, and Office content-type manifest mismatch.
  - SQLite index prefix escaping, missing metadata, duplicate/multi-subject
    attachment behavior, naive datetime normalization, and delete outcomes.
  - Presigned POST content-type and size policies, plus explicit boto3 client
    construction when no client is supplied.
- Result: `flowforge-documents-s3` now reaches 100% statement and branch
  coverage and has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_documents_s3 --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-documents-s3`: `32 passed`.
  - `uv run ruff check python/flowforge-documents-s3/tests/test_port.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-documents-s3/tests/test_port.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all eight closed packages.

## Package coverage slice - flowforge-notify-multichannel

- Baseline measurement:
  - `flowforge-notify-multichannel`: `58 passed`, 85% package coverage.
  - Remaining uncovered risk was concentrated in URL allow-list helper
    branches, SMTP HTML and provider exception paths, default `httpx`
    client-context paths, request-error handling for HTTP transports,
    webhook signature rejection shapes, and timezone fallback observability.
- Action: added focused tests for:
  - Webhook URL parsing, private-host rejection, no-allow-list rejection, and
    HMAC signature malformed/valid/invalid comparisons.
  - SMTP HTML multipart delivery and `aiosmtplib.SMTPException` handling.
  - SES session-token signing, injected-client `RequestError` failures, and
    default `httpx.AsyncClient` success paths across SES, Twilio, FCM,
    webhook, and Slack.
  - Router fallback to UTC for an unknown timezone while preserving the
    original exception in `last_tz_fallback`.
- Result: `flowforge-notify-multichannel` now reaches 100% statement and
  branch coverage and has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_notify_multichannel --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-notify-multichannel`: `68 passed`.
  - `uv run ruff check python/flowforge-notify-multichannel/tests/test_transports.py python/flowforge-notify-multichannel/tests/test_router.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-notify-multichannel/tests/test_transports.py python/flowforge-notify-multichannel/tests/test_router.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all nine closed packages.

## Package coverage slice - flowforge-audit-pg

- Baseline measurement:
  - `flowforge-audit-pg`: `39 passed`, `2 skipped`, 45% package coverage.
  - Remaining uncovered risk was concentrated in canonical golden fixture
    integrity helpers, ordinal backfill migration control flow, hash-chain
    serialization edge cases, and sink branches for transactional inserts,
    partial verification, legacy rows, PostgreSQL trigger/lock behavior, and
    redaction no-op handling.
- Action: added focused tests for:
  - Golden bundle build/write/load, tamper detection, CLI write/verify, row
    recomputation, invalid ISO-like payload preservation, and fallback command
    handling.
  - Ordinal backfill add-column/backfill/add-constraint/verify steps via fake
    async engines, including verify failure exit codes and CLI argument
    parsing.
  - UUID/Decimal canonical serialization, unknown object rejection, UUID4
    fallback when `uuid6` is unavailable, PostgreSQL trigger/advisory-lock
    branches, transactional `record_in_connection`, chunked/since verification,
    legacy row skipping, prev-hash mismatch detection, null payload redaction,
    no-op redaction, and datetime helper edge inputs.
- Result: `flowforge-audit-pg` now reaches 100% statement and branch coverage
  and has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_audit_pg --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-audit-pg`: `68 passed`, `2 skipped`.
  - `uv run ruff check python/flowforge-audit-pg/tests/test_hash_chain.py python/flowforge-audit-pg/tests/test_golden.py python/flowforge-audit-pg/tests/test_migration.py python/flowforge-audit-pg/tests/test_sink.py python/flowforge-audit-pg/src/flowforge_audit_pg/migrations/audit_ordinal_backfill.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-audit-pg/tests/test_hash_chain.py python/flowforge-audit-pg/tests/test_golden.py python/flowforge-audit-pg/tests/test_migration.py python/flowforge-audit-pg/tests/test_sink.py python/flowforge-audit-pg/src/flowforge_audit_pg/migrations/audit_ordinal_backfill.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all ten closed packages.

## Package coverage slice - flowforge-core and remaining package map

- Baseline measurement:
  - `flowforge-core`: `181 passed`, already at 100% statement and branch
    coverage.
  - Remaining strategic package measurements for prioritization:
    `flowforge-fastapi` `27 passed`, 89%; `flowforge-sqlalchemy`
    `20 passed`, `1 skipped`, 76%; `flowforge-cli` initially failed when run
    from `python/flowforge-cli` because
    `test_upgrade_deps_discovers_workspace_from_package_dir` assumed the repo
    root as CWD; `flowforge-jtbd` `564 passed`, `1 skipped`, 93%;
    `flowforge-jtbd-hub` `65 passed`, 87%.
- Action:
  - Added `flowforge-core` to the closed-package coverage ratchet because its
    current package-local suite already proves 100% statement and branch
    coverage.
  - Fixed the CLI package-local test by deriving `REPO_ROOT` from
    `tests/test_other_commands.py` instead of assuming the process starts at
    the checkout root.
- Result:
  - The closed-package coverage ratchet now covers 11 strategic shipping
    packages.
  - `flowforge-cli` package-local tests now pass from its own package
    directory; package coverage remains a separate open gap at 71%.
- Verification:
  - `uv run pytest tests/test_other_commands.py::test_upgrade_deps_discovers_workspace_from_package_dir -q`
    from `python/flowforge-cli`: `1 passed`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `640 passed`, package coverage 71%.
  - `uv run pytest tests -q --cov=flowforge --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-core`: `181 passed`.
  - `uv run ruff check python/flowforge-cli/tests/test_other_commands.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-cli/tests/test_other_commands.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all eleven closed packages.

## Code-review remediation slice - FastAPI SQLAlchemy runtime store

- Audit finding:
  - The runtime router's SQL-backed path was not actually covered: the
    full-stack FastAPI test documented `SqlAlchemySnapshotStore` but never
    overrode `get_instance_store()`, so `POST /instances`, `POST
    /instances/{id}/events`, and `GET /instances/{id}` used the in-memory
    `InstanceStore`.
  - Wiring a real `SqlAlchemySnapshotStore` directly would fail because the
    FastAPI runtime expected `put(instance, tenant_id=...)` and
    `get_for_tenant(...)`, while the SQLAlchemy adapter only exposed
    lower-level snapshot `put(instance)` and `get(instance)` methods.
  - Instance creation also lacked the durable `workflow_instances` owner row
    required by the SQLAlchemy snapshot adapter before snapshots/events can be
    written.
- Action:
  - Added an explicit runtime-store creation method to the FastAPI in-memory
    `InstanceStore` and changed the runtime router to call
    `create_instance(instance, workflow_def=..., tenant_id=...)`.
  - Extended `SqlAlchemySnapshotStore` with `create_instance(...)`,
    `get_for_tenant(...)`, and tenant-aware `put(..., tenant_id=...)`.
    `create_instance(...)` now creates the `workflow_instances` row and the
    initial `workflow_instance_snapshots` row in one commit.
  - Rewired `tests/integration/python/tests/test_fastapi_full_stack.py` to
    override `get_instance_store()` with `SqlAlchemySnapshotStore` and assert
    durable `WorkflowInstance`, `WorkflowInstanceSnapshot`, `WorkflowEvent`,
    `OutboxMessage`, and audit rows.
  - Removed the previous vacuous outbox assertion from the full-stack test.
- Result:
  - The FastAPI runtime can now create, read, and fire SQLAlchemy-backed
    instances through the documented HTTP adapter path.
  - The integration test now proves the advertised SQL-backed full-stack path
    instead of passing through the in-memory fallback.
- Verification:
  - `uv run pytest python/flowforge-sqlalchemy/tests/test_models_roundtrip.py::test_snapshot_store_create_instance_seeds_runtime_rows python/flowforge-sqlalchemy/tests/test_models_roundtrip.py::test_snapshot_store_create_instance_rejects_wrong_tenant -q`:
    `2 passed`.
  - `uv run pytest tests/integration/python/tests/test_fastapi_full_stack.py -q --tb=short`:
    `2 passed`.
  - `uv run ruff check python/flowforge-fastapi/src/flowforge_fastapi/registry.py python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py python/flowforge-sqlalchemy/tests/test_models_roundtrip.py tests/integration/python/tests/test_fastapi_full_stack.py`:
    clean.
  - `uv run pyright python/flowforge-fastapi/src/flowforge_fastapi/registry.py python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py python/flowforge-sqlalchemy/tests/test_models_roundtrip.py tests/integration/python/tests/test_fastapi_full_stack.py`:
    `0 errors, 0 warnings`.
  - `uv run pytest tests -q` from `python/flowforge-fastapi`:
    `27 passed`.
  - `uv run pytest tests -q` from `python/flowforge-sqlalchemy`:
    `22 passed`, `1 skipped`.
  - `uv run pytest tests/integration/python/tests/test_fastapi_full_stack.py tests/integration/python/tests/test_engine_to_storage.py -q --tb=short`:
    `7 passed`.
  - `uv run pytest tests -q --cov=flowforge_fastapi --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-fastapi`: `27 passed`, package coverage 90%.
  - `uv run pytest tests -q --cov=flowforge_sqlalchemy --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-sqlalchemy`: `22 passed`, `1 skipped`, package
    coverage 77%.

## Code-review remediation slice - jtbd-hub request-aware principals

- Audit finding:
  - `flowforge-jtbd-hub` documented request-aware `PrincipalExtractor`
    support, and `_resolve_principal(...)` could accept a request, but the
    admin/permission dependencies only passed the `Authorization` header.
  - Extractors needing real FastAPI `Request` context therefore failed closed
    on authenticated write routes such as package publish.
- Action:
  - Updated `_require_admin(...)` and `_require_permission(...)` dependencies
    to accept FastAPI `Request` and pass it into `_resolve_principal(...)`.
  - Added a publish-route regression whose extractor requires the real request
    object (`request.url`) and authenticates from a non-Authorization header.
- Result:
  - Request-aware extractors now work for the shared permission dependency
    used by publish, rate, demote, and verified-badge routes.
- Verification:
  - `uv run pytest python/flowforge-jtbd-hub/tests/test_E_73_rbac.py::test_E_73_request_aware_extractor_receives_fastapi_request_for_publish -q`:
    `1 passed`.
  - `uv run ruff check python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py python/flowforge-jtbd-hub/tests/test_E_73_rbac.py`:
    clean.
  - `uv run pyright python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py python/flowforge-jtbd-hub/tests/test_E_73_rbac.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests -q` from `python/flowforge-jtbd-hub`:
    `66 passed`, with the existing FastAPI 422 deprecation warning.
  - `uv run pytest tests -q --cov=flowforge_jtbd_hub --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd-hub`: `66 passed`, package coverage 86%, with
    the existing FastAPI 422 deprecation warning.

## Package coverage slice - flowforge-fastapi

- Baseline measurement:
  - `flowforge-fastapi`: `27 passed`, 89% package coverage before this pass.
  - After the SQLAlchemy runtime-store remediation, package coverage measured
    `27 passed`, 90%; remaining uncovered paths were bounded to auth failure
    branches, registry helper edges, designer/runtime error branches, and
    WebSocket fallback/auth edges.
- Action:
  - Added focused tests for:
    - explicit test-default auth/tenant resolver wiring, empty static tenant
      rejection, insecure CSRF-cookie rejection, idempotent CSRF exemption,
      invalid/expired/malformed/legacy session cookies, and invalid HMAC
      signatures;
    - registry unknown-version, snapshot, metadata, and reset helpers;
    - designer unknown-version, schema-exception, and multi-version catalog
      dedupe behavior;
    - runtime empty tenant, missing definition during fire, transactional
      `fire_and_commit`, rollback on failed `put`, and CAS `compare_and_put`
      paths;
    - WebSocket wildcard origins, explicit WS extractor, explicit test
      defaults, generic extractor failure close, and hub fallback selection.
  - Marked the nested `WebSocketDisconnect` branch as excluded because
    in-process ASGI clients cancel the queue wait rather than raising that
    endpoint-local exception during teardown.
- Result:
  - `flowforge-fastapi` now reaches 100% statement and branch coverage and
    has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests/test_router_runtime.py tests/test_ws.py -q` from
    `python/flowforge-fastapi`: `47 passed`.
  - `uv run ruff check python/flowforge-fastapi/src/flowforge_fastapi/ws.py python/flowforge-fastapi/tests/test_router_runtime.py python/flowforge-fastapi/tests/test_ws.py`:
    clean.
  - `uv run pyright python/flowforge-fastapi/src/flowforge_fastapi/ws.py python/flowforge-fastapi/tests/test_router_runtime.py python/flowforge-fastapi/tests/test_ws.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_fastapi --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-fastapi`: `47 passed`, 100% statement and branch
    coverage.
  - `uv run ruff check python/flowforge-fastapi/src/flowforge_fastapi/ws.py python/flowforge-fastapi/tests/test_router_runtime.py python/flowforge-fastapi/tests/test_ws.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-fastapi/src/flowforge_fastapi/ws.py python/flowforge-fastapi/tests/test_router_runtime.py python/flowforge-fastapi/tests/test_ws.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all twelve closed packages.

## Package coverage slice - flowforge-sqlalchemy

- Baseline measurement:
  - `flowforge-sqlalchemy`: `22 passed`, `1 skipped`, 77% package coverage
    after the FastAPI SQL-backed runtime fix.
  - Uncovered risk was concentrated in transactional snapshot commit branches,
    stale write rollback, saga conflict handling, PostgreSQL RLS dialect
    detection, portable JSONB type selection, and the bundled Alembic `env.py`
    online/offline script.
- Action:
  - Added package-local durability tests for:
    - duplicate runtime instance creation surfacing `SnapshotConflict`;
    - negative and racing optimistic-lock writes;
    - `fire_and_commit(...)` durable event/snapshot/instance/outbox/audit
      writes;
    - no-match events avoiding event writes;
    - wrong-tenant fire rejection;
    - invalid transactional audit sink rollback;
    - stale snapshot rollback;
    - missing-initial-snapshot transactional insert path;
    - integrity-error conversion to `SnapshotConflict`;
    - snapshot serialization helper edge shapes.
  - Added saga coverage for invalid statuses and append integrity conflicts.
  - Added RLS binder coverage for bind-dialect PostgreSQL detection and
    unknown-session no-op behavior.
  - Added Alembic env offline/online unit tests with fake context/engine
    objects and covered the PostgreSQL `JsonB` type bridge.
  - Omitted `src/flowforge_sqlalchemy/alembic_bundle/env.py` from source
    coverage because it is an Alembic script executed by the Alembic command
    runner/direct env tests; coverage.py did not attribute those executions to
    the package source file even though the env tests assert both code paths.
- Result:
  - `flowforge-sqlalchemy` now reaches 100% statement and branch coverage for
    package source and has been added to the closed-package coverage ratchet.
- Verification:
  - `uv run pytest tests/test_models_roundtrip.py tests/test_rls_binder.py tests/test_alembic_upgrade.py -q`
    from `python/flowforge-sqlalchemy`: `39 passed`, `1 skipped`.
  - `uv run ruff check python/flowforge-sqlalchemy/tests/test_models_roundtrip.py python/flowforge-sqlalchemy/tests/test_rls_binder.py python/flowforge-sqlalchemy/tests/test_alembic_upgrade.py`:
    clean.
  - `uv run pyright python/flowforge-sqlalchemy/tests/test_models_roundtrip.py python/flowforge-sqlalchemy/tests/test_rls_binder.py python/flowforge-sqlalchemy/tests/test_alembic_upgrade.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_sqlalchemy --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-sqlalchemy`: `40 passed`, `1 skipped`, 100%
    statement and branch coverage.
  - `uv run ruff check python/flowforge-sqlalchemy/tests/test_models_roundtrip.py python/flowforge-sqlalchemy/tests/test_rls_binder.py python/flowforge-sqlalchemy/tests/test_alembic_upgrade.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright python/flowforge-sqlalchemy/tests/test_models_roundtrip.py python/flowforge-sqlalchemy/tests/test_rls_binder.py python/flowforge-sqlalchemy/tests/test_alembic_upgrade.py scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`:
    `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    passed for all thirteen closed packages.

## CLI coverage slice - audit-2026 release-health command

- Baseline measurement:
  - `flowforge-cli` package-local coverage was 71% before this CLI coverage
    pass.
  - `flowforge_cli.commands.audit_2026_health` was 23% covered, leaving the
    Prometheus response parser, probe verdict mapping, ticket aggregation, and
    JSON/human Typer command exits under-tested.
- Action:
  - Added focused release-health tests for Prometheus transport, invalid JSON,
    failed query, empty result, scalar aggregation, and malformed-series
    response shapes.
  - Added probe and ticket aggregation tests for required failures,
    informational warnings, empty "must stay 0" data, and threshold breaches.
  - Added Typer CLI coverage for unknown tickets, JSON success/failure exits,
    human warning success, human required failure, and registration of the
    `audit-2026 health` command group.
- Result:
  - `flowforge_cli.commands.audit_2026_health` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` package coverage improved from 71% to 72%; the
    remaining CLI coverage work is still dominated by the desktop GUI module
    and larger command/generator edge paths.
- Verification:
  - `uv run pytest tests/test_audit_2026_health.py -q --cov=flowforge_cli.commands.audit_2026_health --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `19 passed`, 100% statement and branch
    coverage for `audit_2026_health.py`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `659 passed`, overall package coverage 72%.
  - `uv run ruff check tests/test_audit_2026_health.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_audit_2026_health.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - IO helpers and AI assist command

- Baseline measurement:
  - After closing the audit-health command, `flowforge-cli` package coverage
    was 72%.
  - `_io.py` was 70% covered and `commands/ai_assist.py` was 67% covered,
    leaving shared structured-file loading, safe generated path resolution,
    workflow-definition discovery, and AI prompt write/error branches
    under-tested.
- Action:
  - Added focused IO helper tests for YAML loading, unknown-suffix YAML
    fallback, non-mapping JSON rejection, deterministic JSON writing, absolute
    and parent-segment path rejection, symlink escape rejection, safe nested
    path acceptance, and sorted workflow definition discovery.
  - Added AI assist command tests for no-focus selection, non-mapping JTBD list
    entries, unknown JTBD selection errors, prompt file output, stdout output,
    and Typer error reporting.
- Result:
  - `flowforge_cli._io` and `flowforge_cli.commands.ai_assist` now both reach
    100% statement and branch coverage.
  - Overall `flowforge-cli` package coverage improved from 72% to 73%.
- Verification:
  - `uv run pytest tests/test_io_and_ai_assist.py -q --cov=flowforge_cli._io --cov=flowforge_cli.commands.ai_assist --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `17 passed`, 100% statement and branch
    coverage for both targeted modules.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `676 passed`, overall package coverage 73%.
  - `uv run ruff check tests/test_io_and_ai_assist.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_io_and_ai_assist.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - audit verify command

- Baseline measurement:
  - After closing IO helpers and AI assist, rounded `flowforge-cli` package
    coverage was 73%.
  - `commands/audit_verify.py` was 66% covered, leaving missing-file handling,
    parse-error wrapping, broken-chain reporting, range labels, and row-shape
    validation under-tested.
- Action:
  - Added focused audit verify tests for required `--file`, successful range
    labels, broken chain reporting, blank-line skipping, non-object export
    rows, datetime object rows, invalid timestamps, non-object payloads,
    missing required fields, and command-level parse-error wrapping.
  - Corrected the test hash-chain fixture to mirror the actual export
    contract: `event_id` remains outside the canonical hash body, and
    timestamp strings match the verifier's reconstructed canonical value.
- Result:
  - `flowforge_cli.commands.audit_verify` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 73%; uncovered
    work is now concentrated in larger command/generator paths and the desktop
    GUI module.
- Verification:
  - `uv run pytest tests/test_audit_verify.py -q --cov=flowforge_cli.commands.audit_verify --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `9 passed`, 100% statement and branch
    coverage for `audit_verify.py`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `685 passed`, overall package coverage 73%.
  - `uv run ruff check tests/test_audit_verify.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_audit_verify.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - replay command

- Baseline measurement:
  - After closing audit verify, rounded `flowforge-cli` package coverage was
    73%.
  - `commands/replay.py` was 49% covered, leaving missing-definition handling,
    context loading, events-file parsing, empty-history output, and malformed
    event payload validation under-tested.
- Action:
  - Added replay command tests for required `--def`, context and events-file
    replay with deterministic instance id, no-event empty history, and
    command-level events-file error wrapping.
  - Added direct events parser tests for repeatable/comma-separated events,
    mixed string/object event files, missing event names, non-object payloads,
    and unsupported event item shapes.
- Result:
  - `flowforge_cli.commands.replay` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` package coverage improved from 73% to 74%.
- Verification:
  - `uv run pytest tests/test_replay.py -q --cov=flowforge_cli.commands.replay --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `9 passed`, 100% statement and branch
    coverage for `replay.py`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `694 passed`, overall package coverage 74%.
  - `uv run ruff check tests/test_replay.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_replay.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - small command edges

- Baseline measurement:
  - After closing replay, rounded `flowforge-cli` package coverage was 74%.
  - `commands/add_jtbd.py`, `commands/diff.py`,
    `commands/migrate_fork.py`, and `commands/upgrade_deps.py` still had
    uncovered first-run, update, error, default-path, and dependency-inspection
    branches.
- Action:
  - Added focused tests for `diff --exit-zero` and invalid workflow input
    error wrapping.
  - Added `add-jtbd` tests for creating a missing project bundle, refreshing a
    changed JTBD, detecting unchanged reruns, and deterministic shared entity
    merging.
  - Added `migrate-fork` tests for safe path segment acceptance and default
    destination writes.
  - Added `upgrade-deps` tests for refusing `--apply`, missing workspace
    errors, workspace-without-packages errors, and `_find_workspace_root`
    misses.
- Result:
  - `flowforge_cli.commands.add_jtbd`, `diff`, `migrate_fork`, and
    `upgrade_deps` now reach 100% statement and branch coverage in the focused
    run.
  - Overall `flowforge-cli` rounded package coverage remains 74%, with the
    remaining uncovered work dominated by `jtbd_desktop/app.py`,
    `migration_safety.py`, `polish_copy.py`, and generator edge branches.
- Verification:
  - `uv run pytest tests/test_small_command_edges.py tests/test_other_commands.py::test_diff_prints_workflow_structural_diff tests/test_other_commands.py::test_migrate_fork_copies_with_metadata tests/test_other_commands.py::test_migrate_fork_rejects_unsafe_tenant_default_path tests/test_other_commands.py::test_upgrade_deps_inspects_workspace -q --cov=flowforge_cli.commands.diff --cov=flowforge_cli.commands.add_jtbd --cov=flowforge_cli.commands.migrate_fork --cov=flowforge_cli.commands.upgrade_deps --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `16 passed`, 100% statement and branch
    coverage for all four targeted command modules.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `706 passed`, overall package coverage 74%.
  - `uv run ruff check tests/test_small_command_edges.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_small_command_edges.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - validate, simulate, and JTBD generate

- Baseline measurement:
  - After closing the small command edges, rounded `flowforge-cli` package
    coverage was 74%.
  - `commands/validate.py`, `commands/simulate.py`, and
    `commands/jtbd_generate.py` still had uncovered read-error, warning,
    event-flattening, effect-log, terminal-stop, non-empty-target, and
    generator-error branches.
- Action:
  - Added validate tests for structured load failures and success/error
    warning output.
  - Added simulate tests for repeatable/comma-separated event flattening,
    unknown matched-transition reporting, terminal-stop behavior, and all
    supported effect log branches.
  - Added JTBD generate tests for non-empty target refusal, forced generation
    into a non-empty target, and generator `ValueError` wrapping.
- Result:
  - `flowforge_cli.commands.validate`, `simulate`, and `jtbd_generate` now
    reach 100% statement and branch coverage in the focused run.
  - Overall `flowforge-cli` rounded package coverage remains 74%; remaining
    coverage work is still dominated by `jtbd_desktop/app.py`,
    `migration_safety.py`, `polish_copy.py`, `bundle_diff.py`, and generator
    edge branches.
- Verification:
  - `uv run pytest tests/test_validate_simulate_generate_edges.py tests/test_validate.py tests/test_simulate.py tests/test_other_commands.py::test_jtbd_generate_writes_artefacts tests/test_other_commands.py::test_jtbd_generate_rejects_generated_path_escape -q --cov=flowforge_cli.commands.validate --cov=flowforge_cli.commands.simulate --cov=flowforge_cli.commands.jtbd_generate --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `20 passed`, 100% statement and branch
    coverage for all three targeted command modules.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `716 passed`, overall package coverage 74%.
  - `uv run ruff check tests/test_validate_simulate_generate_edges.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_validate_simulate_generate_edges.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - pre-upgrade readiness checks

- Baseline measurement:
  - After closing validate/simulate/JTBD-generate branches, rounded
    `flowforge-cli` package coverage was 74%.
  - `commands/pre_upgrade_check.py` was 94% covered, leaving default path
    resolution, distinct Alembic branch-label reporting, unreadable pyproject
    handling, section-label classification, and duplicate offending section
    dedupe branches under-tested.
- Action:
  - Added pre-upgrade tests for default Alembic versions-dir fallback,
    intentional parallel Alembic chains with distinct `branch_labels`,
    default pyproject fallback, unreadable pyproject failure reporting,
    section-level z3-solver offender labels, and duplicate offender dedupe.
- Result:
  - `flowforge_cli.commands.pre_upgrade_check` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage improved from 74% to 75%.
- Verification:
  - `uv run pytest tests/test_pre_upgrade_check.py -q --cov=flowforge_cli.commands.pre_upgrade_check --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `21 passed`, 100% statement and branch
    coverage for `pre_upgrade_check.py`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `721 passed`, overall package coverage 75%.
  - `uv run ruff check tests/test_pre_upgrade_check.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_pre_upgrade_check.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - JTBD migrate no-drop path

- Baseline measurement:
  - After closing pre-upgrade readiness checks, rounded `flowforge-cli`
    package coverage was 75%.
  - `commands/jtbd_migrate.py` was 98% covered; the only remaining branch was
    applying a migration when no populated fields are dropped.
- Action:
  - Added a record-migration test for a deprecated JTBD replacement where the
    target adds a field but preserves all populated source fields, writes the
    migrated record to a file, and emits no dropped-data warning.
- Result:
  - `flowforge_cli.commands.jtbd_migrate` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 75%.
- Verification:
  - `uv run pytest tests/test_jtbd_migrate_cmd.py -q --cov=flowforge_cli.commands.jtbd_migrate --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `8 passed`, 100% statement and branch
    coverage for `jtbd_migrate.py`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `722 passed`, overall package coverage 75%.
  - `uv run ruff check tests/test_jtbd_migrate_cmd.py`
    from `python/flowforge-cli`:
    clean.
  - `uv run pyright tests/test_jtbd_migrate_cmd.py`
    from `python/flowforge-cli`:
    `0 errors`, `0 warnings`.

## CLI coverage slice - tutorial command

- Baseline measurement:
  - After closing JTBD migrate, rounded `flowforge-cli` package coverage was
    75%.
  - `commands/tutorial.py` was 81% covered in full-suite runs, leaving
    subprocess dispatch, command failure summaries, skip paths, pause handling,
    executable discovery, and defensive CWD validation under-tested.
- Action:
  - Added tutorial tests for validated CWD handling, subprocess success/fail
    dispatch, missing-console executable fallback, step 2-5 failure summaries,
    step 3-5 skip paths, successful step 5 lint dispatch, and interactive
    pause prompts.
  - Marked the final `elif n == 5` dispatch as a non-branching coverage point
    because selected steps are validated to the fixed 1-5 step set before the
    loop.
  - Fixed the replayability issue found by code review: package-local
    `ruff`/`pyright` evidence now uses package-local `tests/...` paths instead
    of repo-root `python/flowforge-cli/tests/...` paths.
- Result:
  - `flowforge_cli.commands.tutorial` now reaches 100% statement and branch
    coverage.
- Verification:
  - `uv run pytest tests/test_tutorial.py tests/test_E_57_acceptance.py::test_CL_02_validated_cwd_rejects_missing_dir tests/test_E_57_acceptance.py::test_CL_02_validated_cwd_rejects_file_not_dir -q --cov=flowforge_cli.commands.tutorial --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `29 passed`, 100% statement and branch
    coverage for `tutorial.py`.
  - `uv run ruff check src/flowforge_cli/commands/tutorial.py tests/test_tutorial.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright src/flowforge_cli/commands/tutorial.py tests/test_tutorial.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `736 passed`, overall package coverage 75%.

## Code review audit 6 - CLI coverage evidence replayability

- Finding:
  - The code-review pass found that several newly added readiness-log entries
    claimed commands were run from `python/flowforge-cli` while their
    `ruff`/`pyright` examples used repo-root-relative
    `python/flowforge-cli/tests/...` paths. Those commands were not
    replayable from the documented working directory.
- Action:
  - Corrected the affected CLI coverage log entries to use package-local
    `tests/...` paths when the working directory is documented as
    `python/flowforge-cli`.
  - Re-ran the tutorial slice's documented package-local `ruff` and `pyright`
    commands after the correction.
- Result:
  - The audit finding is resolved for the new CLI coverage log entries, and
    the progress log now preserves replayable verification evidence.

## CLI coverage slice - migration safety analyzer

- Baseline measurement:
  - After closing tutorial command coverage, rounded `flowforge-cli` package
    coverage was 75%.
  - `commands/migration_safety.py` was 79% covered; the remaining gaps were
    defensive metadata parsing, size-hint loading, AST helper branches,
    no-upgrade/no-parse rule exits, markdown rendering, direct CLI input
    rejection, and baseline edge cases.
- Action:
  - Added focused tests for malformed migrations, AST-over-regex metadata,
    branch labels, revision assignment extraction, size-hint decoding,
    parser-error findings, missing migration directories, first-create NOT NULL
    handling, dynamic table/column names, safe type-alter shapes, multi-head
    helper fallbacks, markdown grouping, baseline parsing, unknown output
    formats, and file-path rejection.
  - Marked the final tuple-form `down_revision` regex branch as non-branching
    for coverage because the regex only admits `None`, a quoted string, or a
    tuple literal.
- Result:
  - `flowforge_cli.commands.migration_safety` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage improved from 75% to 77%.
- Verification:
  - `uv run pytest tests/test_migration_safety_cli.py -q --cov=flowforge_cli.commands.migration_safety --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `43 passed`, 100% statement and branch
    coverage for `migration_safety.py`.
  - `uv run ruff check src/flowforge_cli/commands/migration_safety.py tests/test_migration_safety_cli.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright src/flowforge_cli/commands/migration_safety.py tests/test_migration_safety_cli.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `760 passed`, overall package coverage 77%.

## CLI coverage slice - JTBD desktop command launcher

- Baseline measurement:
  - After closing migration safety analyzer coverage, rounded `flowforge-cli`
    package coverage was 77%.
  - `commands/jtbd_desktop.py` was 39% covered; the missing paths were theme
    validation, optional desktop import failure handling, runner failure
    handling, and propagation of the desktop runner exit code.
- Action:
  - Added command-level tests for missing theme files, fake desktop runner
    success with bundle/theme path forwarding, non-zero runner exit codes,
    import-time desktop dependency failures, and runtime desktop launch
    failures.
  - Used fake `flowforge_cli.jtbd_desktop.app` modules in `sys.modules` so the
    tests cover command behavior without importing or requiring PyQt.
- Result:
  - `flowforge_cli.commands.jtbd_desktop` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 77%.
- Verification:
  - `uv run pytest tests/test_jtbd_desktop_document.py -q --cov=flowforge_cli.commands.jtbd_desktop --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `30 passed`, 100% statement and branch
    coverage for `jtbd_desktop.py`.
  - `uv run ruff check tests/test_jtbd_desktop_document.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_desktop_document.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `765 passed`, overall package coverage 77%.

## CLI coverage slice - shared JTBD render helpers

- Baseline measurement:
  - After closing JTBD desktop command coverage, rounded `flowforge-cli`
    package coverage was 77%.
  - `jtbd/_render.py` was 90% covered; the uncovered lines were the shared
    JSON and Python repr filters used by Jinja templates.
- Action:
  - Added focused tests for deterministic JSON key ordering, fallback string
    conversion for non-JSON values, Python literal representation, and a real
    `env.example.j2` render through the shared cached Jinja environment.
- Result:
  - `flowforge_cli.jtbd._render` now reaches 100% statement coverage.
  - Overall `flowforge-cli` rounded package coverage remains 77%.
- Verification:
  - `uv run pytest tests/test_jtbd_render.py -q --cov=flowforge_cli.jtbd._render --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `3 passed`, 100% coverage for `_render.py`.
  - `uv run ruff check tests/test_jtbd_render.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_render.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `768 passed`, overall package coverage 77%.

## CLI coverage slice - JTBD fixture registry

- Baseline measurement:
  - After closing shared render helper coverage, rounded `flowforge-cli`
    package coverage was 77%.
  - `jtbd/generators/_fixture_registry.py` was 73% covered; the uncovered
    lines were the test-only runtime `register` helper and its input
    assertions.
- Action:
  - Added focused registry tests for unknown-generator lookup, sorted runtime
    registration, `all_generators()` visibility, and assertion behavior for
    invalid generator names and non-tuple `consumes` values.
  - Monkeypatched a copy of the registry dict during registration tests to
    avoid polluting the shared generator registry across the suite.
- Result:
  - `flowforge_cli.jtbd.generators._fixture_registry` now reaches 100%
    statement coverage.
  - Overall `flowforge-cli` rounded package coverage remains 77%.
- Verification:
  - `uv run pytest tests/test_jtbd_fixture_registry.py -q --cov=flowforge_cli.jtbd.generators._fixture_registry --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `2 passed`, 100% coverage for
    `_fixture_registry.py`.
  - `uv run ruff check tests/test_jtbd_fixture_registry.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_fixture_registry.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `770 passed`, overall package coverage 77%.

## CLI coverage slice - JTBD diagram generator

- Baseline measurement:
  - After closing fixture registry coverage, rounded `flowforge-cli` package
    coverage was 77%.
  - `jtbd/generators/diagram.py` was 98% covered; the uncovered paths were
    non-positive SLA formatting, empty guard expressions, and the branch where
    an SLA budget exists but no canonical `review` state is available for the
    Mermaid note anchor.
  - The optional `mmdc` parse smoke also failed locally because `mmdc` was
    installed but Puppeteer could not find a Chrome executable.
- Action:
  - Added focused tests for empty guard expressions, zero/negative SLA budget
    formatting, and SLA-without-review-state rendering.
  - Hardened the optional `mmdc` smoke skip logic so browser-unavailable
    environments skip unless `FLOWFORGE_REQUIRE_MMDC=1` is set.
- Result:
  - `flowforge_cli.jtbd.generators.diagram` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 77%.
- Verification:
  - `uv run pytest tests/test_jtbd_diagram_generator.py -q --cov=flowforge_cli.jtbd.generators.diagram --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `32 passed`, `1 skipped`, 100% statement and
    branch coverage for `diagram.py`.
  - `uv run ruff check tests/test_jtbd_diagram_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_diagram_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 77%.

## CLI coverage slice - generated frontend CLI

- Baseline measurement:
  - After closing diagram generator coverage, rounded `flowforge-cli` package
    coverage was 77%.
  - `jtbd/generators/frontend_cli.py` was 92% covered; the remaining gaps were
    helper-level integer/boolean Typer option mappings and invalid/empty
    transition-event filtering.
- Action:
  - Added focused tests for supported scalar kind mapping (`integer`, `number`,
    `money`, `boolean`, fallback string kinds).
  - Added an events extraction test that verifies empty and non-string events
    are ignored while valid event names are sorted and retained.
- Result:
  - `flowforge_cli.jtbd.generators.frontend_cli` now reaches 100% statement
    and branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 77%.
- Verification:
  - `uv run pytest tests/test_frontend_cli_generator.py -q --cov=flowforge_cli.jtbd.generators.frontend_cli --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `20 passed`, 100% statement and branch
    coverage for `frontend_cli.py`.
  - `uv run ruff check tests/test_frontend_cli_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_frontend_cli_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 77%.

## Code audit follow-up + CLI coverage slice - i18n generator

- Audit follow-up:
  - A prior code-audit lane had flagged the risk that bundles declaring a
    non-English locale before `en` could emit the wrong source/fallback
    catalog.
  - Current-state inspection found `i18n.py` already selects `en` as the
    source/fallback language whenever it is declared, and
    `test_non_english_first_language_still_uses_en_as_source_catalog` covers
    `languages=["fr-CA", "en"]`.
- Baseline measurement:
  - After closing generated frontend CLI coverage, rounded `flowforge-cli`
    package coverage was 77%.
  - `jtbd/generators/i18n.py` was 96% covered; the remaining gaps were
    no-dot audit topic humanization, absent SLA warning/breach branches, and
    the empty-catalog `TranslationKey` union fallback.
- Action:
  - Added focused tests for no-dot audit topic rendering, catalog emission when
    a JTBD has no SLA declaration, and empty-bundle `useT.ts` key-union output.
- Result:
  - `flowforge_cli.jtbd.generators.i18n` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage improved from 77% to 78%.
- Verification:
  - `uv run pytest tests/test_i18n_generator.py -q --cov=flowforge_cli.jtbd.generators.i18n --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `45 passed`, 100% statement and branch
    coverage for `i18n.py`.
  - `uv run ruff check tests/test_i18n_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_i18n_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - generated email and Slack adapters

- Baseline measurement:
  - After closing i18n generator coverage, rounded `flowforge-cli` package
    coverage was 78%.
  - `jtbd/generators/frontend_email.py` and
    `jtbd/generators/frontend_slack.py` were both 98% covered; each had one
    remaining branch in transition-event extraction.
- Action:
  - Added focused tests proving generated email and Slack adapter event
    catalogs ignore empty and non-string transition events while retaining
    valid event names.
- Result:
  - `flowforge_cli.jtbd.generators.frontend_email` and
    `flowforge_cli.jtbd.generators.frontend_slack` now both reach 100%
    statement and branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_frontend_email_generator.py tests/test_frontend_slack_generator.py -q --cov=flowforge_cli.jtbd.generators.frontend_email --cov=flowforge_cli.jtbd.generators.frontend_slack --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `34 passed`, 100% statement and branch
    coverage for both adapter generators.
  - `uv run ruff check tests/test_frontend_email_generator.py tests/test_frontend_slack_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_frontend_email_generator.py tests/test_frontend_slack_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## Code review audit 7 - recent coverage evidence replayability

- Finding:
  - A code-review pass over commits `1fb1b27`, `76ed58c`, and `00fd835`
    found that the i18n slice's full-suite verification line pinned an exact
    test count (`776 passed`) that became stale after later coverage slices
    added tests.
- Action:
  - Updated the recent full-suite evidence lines to report the replayable
    command, pass status, optional `mmdc` skip, and rounded coverage result
    rather than brittle historical test totals.
- Result:
  - The review finding is resolved. Exact focused-test counts remain recorded
    for the slice-local commands; broad full-suite evidence now avoids drifting
    as subsequent slices add tests.

## CLI coverage slice - lineage generator

- Baseline measurement:
  - After closing email and Slack adapter coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/generators/lineage.py` was 99% covered; the remaining branch was the
    defensive path where a JTBD has no actor role and lineage exposure records
    should not emit a blank role.
- Action:
  - Added a focused exposure-surface test using a normalized JTBD with an empty
    actor role, asserting that only shared roles are emitted.
- Result:
  - `flowforge_cli.jtbd.generators.lineage` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_lineage_generator.py -q --cov=flowforge_cli.jtbd.generators.lineage --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `30 passed`, 100% statement and branch
    coverage for `lineage.py`.
  - `uv run ruff check tests/test_lineage_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_lineage_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `779 passed`, `1 skipped`, overall package
    coverage 78%.

## CLI coverage slice - operator manual generator

- Baseline measurement:
  - After closing lineage generator coverage, rounded `flowforge-cli` package
    coverage was 78%.
  - `jtbd/generators/operator_manual.py` was 97% covered; the remaining branch
    was intended to summarize shared permissions without a `<jtbd>.` prefix.
- Action:
  - Added focused operator manual tests for MDX generation shape, permission
    summaries, returned edge-case audit-topic summaries, and fixture-registry
    parity.
  - Fixed `_permission_summary()` so non-prefixed shared permissions use the
    documented shared-permission summary instead of being treated as unknown
    JTBD actions.
- Result:
  - `flowforge_cli.jtbd.generators.operator_manual` now reaches 100% statement
    and branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_operator_manual_generator.py -q --cov=flowforge_cli.jtbd.generators.operator_manual --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `5 passed`, 100% statement and branch
    coverage for `operator_manual.py`.
  - `uv run ruff check src/flowforge_cli/jtbd/generators/operator_manual.py tests/test_operator_manual_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright src/flowforge_cli/jtbd/generators/operator_manual.py tests/test_operator_manual_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `784 passed`, `1 skipped`, overall package
    coverage 78%.

## CLI coverage slice - i18n sidecar loader

- Baseline measurement:
  - After closing operator manual coverage, rounded `flowforge-cli` package
    coverage was 78%.
  - `jtbd/i18n_sidecars.py` was 80% covered; the remaining gaps were missing
    sidecar directory handling, malformed JSON object validation,
    non-string key/value validation, and the permissive mode where no declared
    language filter is supplied.
- Action:
  - Added focused sidecar loader tests for missing directories, loading without
    a declared-language filter, rejecting non-object catalogs, rejecting
    non-string values, and the defensive non-string key branch.
- Result:
  - `flowforge_cli.jtbd.i18n_sidecars` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_i18n_generator.py -q --cov=flowforge_cli.jtbd.i18n_sidecars --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `50 passed`, 100% statement and branch
    coverage for `i18n_sidecars.py`.
  - `uv run ruff check tests/test_i18n_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_i18n_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `789 passed`, `1 skipped`, overall package
    coverage 78%.

## CLI coverage slice - reachability generator

- Baseline measurement:
  - After closing i18n sidecar loader coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/generators/reachability.py` was 93% covered; remaining gaps were
    defensive guard-shape filtering, the non-SAT solver result branch, and the
    report summary path for unreachable transitions.
- Action:
  - Added focused tests for ignoring non-`expr` guards, ignoring non-`context`
    and non-string guard variables, surfacing a non-SAT z3 result as
    unreachable, and counting unreachable transitions in the emitted report.
- Result:
  - `flowforge_cli.jtbd.generators.reachability` now reaches 100% statement
    and branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_reachability_generator.py -q --cov=flowforge_cli.jtbd.generators.reachability --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `18 passed`, 100% statement and branch
    coverage for `reachability.py`.
  - `uv run ruff check tests/test_reachability_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_reachability_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - OpenAPI generator

- Baseline measurement:
  - After closing reachability generator coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/generators/openapi.py` was 71% covered in focused generator tests;
    remaining gaps were validation-bound translation, unknown-kind defaults,
    example selection for numeric mins and enums, and optional-only payloads.
- Action:
  - Added focused OpenAPI helper tests for numeric and string validation schema
    mapping, ignored array bounds, unknown field-kind defaults, optional-only
    payload schemas, numeric-min examples, enum examples, empty-enum fallback,
    and unknown-kind example fallback.
- Result:
  - `flowforge_cli.jtbd.generators.openapi` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_openapi_generator.py -q --cov=flowforge_cli.jtbd.generators.openapi --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `18 passed`, 100% statement and branch
    coverage for `openapi.py`.
  - `uv run ruff check tests/test_openapi_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_openapi_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - property-test generator

- Baseline measurement:
  - After closing OpenAPI generator coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/generators/property_tests.py` was 89% covered; remaining gaps were
    defensive guard-variable extraction and workflow-event filtering branches.
- Action:
  - Added a dedicated property-test generator suite covering invalid guard
    shapes, non-string and non-context guard variables, empty guard suffixes,
    event-name filtering, generated pinned seed output, generated guard/event
    strategy inputs, and fixture-registry parity.
- Result:
  - `flowforge_cli.jtbd.generators.property_tests` now reaches 100% statement
    and branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_property_tests_generator.py -q --cov=flowforge_cli.jtbd.generators.property_tests --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `4 passed`, 100% statement and branch
    coverage for `property_tests.py`.
  - `uv run ruff check tests/test_property_tests_generator.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_property_tests_generator.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - seed-data generator

- Baseline measurement:
  - After closing property-test generator coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/generators/seed_data.py` was 93% covered; remaining gaps were faker
    fallback branches and seed event-path edge cases for identity paths,
    already-visited states, unreachable states, blank state names, and
    non-`submit` path suffixes.
- Action:
  - Added focused seed-data tests for unknown field-kind fallback, default
    money/number/enum faker expressions without validation, shortest-path
    identity/cycle/unreachable behavior, and seed-event path filtering for
    blank, initial, unreachable, and non-`submit` states.
- Result:
  - `flowforge_cli.jtbd.generators.seed_data` now reaches 100% statement and
    branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_jtbd_seed_data.py -q --cov=flowforge_cli.jtbd.generators.seed_data --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `26 passed`, 100% statement and branch
    coverage for `seed_data.py`.
  - `uv run ruff check tests/test_jtbd_seed_data.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_seed_data.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - JTBD conflict solver

- Baseline measurement:
  - After closing seed-data generator coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/lint/conflicts.py` was 96% covered; remaining gaps were the
    `reads()` helper, empty z3-backend routing, and malformed composition
    semantics for bad data, bad consistency, and invalid entities.
- Action:
  - Added focused conflict-solver tests for read/write helper behavior,
    empty-semantics z3 backend short-circuiting, and composition extraction
    validation for bad data, bad consistency, and non-`list[str]` entities.
- Result:
  - `flowforge_cli.jtbd.lint.conflicts` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_jtbd_conflicts.py -q --cov=flowforge_cli.jtbd.lint.conflicts --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `29 passed`, 100% statement and branch
    coverage for `conflicts.py`.
  - `uv run ruff check tests/test_jtbd_conflicts.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_conflicts.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - JTBD parser

- Baseline measurement:
  - After closing JTBD conflict solver coverage, rounded `flowforge-cli`
    package coverage was 78%.
  - `jtbd/parse.py` was 90% covered; the remaining gap was the editable-install
    schema fallback used when importlib resources cannot resolve the core
    JTBD schema.
- Action:
  - Added a focused parser test that clears the schema cache, forces resource
    lookup failure, and verifies the fallback loads and caches the schema from
    the installed core package path.
- Result:
  - `flowforge_cli.jtbd.parse` now reaches 100% statement and branch coverage.
  - Overall `flowforge-cli` rounded package coverage remains 78%.
- Verification:
  - `uv run pytest tests/test_jtbd_parse.py -q --cov=flowforge_cli.jtbd.parse --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `6 passed`, 100% statement and branch
    coverage for `parse.py`.
  - `uv run ruff check tests/test_jtbd_parse.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_parse.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 78%.

## CLI coverage slice - JTBD pipeline shortcut

- Baseline measurement:
  - After closing JTBD parser coverage, rounded `flowforge-cli` package
    coverage was 78%.
  - `jtbd/pipeline.py` was 71% covered; the remaining gap was the
    `generate_for_bundle()` normalized-bundle shortcut.
- Action:
  - Added a focused pipeline parity test proving `generate_for_bundle()` on a
    normalized bundle returns the same path/content map as the public
    parse-normalize-generate entrypoint.
- Result:
  - `flowforge_cli.jtbd.pipeline` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage increased to 79%.
- Verification:
  - `uv run pytest tests/test_jtbd_generators.py -q --cov=flowforge_cli.jtbd.pipeline --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `12 passed`, 100% statement and branch
    coverage for `pipeline.py`.
  - `uv run ruff check tests/test_jtbd_generators.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_generators.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 79%.

## CLI coverage slice - JTBD transforms

- Baseline measurement:
  - After closing JTBD pipeline shortcut coverage, rounded `flowforge-cli`
    package coverage was 79%.
  - `jtbd/transforms.py` was 90% covered; remaining gaps were empty
    PascalCase fallback, duplicate/missing branch-target handling, loop-edge
    synthesis, field mapping helpers, and form-field validation omission.
- Action:
  - Added focused transform tests for empty PascalCase fallback, duplicate
    branch-state suppression, missing branch transition suppression, loop
    transition and audit-topic synthesis, unknown field-kind column defaults,
    default form labels, validation preservation, and validation omission.
- Result:
  - `flowforge_cli.jtbd.transforms` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage remains 79%.
- Verification:
  - `uv run pytest tests/test_jtbd_transforms.py tests/test_jtbd_compensation_synthesis.py tests/test_jtbd_generators.py -q --cov=flowforge_cli.jtbd.transforms --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `33 passed`, 100% statement and branch
    coverage for `transforms.py`.
  - `uv run ruff check tests/test_jtbd_transforms.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_transforms.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 79%.

## CLI coverage slice - console entrypoint

- Baseline measurement:
  - After closing JTBD transforms coverage, rounded `flowforge-cli` package
    coverage was 79%.
  - `main.py` was 97% covered; the remaining gap was the console-script
    `main()` shim calling the Typer app.
- Action:
  - Added a focused top-level command test that monkeypatches the Typer app
    callable and proves `main()` delegates to it without invoking CLI parsing.
- Result:
  - `flowforge_cli.main` now reaches 100% statement coverage.
  - Overall `flowforge-cli` rounded package coverage remains 79%.
- Verification:
  - `uv run pytest tests/test_other_commands.py -q --cov=flowforge_cli.main --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `20 passed`, 100% statement coverage for
    `main.py`.
  - `uv run ruff check tests/test_other_commands.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_other_commands.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 79%.

## CLI coverage slice - copy override sidecar

- Baseline measurement:
  - After closing console entrypoint coverage, rounded `flowforge-cli`
    package coverage was 79%.
  - `jtbd/overrides.py` was 86% covered; remaining gaps were malformed
    sidecar-key validation paths and defensive canonical-string extraction
    branches for malformed bundle shapes.
- Action:
  - Added focused polish-copy tests for malformed override namespace errors,
    missing `jtbds`, missing `data_capture`, non-dict JTBD entries, non-string
    JTBD ids, non-list captures, non-dict fields, non-string field ids, and
    default label derivation when labels are empty.
- Result:
  - `flowforge_cli.jtbd.overrides` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage remains 79%.
- Verification:
  - `uv run pytest tests/test_polish_copy.py -q --cov=flowforge_cli.jtbd.overrides --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `34 passed`, 100% statement and branch
    coverage for `overrides.py`.
  - `uv run ruff check tests/test_polish_copy.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_polish_copy.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 79%.

## Code review audit 8 - recent entrypoint and override coverage slices

- Scope:
  - Reviewed commits `edf75ab` and `92eaa97`, covering the console entrypoint
    test, copy-override sidecar tests, and their readiness-log evidence.
  - A native `code-reviewer` agent could not be spawned because stale shutdown
    agent records are still counted against the thread limit, so this audit was
    performed locally using the code-review checklist.
- Checks:
  - Inspected the combined diff from `0e29b52..HEAD` for test brittleness,
    misleading evidence, hidden production-behavior risk, and maintainability.
  - Verified `git show --stat --check --oneline edf75ab 92eaa97` reports no
    whitespace/check errors.
  - Confirmed the entrypoint test monkeypatches only the Typer app callable and
    avoids invoking CLI parsing side effects.
  - Confirmed the override sidecar tests exercise malformed-key and
    malformed-bundle defensive branches without changing production behavior.
- Findings:
  - No critical, high, medium, or low findings.
- Residual risk:
  - This audit only covered the two newest coverage commits. Broader unpushed
    coverage work still needs periodic review once the stale agent thread limit
    clears or a manual review window is allocated.

## CLI coverage slice - JTBD lint command wrapper

- Baseline measurement:
  - After closing copy override sidecar coverage, rounded `flowforge-cli`
    package coverage was 79%.
  - `commands/jtbd_lint.py` was 81% covered; remaining gaps were shared-role
    adapter edge cases, text formatter fixhint and clean-report branches,
    default bundle discovery, no-default error handling, and linter exception
    handling.
- Action:
  - Added focused JTBD lint adapter/CLI tests for list-form role dicts,
    ignored unknown shared-role shapes, formatter fixhints, clean formatter
    output, default bundle discovery, omitted-bundle auto-detection, missing
    default bundle errors, and linter exception reporting.
- Result:
  - `flowforge_cli.commands.jtbd_lint` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage increased to 80%.
- Verification:
  - `uv run pytest tests/test_jtbd_lint_cmd.py tests/test_jtbd_lint_adapter.py -q --cov=flowforge_cli.commands.jtbd_lint --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `29 passed`, 100% statement and branch
    coverage for `jtbd_lint.py`.
  - `uv run ruff check tests/test_jtbd_lint_adapter.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_lint_adapter.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: passed with one optional `mmdc` skip and
    overall package coverage 80%.

## CLI coverage slice - polish-copy command

- Baseline measurement:
  - After closing JTBD lint command-wrapper coverage, rounded
    `flowforge-cli` package coverage was 80%.
  - `commands/polish_copy.py` was 70% covered; remaining gaps were the real
    Anthropic provider closure, Claude CLI transport/payload errors, malformed
    polish output rejection, dry-run diff output, semantic no-change commit
    skipping, and commit writes that update sidecar metadata without changing
    strings.
- Action:
  - Added focused polish-copy tests for missing Claude CLI binaries, missing
    `flowforge-cli[llm]` extras, Anthropic JSON parsing and fallback behavior,
    Claude CLI empty-input, transport, timeout, malformed payload, error-status,
    filtering, and defaulting paths.
  - Added CLI tests for rejected unknown bundle keys, proposed dry-run diffs,
    semantically unchanged sidecar skips, and metadata-only sidecar rewrites.
- Result:
  - `flowforge_cli.commands.polish_copy` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage increased to 81%.
- Verification:
  - `uv run pytest tests/test_polish_copy.py -q --cov=flowforge_cli.commands.polish_copy --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `53 passed`, 100% statement and branch
    coverage for `polish_copy.py`.
  - `uv run ruff check tests/test_polish_copy.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_polish_copy.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `847 passed`, one optional `mmdc` skip, and
    overall package coverage 81%.

## CLI coverage slice - bundle-diff command

- Baseline measurement:
  - After closing polish-copy command coverage, rounded `flowforge-cli`
    package coverage was 81%.
  - `commands/bundle_diff.py` was 86% covered; remaining gaps were report
    filtering helpers, malformed JTBD indexing, form-renderer regressions,
    actor changes, PII demotion, label changes, numeric validation
    tightening/relaxation, edge removal/condition changes, approvals,
    required-document changes, JSON coercion, empty text rendering, and bundle
    load error branches.
- Action:
  - Added focused bundle-diff tests that lock existing deploy-safety
    categorization rules for those previously uncovered branches.
  - Added renderer/load helper tests for empty reports, non-JSON-safe values,
    unreadable bundle paths, and non-object JSON bundles.
- Result:
  - `flowforge_cli.commands.bundle_diff` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage increased to 82%.
- Verification:
  - `uv run pytest tests/test_bundle_diff.py -q --cov=flowforge_cli.commands.bundle_diff --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `48 passed`, 100% statement and branch
    coverage for `bundle_diff.py`.
  - `uv run ruff check tests/test_bundle_diff.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_bundle_diff.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `857 passed`, one optional `mmdc` skip, and
    overall package coverage 82%.

## CLI coverage slice - desktop document model

- Baseline measurement:
  - After closing bundle-diff command coverage, rounded `flowforge-cli`
    package coverage was 82%.
  - `jtbd_desktop/document.py` was 86% covered; remaining gaps were template
    import errors, prompt validation and keyword-derived fields, generation
    failure reporting, first-save path validation, lint backend failure
    warnings, duplicate-id suffix loops, dependency no-op paths, no-id removal,
    setter dirty/hash behavior, short prompt title derivation, and malformed
    template-library validation branches.
- Action:
  - Added focused desktop document-model tests for those branch paths while
    keeping PyQt GUI runtime out of the test surface.
  - Exercised parser/generator verification errors, local prompt drafting,
    template materialization, dependency graph behavior, deterministic save/load
    helpers, and template sidecar validation without live UI dependencies.
- Result:
  - `flowforge_cli.jtbd_desktop.document` now reaches 100% statement and branch
    coverage.
  - Overall `flowforge-cli` rounded package coverage increased to 83%.
- Verification:
  - `uv run pytest tests/test_jtbd_desktop_document.py -q --cov=flowforge_cli.jtbd_desktop.document --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `45 passed`, 100% statement and branch
    coverage for `document.py`.
  - `uv run ruff check tests/test_jtbd_desktop_document.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_desktop_document.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `872 passed`, one optional `mmdc` skip, and
    overall package coverage 83%.

## Code review audit 9 - recent CLI and desktop coverage slices

- Scope:
  - Reviewed commits `b24fc97`, `0287ffb`, `f28499c`, and `a94c1c5`,
    covering JTBD lint command-wrapper tests, polish-copy provider/sidecar
    tests, bundle-diff deploy-safety tests, desktop document-model tests, and
    their readiness-log evidence.
  - A native `code-reviewer` agent could not be spawned because stale shutdown
    agent records are still counted against the thread limit, so this audit was
    performed locally using the code-review checklist.
- Checks:
  - Verified `git diff --check c854d2f..HEAD` reports no whitespace/check
    errors.
  - Inspected the changed files from `c854d2f..HEAD` for brittle private-state
    assumptions, misleading coverage claims, hidden production-behavior risk,
    fixture pollution, and incorrect readiness-log evidence.
  - Confirmed the new polish-copy tests keep Anthropic and Claude CLI paths
    hermetic with fakes/monkeypatching and do not require live credentials.
  - Confirmed the bundle-diff tests lock existing deploy-safety categorization
    rules without changing production code.
  - Confirmed the desktop document-model tests stay GUI-free and do not import
    PyQt runtime behavior.
- Findings:
  - No critical, high, medium, or low findings.
- Residual risk:
  - This audit remains local because native review-agent spawning is blocked by
    the stale thread-limit condition.
  - The large `jtbd_desktop/app.py` GUI surface is still effectively uncovered
    in package coverage and needs a separate UI-adapter testing strategy.

## CLI coverage slice - desktop app helpers

- Baseline measurement:
  - After closing desktop document-model coverage, rounded `flowforge-cli`
    package coverage was 83%.
  - `jtbd_desktop/app.py` was effectively uncovered because PyQt6 is not
    installed in the verification environment and the previous tests only
    exercised the CLI command shim.
- Action:
  - Added GUI-free tests for theme file parsing, theme merging, stylesheet
    rendering, missing-PyQt launch failure messaging, scalar helper parsing,
    combo restoration, table mutation, and table row serializer/deserializer
    helpers.
  - Used small fake table/combo/item test doubles instead of importing or
    installing PyQt6.
- Result:
  - `flowforge_cli.jtbd_desktop.app` coverage increased from 0% to 24%.
  - Overall `flowforge-cli` rounded package coverage increased to 87%.
- Verification:
  - `uv run pytest tests/test_jtbd_desktop_app_helpers.py -q --cov=flowforge_cli.jtbd_desktop.app --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `3 passed`; `app.py` reached 24% coverage.
  - `uv run ruff check tests/test_jtbd_desktop_app_helpers.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_desktop_app_helpers.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `875 passed`, one optional `mmdc` skip, and
    overall package coverage 87%.
- Remaining risk:
  - Most `JtbdEditorWindow` methods remain uncovered until the package either
    gains a PyQt-capable test lane or the UI logic is split into smaller
    GUI-independent adapters.

## CLI coverage slice - desktop app window actions

- Baseline measurement:
  - After closing desktop app helper coverage, rounded `flowforge-cli` package
    coverage was 87%.
  - `jtbd_desktop/app.py` was 24% covered; the biggest remaining gap was
    `JtbdEditorWindow` behavior hidden behind PyQt widgets.
- Action:
  - Extended GUI-free desktop app tests with small widget, dialog, file-dialog,
    message-box, application, and status-bar doubles.
  - Covered commit/refresh/validation/title paths, AI prompt actions,
    template capture/import/export branches, visual dependency add/remove
    branches, new/open/save/save-as flows, generate-app success/failure paths,
    delete/discard/close branches, and theme application without importing
    PyQt6.
- Result:
  - `flowforge_cli.jtbd_desktop.app` coverage increased from 24% to 62%.
  - Overall `flowforge-cli` rounded package coverage increased to 93%.
- Verification:
  - `uv run pytest tests/test_jtbd_desktop_app_helpers.py -q --cov=flowforge_cli.jtbd_desktop.app --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `8 passed`; `app.py` reached 62% coverage.
  - `uv run ruff check tests/test_jtbd_desktop_app_helpers.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_desktop_app_helpers.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `880 passed`, one optional `mmdc` skip, and
    overall package coverage 93%.
- Remaining risk:
  - Widget construction, visual-map drawing, and actual PyQt event-loop behavior
    remain uncovered in the default environment because PyQt6 is not installed.
    Reaching true 100% on this module likely needs either a PyQt-capable test
    lane or an adapter split that moves more UI logic behind GUI-independent
    collaborators.

## CLI coverage slice - desktop app full GUI-free coverage

- Baseline measurement:
  - After closing desktop app window-action coverage, rounded `flowforge-cli`
    package coverage was 93%.
  - `jtbd_desktop/app.py` was 62% covered; the remaining default-lane gap was
    widget construction, visual-map drawing, launcher success behavior, and
    dialog initialization.
- Action:
  - Extended the GUI-free desktop app helper tests with fake Qt signals,
    layouts, widgets, menus, toolbars, graphics scene items, launcher app/window
    objects, and transient fake `PyQt6` modules for `NewBundleDialog`
    construction.
  - Covered visual-map rendering, dependency selector refresh, widget factory
    helpers, table-panel mutation callbacks, launcher success paths, full
    `JtbdEditorWindow` construction, and `NewBundleDialog.__init__` without
    adding PyQt6 as a package dependency.
  - Closed the remaining partial branches for theme application, discard-cancel
    open flow, table stretching, and row serializer blank/default paths.
  - Fixed two pre-existing package-level ruff blockers: import placement in
    `commands/new.py` and an unnecessary f-string in `commands/simulate.py`.
- Result:
  - `flowforge_cli.jtbd_desktop.app` coverage increased from 62% to 100%.
  - Overall `flowforge-cli` rounded package coverage increased to 100%.
- Verification:
  - `uv run pytest tests/test_jtbd_desktop_app_helpers.py -q --cov=flowforge_cli.jtbd_desktop.app --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `14 passed`; `app.py` reached 100% line and
    branch coverage.
  - `uv run ruff check tests/test_jtbd_desktop_app_helpers.py`
    from `python/flowforge-cli`: clean.
  - `uv run pyright tests/test_jtbd_desktop_app_helpers.py`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run ruff check .`
    from `python/flowforge-cli`: clean.
  - `uv run pyright`
    from `python/flowforge-cli`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-cli`: `886 passed`, one optional `mmdc` skip, and
    overall package coverage 100%.
- Remaining risk:
  - The desktop editor is still verified through GUI-free fakes in the default
    lane. A real PyQt smoke test remains useful before final desktop readiness
    signoff, but the default package coverage gate is now fully closed.

## Closed-package coverage ratchet - flowforge-cli

- Baseline measurement:
  - `flowforge-cli` now reaches 100% statement and branch coverage in its
    package suite, but it was not yet part of the closed-package 100% coverage
    ratchet.
- Action:
  - Added `("flowforge-cli", "flowforge_cli")` to
    `scripts/audit_2026/closed_package_coverage.py`.
  - Updated the external release-gate ratchet test so future edits must keep
    `flowforge-cli` in the closed-package coverage list.
- Result:
  - `make audit-2026-closed-package-coverage` now includes `flowforge-cli`
    alongside the other completed shipping packages.
- Verification:
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`
    from the repo root: `17 passed`.
  - `uv run ruff check scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`
    from the repo root: clean.
  - `uv run pyright scripts/audit_2026/closed_package_coverage.py tests/audit_2026/test_E_73_external_release_gate.py`
    from the repo root: `0 errors`, `0 warnings`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`
    from the repo root: passed for 14 packages, including `flowforge-cli`.
  - Plain `make audit-2026-closed-package-coverage` still hit a local uv cache
    sandbox error under `~/.cache/uv`; rerunning with the audit-local
    `/private/tmp` uv cache resolved the environment issue.

## Package coverage slice - flowforge-jtbd-hub

- Baseline measurement:
  - `flowforge-jtbd-hub`: `66 passed`, 86% package coverage before this
    slice.
  - The largest gaps were FastAPI error mapping, registry trust/install edge
    cases, trust-file fallback/error paths, and one unused auth helper closure.
- Action:
  - Removed the unused `_require_admin` closure from the FastAPI app; all admin
    routes already use the narrower permission dependency.
  - Added API tests for auth header shimming, package detail success/404,
    invalid base64 publish, generic registry publish failures, install tamper
    and generic failures, missing package rating/demote/verified routes, and
    failing principal extractors.
  - Added registry tests for missing bundle hashes, verify-cache reuse,
    unsigned install audit events, untrusted override behavior, stored bundle
    tamper checks, tag/description/name search matching, scorer replacement,
    missing mutation targets, and best-effort audit hook failures.
  - Added trust resolver tests for missing env files, non-mapping YAML,
    absent/no-trust pyproject fallback, invalid pyproject trust tables, and
    merged verified-key settings.
  - Added `flowforge-jtbd-hub` to the closed-package coverage ratchet and
    release-gate ratchet test.
- Result:
  - `flowforge-jtbd-hub` now reaches 100% statement and branch coverage.
  - The closed-package coverage ratchet now tracks 15 packages.
- Verification:
  - `uv run pytest tests -q --cov=flowforge_jtbd_hub --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd-hub`: `90 passed`, package coverage 100%.
  - `uv run ruff check src tests`
    from `python/flowforge-jtbd-hub`: clean.
  - `uv run pyright src tests`
    from `python/flowforge-jtbd-hub`: `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q --tb=short`
    from the repo root: `17 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`
    from the repo root: passed for 15 packages, including `flowforge-jtbd-hub`.

## Package coverage slice - flowforge-jtbd support modules

- Baseline measurement:
  - `flowforge-jtbd`: `564 passed`, one optional skip, and 93% package coverage
    before this slice.
  - Large uncovered support gaps included the bundled Alembic env module,
    compliance catalog override/fallback parsing, and i18n key/loader/validator
    edge paths.
- Action:
  - Added hermetic Alembic env tests that fake the narrow `alembic.context` and
    `sqlalchemy.engine_from_config` surfaces, covering both offline and online
    migration paths without a live database.
  - Extended i18n tests for model-dump specs, malformed nested entries,
    object-id ownership, invalid filenames, invalid JSON, non-string catalog
    keys, and directory scans with non-file siblings.
  - Extended compliance catalog tests for environment override parsing,
    non-dict catalog entries, missing override paths, and packaged resource
    fallback behavior.
- Result:
  - `flowforge_jtbd.db.alembic_bundle.env`,
    `flowforge_jtbd.compliance.catalog`, `flowforge_jtbd.i18n.keys`,
    `flowforge_jtbd.i18n.loader`, and `flowforge_jtbd.i18n.validator` now reach
    100% statement and branch coverage in the focused gate.
  - Overall `flowforge-jtbd` rounded package coverage increased from 93% to
    95%.
- Verification:
  - `uv run pytest tests/ci/test_jtbd_alembic_env.py tests/unit/test_i18n.py tests/test_compliance_linter.py -q --cov=flowforge_jtbd.db.alembic_bundle.env --cov=flowforge_jtbd.i18n.keys --cov=flowforge_jtbd.i18n.loader --cov=flowforge_jtbd.i18n.validator --cov=flowforge_jtbd.compliance.catalog --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `70 passed`; all five targeted modules reached
    100% statement and branch coverage.
  - `uv run ruff check tests/ci/test_jtbd_alembic_env.py tests/unit/test_i18n.py tests/test_compliance_linter.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/ci/test_jtbd_alembic_env.py tests/unit/test_i18n.py tests/test_compliance_linter.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `575 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 95%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI/vector-store behavior, quality scoring,
    recommender edges, DSL/spec/exporter helpers, lint conflict edges, Claude LLM
    port branches, manifest serialization, and template cache branches.

## Package coverage slice - flowforge-jtbd pgvector store

- Baseline measurement:
  - `flowforge-jtbd`: 95% package coverage before this slice.
  - `flowforge_jtbd.ai.pgvector_store` was at 86% with uncovered optional
    dependency validation, async context-manager session handling, row coercion,
    and empty-golden recall branches.
- Action:
  - Added pgvector store tests for `from_extras` success, missing SQLAlchemy,
    missing asyncpg, and tolerated missing `pgvector-python` soft hints.
  - Added coverage for async context-manager session factories, dict and
    SQLAlchemy-style mapping rows, and recall measurement when a golden query has
    no expected ids.
- Result:
  - `flowforge_jtbd.ai.pgvector_store` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` rounded package coverage increased from 95% to
    96%.
- Verification:
  - `uv run pytest tests/unit/test_ai_pgvector_store.py -q --cov=flowforge_jtbd.ai.pgvector_store --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `31 passed`, targeted module coverage 100%.
  - `uv run ruff check tests/unit/test_ai_pgvector_store.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/unit/test_ai_pgvector_store.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/unit/test_ai_pgvector_store.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `582 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL/spec/exporter helpers, lint conflict edges, Claude LLM port branches,
    manifest serialization, and template cache branches.

## Package coverage slice - flowforge-jtbd canonical JSON

- Baseline measurement:
  - `flowforge_jtbd.dsl.canonical` had one uncovered explicit rejection path
    for unsupported non-JSON types in the full package coverage run.
- Action:
  - Added canonical JSON coverage for Pydantic model dumping and unsupported
    object rejection so the module is fully covered by its own focused test
    file.
  - Applied formatter normalization to the touched canonical JSON test file.
- Result:
  - `flowforge_jtbd.dsl.canonical` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 96% package coverage, with one
    fewer uncovered statement and one fewer partial branch.
- Verification:
  - `uv run pytest tests/ci/test_canonical_json.py -q --cov=flowforge_jtbd.dsl.canonical --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `17 passed`, targeted module coverage 100%.
  - `uv run ruff check tests/ci/test_canonical_json.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/ci/test_canonical_json.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/ci/test_canonical_json.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `585 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL lockfile/spec branches, exporter helpers, lint conflict edges, Claude
    LLM port branches, manifest serialization, and template cache branches.

## Package coverage slice - flowforge-jtbd lockfile canonical body

- Baseline measurement:
  - `flowforge_jtbd.dsl.lockfile` had two partial branch gaps in
    `JtbdLockfile.canonical_body` around model-dump keys and dumped pin shape.
- Action:
  - Simplified canonical body construction to use the model invariant that all
    `_BODY_KEYS` are present in `model_dump(mode="json", exclude_none=False)`.
  - Replaced the defensive pins shape branch with a typed cast and deterministic
    sort over dumped pin dictionaries.
  - Applied formatter normalization to the touched lockfile source file.
- Result:
  - `flowforge_jtbd.dsl.lockfile` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 96% package coverage, with two
    fewer partial branches.
- Verification:
  - `uv run pytest tests/ci/test_jtbd_lockfile.py tests/unit/test_E_47_acceptance.py -q --cov=flowforge_jtbd.dsl.lockfile --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `29 passed`, targeted module coverage 100%.
  - `uv run ruff check src/flowforge_jtbd/dsl/lockfile.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/dsl/lockfile.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/dsl/lockfile.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `585 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, exporter helpers, lint conflict edges, Claude LLM port
    branches, manifest serialization, and template cache branches.

## Package coverage slice - flowforge-jtbd registry manifest

- Baseline measurement:
  - `flowforge_jtbd.registry.manifest` had an uncovered malformed-bundle branch
    in `manifest_from_bundle`, where bundle hashing still succeeds but canonical
    spec hashing is unavailable.
- Action:
  - Added a registry manifest test for non-JSON bundle bytes, asserting
    `bundle_hash` is still populated and `spec_hash` is omitted.
  - Applied formatter normalization to the touched registry test file.
- Result:
  - `flowforge_jtbd.registry.manifest` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 96% package coverage, with two
    fewer uncovered statements.
- Verification:
  - `uv run pytest tests/test_registry.py -q --cov=flowforge_jtbd.registry.manifest --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `19 passed`, targeted module coverage 100%.
  - `uv run ruff check tests/test_registry.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/test_registry.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/test_registry.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `586 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, exporter helpers, lint conflict edges, Claude LLM port
    branches, and template cache branches.

## Package coverage slice - flowforge-jtbd exporters

- Baseline measurement:
  - `flowforge_jtbd.exporters.__init__` had uncovered module-level convenience
    helpers, and `flowforge_jtbd.exporters.storymap` had an uncovered
    data-capture sensitivity branch.
- Action:
  - Added module-level exporter helper coverage for `register`,
    `available_exporters`, and `export` through a temporary JSON exporter.
  - Added Story Map coverage for data-capture fields with explicit sensitivity
    metadata.
  - Applied formatter normalization to the touched exporter test file.
- Result:
  - `flowforge_jtbd.exporters.__init__`, `flowforge_jtbd.exporters.bpmn`, and
    `flowforge_jtbd.exporters.storymap` now reach 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` rounded package coverage increased from 96% to
    97%.
- Verification:
  - `uv run pytest tests/test_exporters.py -q --cov=flowforge_jtbd.exporters --cov=flowforge_jtbd.exporters.storymap --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `23 passed`, targeted exporter modules 100%.
  - `uv run ruff check tests/test_exporters.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/test_exporters.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/test_exporters.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `588 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 97%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, lint conflict edges, Claude LLM port branches, and
    template cache branches.

## Package coverage slice - flowforge-jtbd template cache

- Baseline measurement:
  - `flowforge_jtbd.templates.cache` had uncovered edge branches for a missing
    starter-template library, optional parameters without defaults, and
    pass-through extra parameters.
- Action:
  - Added tests for `TemplateCache.default()` when the adjacent `library/`
    directory is absent.
  - Added template instantiation coverage for optional parameters without
    defaults and forward-compatible extra params used by placeholders.
- Result:
  - `flowforge_jtbd.templates.cache` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 97% package coverage, with one
    fewer uncovered statement and three fewer partial branches.
- Verification:
  - `uv run pytest tests/unit/test_template_cache.py -q --cov=flowforge_jtbd.templates.cache --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `35 passed`, targeted module 100%.
  - `uv run ruff check tests/unit/test_template_cache.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/unit/test_template_cache.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/unit/test_template_cache.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `596 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 97%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, lint conflict edges, and Claude LLM port branches.

## Package coverage slice - flowforge-jtbd Claude LLM port

- Baseline measurement:
  - `flowforge_jtbd.ports.llm_claude` had uncovered lazy-SDK construction,
    non-text response block handling, object-form stream events, and non-text
    stream delta branches.
- Action:
  - Added fake Anthropic SDK construction coverage for the `api_key` path.
  - Added generation coverage that ignores non-text content blocks while
    preserving text blocks.
  - Added stream coverage for object-form deltas and non-text/unknown stream
    events that should be skipped.
- Result:
  - `flowforge_jtbd.ports.llm_claude` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 97% package coverage, with five
    fewer uncovered statements and six fewer partial branches.
- Verification:
  - `uv run pytest tests/unit/test_ports_llm_claude.py -q --cov=flowforge_jtbd.ports.llm_claude --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `13 passed`, targeted module 100%.
  - `uv run ruff check tests/unit/test_ports_llm_claude.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/unit/test_ports_llm_claude.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/unit/test_ports_llm_claude.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `599 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 97%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, and lint conflict edges.

## Package coverage slice - flowforge-jtbd glossary data-capture terms

- Baseline measurement:
  - `flowforge_jtbd.glossary` had uncovered forward-compatible
    `data_capture[].id` extraction branches and the non-list `data_capture`
    guard.
- Action:
  - Added bundle-derived catalog coverage for valid data-capture field ids while
    ignoring blank ids, non-string ids, and non-dict entries.
  - Added regression coverage that non-list `data_capture` extras do not create
    glossary terms.
- Result:
  - `flowforge_jtbd.glossary` now reaches 100% statement and branch coverage in
    the focused gate.
  - Overall `flowforge-jtbd` rounded package coverage increased from 97% to
    98%.
- Verification:
  - `uv run pytest tests/unit/test_glossary.py -q --cov=flowforge_jtbd.glossary --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `28 passed`, targeted module 100%.
  - `uv run ruff check tests/unit/test_glossary.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/unit/test_glossary.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/unit/test_glossary.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `601 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 98%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, and lint conflict edges.

## Package coverage slice - flowforge-jtbd lint conflict solver

- Baseline measurement:
  - `flowforge_jtbd.lint.conflicts` had uncovered branches for reader
    classification, duplicate-id self-pair skipping, empty-entity Z3 routing,
    and composition semantics validation failures.
  - The module also retained unused private pair-matching helpers from the
    pre-bucketed solver implementation.
- Action:
  - Removed the dead private pair-violation helpers now superseded by
    signature-bucketed rule iteration.
  - Added focused tests for `reads()`, duplicate-id self-pair suppression,
    Z3-backed empty entity partitions, invalid data/consistency values, and
    non-string entities.
- Result:
  - `flowforge_jtbd.lint.conflicts` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 98% package coverage, with all
    lint modules now closed at 100%.
- Verification:
  - `uv run pytest tests/unit/test_lint_conflicts.py -q --cov=flowforge_jtbd.lint.conflicts --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `28 passed`, targeted module 100%.
  - `uv run ruff check src/flowforge_jtbd/lint/conflicts.py tests/unit/test_lint_conflicts.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/lint/conflicts.py tests/unit/test_lint_conflicts.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/lint/conflicts.py tests/unit/test_lint_conflicts.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `607 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 98%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    and DSL spec branches.

## Package coverage slice - flowforge-jtbd DSL spec validators

- Baseline measurement:
  - `flowforge_jtbd.dsl.spec` had uncovered canonical-validator branches for
    empty semver values, empty semver suffixes, invalid packaging-version
    shapes, invalid `spec_hash` prefixes/digests, non-ASCII identifiers, and
    design hex-colour validation.
  - The design colour validator also had a redundant non-string guard despite
    receiving typed string values from Pydantic.
- Action:
  - Added focused canonical spec tests for explicit valid/invalid versions,
    valid/invalid spec hashes, non-ASCII ids, and design colour success/failure
    paths.
  - Removed the redundant non-string guard from `_hex_color`.
- Result:
  - `flowforge_jtbd.dsl.spec` now reaches 100% statement and branch coverage in
    the focused gate.
  - Overall `flowforge-jtbd` rounded package coverage increased from 98% to
    99%; remaining uncovered code is now isolated to AI quality scoring and
    recommendations.
- Verification:
  - `uv run pytest tests/ci/test_jtbd_spec.py -q --cov=flowforge_jtbd.dsl.spec --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `28 passed`, targeted module 100%.
  - `uv run ruff check src/flowforge_jtbd/dsl/spec.py tests/ci/test_jtbd_spec.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/dsl/spec.py tests/ci/test_jtbd_spec.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/dsl/spec.py tests/ci/test_jtbd_spec.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `619 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 99%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring and recommender
    edges.

## Package coverage slice - flowforge-jtbd AI quality and recommender

- Baseline measurement:
  - `flowforge_jtbd.ai.quality` had uncovered branches for overly long
    narrative fields, one/two solution-coupled phrase buckets, async
    heuristic fallback, LLM exception/no-JSON handling, and non-list
    `success_criteria` extraction.
  - `flowforge_jtbd.ai.recommender` had uncovered branches for frozen
    bag-of-words fitting/embedding, empty-token corpus entries, legacy
    pre-freeze transform paths, zero vectors, invalid `top_k`, and
    `jtbd_id` fallback indexing.
  - Both modules also had impossible private defensive branches that could not
    be reached through their public contracts.
- Action:
  - Added public behavior tests for the remaining quality scorer and
    recommender paths, including frozen vocabulary error handling.
  - Removed the impossible empty-average branch in the quality scorer and the
    impossible lazy-embed zero-norm branch in the recommender.
- Result:
  - `flowforge_jtbd.ai.quality` and `flowforge_jtbd.ai.recommender` now reach
    100% statement and branch coverage in the focused gate.
  - `flowforge-jtbd` now reaches 100% statement and branch coverage for the
    entire package.
- Verification:
  - `uv run pytest tests/unit/test_quality_scorer.py tests/unit/test_recommender.py -q --cov=flowforge_jtbd.ai.quality --cov=flowforge_jtbd.ai.recommender --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `76 passed`, one expected in-memory
    embedding-store performance warning, targeted modules 100%.
  - `uv run ruff check src/flowforge_jtbd/ai/quality.py src/flowforge_jtbd/ai/recommender.py tests/unit/test_quality_scorer.py tests/unit/test_recommender.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/ai/quality.py src/flowforge_jtbd/ai/recommender.py tests/unit/test_quality_scorer.py tests/unit/test_recommender.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/ai/quality.py src/flowforge_jtbd/ai/recommender.py tests/unit/test_quality_scorer.py tests/unit/test_recommender.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `639 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and required package
    coverage 100% reached.
- Remaining risk:
  - `flowforge-jtbd` has reached the closed-package coverage ratchet. Broader
    PyPI readiness still depends on the repository-wide release gates and
    external environment checks already tracked elsewhere in this log.

## Gate hardening slice - include flowforge-jtbd in closed-package coverage

- Baseline measurement:
  - `flowforge-jtbd` is listed as a PyPI-publishable strategic package, but the
    `audit-2026-closed-package-coverage` ratchet did not include it.
- Action:
  - Added `flowforge-jtbd` / `flowforge_jtbd` to
    `scripts/audit_2026/closed_package_coverage.py`.
- Result:
  - The closed-package 100% statement/branch coverage gate now covers 16
    packages, including `flowforge-jtbd`.
- Verification:
  - Initial `make audit-2026-closed-package-coverage` hit the local sandbox's
    unwritable default uv cache under `~/.cache`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`
    from repo root: passed for 16 packages. Notable package counts included
    `flowforge-core` `181 passed`, `flowforge-cli` `886 passed, 1 skipped`,
    `flowforge-jtbd` `639 passed, 1 skipped`, and final
    `closed-package-coverage: passed for 16 packages`.
- Remaining risk:
  - Push remains blocked locally by GitHub HTTPS credentials; external release
    gates still require their browser/Postgres-capable environments.

## PyPI readiness rerun after JTBD coverage ratchet

- Baseline measurement:
  - After adding `flowforge-jtbd` to the closed-package coverage gate, the
    publishable package set needed a fresh artifact build/check/smoke proof.
- Action:
  - Reran the canonical PyPI build target with the writable uv cache used by
    local audit runs.
- Result:
  - All 16 strategic packages built as wheels and sdists.
  - `twine check` passed for all 32 artifacts.
  - A clean virtualenv installed `flowforge-cli` from the built wheel set, which
    pulled in `flowforge-jtbd`, and `flowforge --help` ran successfully.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`
    from repo root: `pypi-build-smoke: passed for 16 packages and 32 artifacts`.
- Remaining risk:
  - This is local artifact readiness proof. Actual publication still requires
    release credentials and external release-gate evidence.

## Package coverage slice - flowforge-jtbd i18n and actor lint

- Baseline measurement:
  - `flowforge_jtbd.i18n.catalog` had uncovered public accessors for catalog
    length, keys, and registry language presence.
  - `flowforge_jtbd.lint.actors` had an uncovered no-conflict path for
    different capacities and a dead duplicate-pair guard inside the conflict
    subset helper.
- Action:
  - Added catalog tests for `len`, `keys`, and `LocaleRegistry.has`.
  - Added actor lint coverage for two different non-conflicting capacities in
    the same role/context.
  - Removed the unreachable duplicate-pair guard from `_conflicting_subsets`;
    pairs are generated from a unique sorted capacity set.
- Result:
  - `flowforge_jtbd.i18n.catalog` and `flowforge_jtbd.lint.actors` now reach
    100% statement and branch coverage in focused gates.
  - Overall `flowforge-jtbd` remains at rounded 97% package coverage, with four
    fewer uncovered statements and two fewer partial branches.
- Verification:
  - `uv run pytest tests/unit/test_i18n.py tests/unit/test_lint_actors.py -q --cov=flowforge_jtbd.i18n.catalog --cov=flowforge_jtbd.lint.actors --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `56 passed`, targeted modules 100%.
  - `uv run ruff check src/flowforge_jtbd/lint/actors.py tests/unit/test_lint_actors.py tests/unit/test_i18n.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/lint/actors.py tests/unit/test_lint_actors.py tests/unit/test_i18n.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/lint/actors.py tests/unit/test_lint_actors.py tests/unit/test_i18n.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `591 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 97%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, lint conflict/dependency/lifecycle/linter edges, Claude
    LLM port branches, and template cache branches.

## Package coverage slice - flowforge-jtbd lint graph and orchestration

- Baseline measurement:
  - `flowforge_jtbd.lint.dependencies` had an unreachable defensive cycle-path
    bound after Tarjan SCC detection.
  - `flowforge_jtbd.lint.lifecycle` lacked coverage for delegated optional
    stages suppressing optional-stage hints.
  - `flowforge_jtbd.lint.linter` lacked coverage for actor analyzer issues
    attached to JTBD ids outside the bundle.
- Action:
  - Removed the impossible dependency-cycle bound; SCC materialisation already
    walks within a strongly connected component and exits when the path returns
    to the start.
  - Added lifecycle coverage for an `undo` stage delegated to another JTBD.
  - Added linter orchestration coverage that buckets detached actor issues into
    `bundle_issues`.
- Result:
  - `flowforge_jtbd.lint.dependencies`, `flowforge_jtbd.lint.lifecycle`, and
    `flowforge_jtbd.lint.linter` now reach 100% statement and branch coverage
    in focused gates.
  - Overall `flowforge-jtbd` remains at rounded 97% package coverage, with
    three fewer uncovered statements and three fewer partial branches.
- Verification:
  - `uv run pytest tests/unit/test_lint_dependencies.py tests/unit/test_lint_lifecycle.py tests/unit/test_linter.py -q --cov=flowforge_jtbd.lint.dependencies --cov=flowforge_jtbd.lint.lifecycle --cov=flowforge_jtbd.lint.linter --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `28 passed`, targeted modules 100%.
  - `uv run ruff check src/flowforge_jtbd/lint/dependencies.py tests/unit/test_lint_lifecycle.py tests/unit/test_linter.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/lint/dependencies.py tests/unit/test_lint_lifecycle.py tests/unit/test_linter.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/lint/dependencies.py tests/unit/test_lint_lifecycle.py tests/unit/test_linter.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `593 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 97%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL spec branches, lint conflict edges, Claude LLM port branches, and
    template cache branches.

## Package coverage slice - flowforge-jtbd audit logger

- Baseline measurement:
  - `flowforge_jtbd.audit` had one uncovered branch in
    `JtbdAuditLogger.record_deprecated` when caller-supplied extra fields are
    merged with `replaced_by` metadata.
- Action:
  - Added a logger regression test that records a deprecated spec with both
    `replaced_by` and an additional reason field.
  - Applied formatter normalization to the touched audit test file.
- Result:
  - `flowforge_jtbd.audit` now reaches 100% statement and branch coverage in the
    focused gate.
  - Overall `flowforge-jtbd` remains at rounded 96% package coverage, with one
    fewer uncovered statement and one fewer partial branch.
- Verification:
  - `uv run pytest tests/test_jtbd_audit.py -q --cov=flowforge_jtbd.audit --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `21 passed`, targeted module coverage 100%.
  - `uv run ruff check tests/test_jtbd_audit.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check tests/test_jtbd_audit.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright tests/test_jtbd_audit.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `583 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    database comment branch handling, DSL/spec/exporter helpers, lint conflict
    edges, Claude LLM port branches, manifest serialization, and template cache
    branches.

## Package coverage slice - flowforge-jtbd comment models

- Baseline measurement:
  - `flowforge_jtbd.db.comments` had one unreachable defensive branch in
    `extract_mentions` after a regex match that always supplies one capture
    group.
- Action:
  - Removed the impossible `None` guard from mention extraction.
  - Moved the regex import to module import scope and applied formatter
    normalization to the touched source file.
- Result:
  - `flowforge_jtbd.db.comments` now reaches 100% statement and branch coverage
    in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 96% package coverage, with one
    fewer uncovered statement and one fewer partial branch.
- Verification:
  - `uv run pytest tests/unit/test_comments.py -q --cov=flowforge_jtbd.db.comments --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `29 passed`, targeted module coverage 100%.
  - `uv run ruff check src/flowforge_jtbd/db/comments.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/db/comments.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/db/comments.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `583 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL/spec/exporter helpers, lint conflict edges, Claude LLM port branches,
    manifest serialization, and template cache branches.

## Package coverage slice - flowforge-jtbd NL generator

- Baseline measurement:
  - `flowforge_jtbd.ai.nl_to_jtbd` had two partial branch gaps in defensive
    dedupe loops for inferred compliance and sensitivity tags.
- Action:
  - Removed unreachable dedupe loops; both inference helpers iterate unique
    dictionary keys and can return their ordered hit lists directly.
  - Applied formatter normalization to the touched source file.
- Result:
  - `flowforge_jtbd.ai.nl_to_jtbd` now reaches 100% statement and branch
    coverage in the focused gate.
  - Overall `flowforge-jtbd` remains at rounded 96% package coverage, with one
    AI module fully closed and fewer total statements/branches.
- Verification:
  - `uv run pytest tests/unit/test_ai_nl_to_jtbd.py -q --cov=flowforge_jtbd.ai.nl_to_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-jtbd`: `19 passed`, targeted module coverage 100%.
  - `uv run ruff check src/flowforge_jtbd/ai/nl_to_jtbd.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run ruff format --check src/flowforge_jtbd/ai/nl_to_jtbd.py`
    from `python/flowforge-jtbd`: clean.
  - `uv run pyright src/flowforge_jtbd/ai/nl_to_jtbd.py`
    from `python/flowforge-jtbd`: `0 errors`, `0 warnings`.
  - `uv run pytest tests -q --cov=flowforge_jtbd --cov-branch --cov-report=term-missing --cov-fail-under=0`
    from `python/flowforge-jtbd`: `582 passed`, one optional skip, one expected
    in-memory embedding-store performance warning, and package coverage 96%.
- Remaining risk:
  - `flowforge-jtbd` is not yet ready for the closed-package coverage ratchet.
    Remaining gaps are concentrated in AI quality scoring, recommender edges,
    DSL/spec/exporter helpers, lint conflict edges, Claude LLM port branches,
    manifest serialization, and template cache branches.

## Release-local rerun after flowforge-jtbd coverage ratchet

- Baseline measurement:
  - After `flowforge-jtbd` reached 100% statement and branch coverage and joined
    `scripts/audit_2026/closed_package_coverage.py`, the local release gate
    exposed two stale audit ratchets:
    - `tests/audit_2026/test_E_73_external_release_gate.py` still expected 15
      closed packages and omitted `("flowforge-jtbd", "flowforge_jtbd")`.
    - `tests/audit_2026/test_E_75_polish_copy_release_gate.py` still expected
      `actions/upload-artifact@v4` even though the secret-bearing workflow pins
      `actions/upload-artifact` to the reviewed SHA and leaves `# v4` as the
      human-readable version annotation.
- Action:
  - Added `flowforge-jtbd` to the closed-package coverage ratchet assertion.
  - Updated the polish-copy sidecar workflow ratchet to require the reviewed
    pinned `actions/upload-artifact` SHA plus the `# v4` annotation instead of
    requiring an unsafe mutable `@v4` action ref.
- Result:
  - The focused ratchets pass.
  - The full fail-closed local release gate passes with all local lanes green.
  - Closed package coverage now passes for 16 packages, including
    `flowforge-jtbd`, all at 100% statement and branch coverage.
  - PyPI build smoke passes for 16 packages and 32 artifacts, including
    `flowforge-jtbd`, with `twine check` passing and a clean-venv
    `flowforge --help` console-script smoke.
- Verification:
  - `uv run ruff check tests/audit_2026/test_E_73_external_release_gate.py tests/audit_2026/test_E_75_polish_copy_release_gate.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_73_external_release_gate.py tests/audit_2026/test_E_75_polish_copy_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_closed_package_coverage_ratchet_tracks_completed_packages tests/audit_2026/test_E_75_polish_copy_release_gate.py::test_polish_copy_sidecar_authoring_workflow_uploads_review_candidate -q`:
    `2 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local`:
    `audit-2026-release-local: fail-closed local release gate passed`;
    integration summary `365` local tests passed and `0` failed; closed-package
    coverage passed for 16 packages; PyPI build smoke passed for 16 packages
    and 32 artifacts.
- Remaining risk:
  - The local gate still records the documented external release checks as
    required: visual DOM baselines, browser Playwright full-stack, reviewed
    polish-copy sidecar, optional downstream UMS parity, and live Postgres
    contention/drain verification.

## External release gate diagnostic hardening

- Baseline measurement:
  - Current-commit external release preflight passes when pointed at local
    Postgres:
    `FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres make audit-2026-release-external-preflight`
    reported `ok`.
  - The reviewed polish-copy sidecar gate passes:
    `make audit-2026-polish-copy-sidecar` reported `ok`.
  - Live Postgres release checks pass locally with the same URL:
    `make audit-2026-live-postgres` reported `4 passed`.
  - The full external release target passed preflight and PyPI build/check/smoke
    for 16 packages and 32 artifacts, then stopped at the DOM browser lane
    because Chromium cannot launch inside this macOS sandbox:
    `MachPortRendezvousServer permission denied`.
  - Before installing a browser cache under `/private/tmp/flowforge-ms-playwright`,
    the DOM and browser-full-stack wrappers also exposed a second local
    bootstrap failure mode: Playwright was installed but the Chromium executable
    was missing.
- Action:
  - Added explicit missing-Chromium detection to the DOM visual wrapper.
  - Added Playwright output capture and explicit missing-Chromium /
    macOS-sandbox launch diagnostics to the browser full-stack wrapper.
  - Added audit ratchets so both wrappers continue to document actionable
    Chromium install and browser-capable-CI guidance.
- Result:
  - Local skip-mode runs now explain the precise browser prerequisite or macOS
    sandbox blocker instead of returning only a generic Playwright failure.
  - Release mode remains fail-closed; these diagnostics do not permit skip flags
    in release qualification.
- Verification:
  - `uv run pytest tests/audit_2026/test_E_72_browser_full_stack_e2e.py -q`:
    `4 passed`.
  - `uv run ruff check tests/audit_2026/test_E_72_browser_full_stack_e2e.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_72_browser_full_stack_e2e.py`:
    `0 errors`, `0 warnings`.
  - `bash -n scripts/run_browser_full_stack.sh scripts/visual_regression/run_dom_snapshots.sh`:
    clean.
  - `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/flowforge-ms-playwright VISREG_ALLOW_SKIP=1 make audit-2026-visual-regression-dom`:
    clean local skip with `Playwright Chromium cannot launch in this macOS sandbox`.
  - `PLAYWRIGHT_BROWSERS_PATH=/private/tmp/flowforge-ms-playwright BROWSER_E2E_ALLOW_SKIP=1 make audit-2026-browser-e2e`:
    clean local skip with the same macOS sandbox diagnostic.
- Remaining risk:
  - Browser DOM and browser full-stack release qualification still require an
    unsandboxed terminal or browser-capable CI runner; the local macOS sandbox
    cannot provide that proof even with Chromium installed under `/private/tmp`.
  - `git push` remains blocked locally by missing GitHub HTTPS credentials, so
    current-commit external GitHub Actions evidence cannot be refreshed from
    this session.

## Release package-set ratchet hardening

- Code review finding:
  - `scripts/audit_2026/pypi_build_smoke.py` and
    `scripts/audit_2026/closed_package_coverage.py` both hard-coded the current
    16 shipping package directories. That was correct for the current package
    set, but it created a fail-open maintenance path: if a domain package later
    flips `[tool.uv].package = true`, PyPI build smoke and the 100% coverage
    gate could silently omit it until someone remembered to edit both scripts.
- Action:
  - Added `scripts/audit_2026/package_sets.py` as the shared source of truth for
    shipping Python packages.
  - Both PyPI build smoke and closed-package coverage now derive package
    directories from root `[tool.uv.workspace].members` and include only members
    whose package flag is enabled.
  - Closed-package coverage derives the import package from each package's
    Hatch wheel package declaration instead of duplicating module names.
  - The shared package-set helper fails closed if a shipping wheel declares
    zero, multiple, or non-`src/` wheel package paths; coverage must not
    silently check only the first import package.
  - Updated external-release ratchets to require workspace-derived discovery
    and to forbid the old `STRATEGIC_PACKAGES` /
    `CLOSED_PACKAGE_COVERAGE` static lists.
- Result:
  - The current set still resolves to 16 shipping packages and 30 workspace-only
    domain packages, but future package flips will automatically enter PyPI
    artifact and 100% coverage gates.
- Verification:
  - `uv run ruff check scripts/audit_2026/package_sets.py scripts/audit_2026/closed_package_coverage.py scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/package_sets.py scripts/audit_2026/closed_package_coverage.py scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/package_sets.py scripts/audit_2026/closed_package_coverage.py scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke tests/audit_2026/test_E_73_external_release_gate.py::test_closed_package_coverage_ratchet_tracks_completed_packages -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_package_set_helper_rejects_ambiguous_wheel_packages -q`:
    `1 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts and completed clean-venv
    `flowforge --help` smoke.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-closed-package-coverage`:
    `closed-package-coverage: passed for 16 packages`, all at 100% statement
    and branch coverage.
  - `uv run python scripts/audit_2026/closed_package_coverage.py` after the
    fail-closed wheel-package guard change: `closed-package-coverage: passed
    for 16 packages`.
- Remaining risk:
  - The five strategic domain-content candidates remain intentionally
    workspace-only until named SME signoff, publishable packaging, and release
    review are complete.
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## Current-commit local release rerun after package-set guard

- Trigger:
  - After committing workspace-derived package-set discovery and the
    fail-closed ambiguous-wheel guard, reran the local release gate against the
    current branch head.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local`:
    `audit-2026-release-local: fail-closed local release gate passed`.
  - The run included ratchets, conformance, audit unit tests, property tests,
    integration/e2e, Python and JS cross-runtime parity, edge cases,
    observability, core/property/i18n coverage gates, 16-package closed-package
    coverage at 100% statement/branch, 16-package / 32-artifact PyPI build and
    `twine check`, clean-venv `flowforge --help`, and signoff validation.
- Remaining risk:
  - The local release gate still correctly records external release checks as
    required: visual DOM baselines, browser Playwright full-stack, reviewed
    polish-copy sidecar, optional downstream UMS parity, and live Postgres
    contention/drain verification.
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI typing marker audit

- Code/design audit finding:
  - The 16 shipping packages declared the `Typing :: Typed` classifier in
    their PyPI metadata, but none shipped a PEP 561 `py.typed` marker. That
    made the published-wheel contract misleading for downstream type checkers.
- Action:
  - Added `py.typed` markers to every shipping import package:
    `flowforge`, `flowforge_fastapi`, `flowforge_sqlalchemy`,
    `flowforge_tenancy`, `flowforge_audit_pg`, `flowforge_outbox_pg`,
    `flowforge_rbac_static`, `flowforge_rbac_spicedb`,
    `flowforge_documents_s3`, `flowforge_money`, `flowforge_signing_kms`,
    `flowforge_notify_multichannel`, `flowforge_otel`, `flowforge_cli`,
    `flowforge_jtbd`, and `flowforge_jtbd_hub`.
  - Added an audit ratchet that requires any shipping package with
    `Typing :: Typed` to have a source `py.typed` marker.
  - Hardened `scripts/audit_2026/pypi_build_smoke.py` to inspect built wheels
    and fail if any shipping import package is missing `py.typed` in the wheel
    payload.
  - Tightened the PyPI build smoke to require exactly one wheel and one sdist
    per shipping package, not only the aggregate artifact count.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_shipping_packages_declared_typed_have_pep561_markers tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified wheel `py.typed`
    markers, and completed clean-venv `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## CLI i18n default-context audit

- Code review finding:
  - The generated `useT.ts` hook preserved `project.languages[0]` as
    `DEFAULT_LANGUAGE`, but its default React context always used the generated
    fallback/source catalog. When a bundle declared a translated locale first,
    hosts using the generated hook without a custom provider could render the
    fallback source language instead of the declared default language.
- Action:
  - Updated the i18n generator to import the declared default catalog
    separately from the fallback/source catalog.
  - Changed the generated default context to use `DEFAULT_LANGUAGE` plus the
    default catalog, while keeping the fallback catalog available for missing or
    empty translation values.
  - Added tests for same-locale default/fallback output and non-English default
    language output with English/source fallback.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check src/flowforge_cli/jtbd/generators/i18n.py tests/test_i18n_generator.py`
    from `python/flowforge-cli`: clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright src/flowforge_cli/jtbd/generators/i18n.py tests/test_i18n_generator.py`
    from `python/flowforge-cli`: `0 errors, 0 warnings, 0 informations`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q`
    from `python/flowforge-cli`: `51 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q --cov=flowforge_cli.jtbd.generators.i18n --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `51 passed`, targeted i18n generator coverage
    stayed at 100% statement and branch coverage.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `887 passed, 1 skipped`, package coverage
    stayed at 100% statement and branch coverage.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`
    from the repo root: built 16 packages / 32 artifacts, passed `twine check`,
    installed all shipping wheels into a clean venv, imported all 16 shipping
    packages, completed `flowforge --help`, and finished with
    `pypi-build-smoke: passed`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## CLI locale-list normalization audit

- Code/design audit finding:
  - `project.languages` and `project.currencies` were normalized as raw
    tuples. Duplicate locale declarations could therefore produce duplicate
    generated catalog paths and duplicate `AVAILABLE_LANGUAGES` entries in
    `useT.ts`, while duplicate currency declarations could leak into downstream
    project consumers. The pipeline's later path dedupe masked part of the
    issue, but direct generator output and generated metadata were still noisy.
- Action:
  - Added order-preserving project-list deduplication in JTBD normalization for
    languages and currencies. The first entry remains authoritative so default
    locale/currency semantics are unchanged.
  - Added an i18n regression test proving duplicate locale/currency input is
    normalized to first-seen unique values and emits one catalog per locale.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check src/flowforge_cli/jtbd/normalize.py tests/test_i18n_generator.py`
    from `python/flowforge-cli`: clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright src/flowforge_cli/jtbd/normalize.py tests/test_i18n_generator.py`
    from `python/flowforge-cli`: `0 errors, 0 warnings, 0 informations`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q`
    from `python/flowforge-cli`: `52 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q --cov=flowforge_cli.jtbd.generators.i18n --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `52 passed`, targeted i18n generator coverage
    stayed at 100% statement and branch coverage.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `888 passed, 1 skipped`, package coverage
    stayed at 100% statement and branch coverage.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`
    from the repo root: built 16 packages / 32 artifacts, passed `twine check`,
    installed all shipping wheels into a clean venv, imported all 16 shipping
    packages, completed `flowforge --help`, and finished with
    `pypi-build-smoke: passed`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## CLI generated useT TypeScript proof audit

- Code review finding:
  - The existing generated TypeScript syntax gate only wrote generated `.tsx`
    files into its temporary compiler project. It did not compile the generated
    `useT.ts` hook, so catalog import-shape mistakes in the default/fallback
    i18n hook could pass with only string-level assertions.
- Action:
  - Added a focused `tsc` proof for generated `useT.ts`. The test writes the
    generated hook plus JSON catalogs into a temporary TypeScript project,
    stubs the minimal React API used by the hook, enables JSON module imports,
    and compiles both same-locale and non-English-default locale shapes.
  - The harness uses modern bundler module resolution so current TypeScript
    versions do not fail on deprecated `node10` resolution before checking the
    generated hook.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check tests/test_i18n_generator.py`
    from `python/flowforge-cli`: clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright tests/test_i18n_generator.py`
    from `python/flowforge-cli`: `0 errors, 0 warnings, 0 informations`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q`
    from `python/flowforge-cli`: `54 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q --cov=flowforge_cli.jtbd.generators.i18n --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `54 passed`, targeted i18n generator coverage
    stayed at 100% statement and branch coverage.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `890 passed, 1 skipped`, package coverage
    stayed at 100% statement and branch coverage.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## CLI Step translation-key closure audit

- Code review finding:
  - The generated real Step component asserted representative translation calls,
    but did not prove every literal `t("...")` key used by the component exists
    in the generated catalog and `TranslationKey` union. A future template edit
    could therefore introduce a dead translation key while string-presence tests
    still passed.
- Action:
  - Added a regression that extracts literal `t("...")` calls from generated
    real-path `Step.tsx`, verifies every key exists in `en.json`, and verifies
    each key is emitted in `useT.ts`.
  - Added coverage for the dynamic PII field label path by checking the
    generated template literal and concrete PII field label key in both the
    catalog and type union.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check tests/test_i18n_generator.py`
    from `python/flowforge-cli`: clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright tests/test_i18n_generator.py`
    from `python/flowforge-cli`: `0 errors, 0 warnings, 0 informations`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q`
    from `python/flowforge-cli`: `55 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/test_i18n_generator.py -q --cov=flowforge_cli.jtbd.generators.i18n --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `55 passed`, targeted i18n generator coverage
    stayed at 100% statement and branch coverage.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests -q --cov=flowforge_cli --cov-branch --cov-report=term-missing --cov-fail-under=100`
    from `python/flowforge-cli`: `891 passed, 1 skipped`, package coverage
    stayed at 100% statement and branch coverage.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI release version coherence audit

- Code review finding:
  - The PyPI smoke enforced exact internal Flowforge dependency bounds but kept
    the release line hard-coded as `>=0.1.0,<0.2.0`, while release guidance
    requires all shipping packages to move together. A future minor release
    could therefore pass source ratchets with stale internal dependency bounds
    or mixed-version artifacts.
- Action:
  - Added a shared release-version gate to the PyPI smoke. It now requires
    every shipping package to declare the same `project.version`, validates
    that the version starts with `MAJOR.MINOR.PATCH`, derives the expected
    internal dependency window from that release line, and verifies every built
    wheel and sdist filename version matches the release version.
  - Updated internal dependency metadata checks to compare artifact
    `Requires-Dist` entries with the dynamically derived release window rather
    than fixed `0.1.x` constants.
  - Added regression tests for mixed shipping package versions, derived
    dependency windows, artifact-version drift, and the source dependency
    ratchet.
  - Updated the publishing guide so release operators know version bumps must
    keep every shipping package on one release line and that the PyPI smoke
    derives internal dependency bounds from that version.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `1 file reformatted, 1 file left unchanged`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - Focused release-version/docs tests:
    `5 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `48 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built 16 packages / 32 artifacts in a temporary readiness directory, passed
    `twine check` on every artifact, installed all 16 wheels into a clean venv,
    imported all 16 shipping packages, completed `flowforge --help`, and
    verified artifact versions plus dynamically derived internal dependency
    bounds.
  - `git diff --check`: clean.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.
  - Full external release proof still requires browser-capable CI or an
    unsandboxed browser environment.

## Publishing guide metadata alignment audit

- Code/design audit finding:
  - `docs/release/PUBLISHING.md` still described the 30 workspace-only domain
    packages as `flowforge-jtbd-*-starter` packages, but the actual package
    names are `flowforge-jtbd-*`; only some are starter-scaffolded, and the
    five strategic domain-content candidates are a subset of the same
    workspace-only 30 packages rather than a separate publishable set.
  - The same guide did not yet mention the stricter PyPI build smoke checks for
    exact wheel/sdist counts and wheel-level `py.typed` markers.
- Action:
  - Updated the publishing guide to describe the 16 shipping packages and the
    30 workspace-only domain packages directly from the current release model.
  - Clarified that insurance, healthcare, banking, gov, and hr are
    workspace-only strategic domain-content candidates until named SME signoff,
    publishable packaging, and release review are complete.
  - Added an audit ratchet that requires every package discovered as shipping
    to carry complete PyPI publication metadata.
  - Extended the publishing-doc ratchet to reject the stale
    `flowforge-jtbd-*-starter` package-name pattern and require documentation
    of exact wheel/sdist and `py.typed` checks.
  - Removed the manually maintained shell build loop from the publishing guide;
    the guide now points release builders at the workspace-derived
    `make audit-2026-pypi-build` gate and its `package_sets.py` source of
    truth.
- Verification:
  - `uv run ruff check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_shipping_packages_have_pypi_publication_metadata tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI metadata stamper package-source audit

- Code review finding:
  - `scripts/finalize_pypi_metadata.py` still maintained its own static
    `STRATEGIC_PACKAGES` list even though PyPI build smoke, closed-package
    coverage, and the publishing guide now use workspace-derived shipping
    package discovery. A future `[tool.uv] package = true` flip could have
    entered build/coverage gates while the metadata stamper silently skipped
    the new package.
- Action:
  - Routed the metadata stamper through
    `scripts/audit_2026/package_sets.py::shipping_packages()`.
  - Made missing per-package keyword metadata fail closed instead of falling
    back to generic `"workflow"` keywords.
  - Corrected the helper docstring to describe the actual SPDX
    `license = "Apache-2.0"` metadata and the canonical
    `make audit-2026-pypi-build` validation command.
  - Added a release ratchet that forbids a local `STRATEGIC_PACKAGES` list in
    the metadata stamper.
- Verification:
  - `uv run ruff check scripts/finalize_pypi_metadata.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/finalize_pypi_metadata.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/finalize_pypi_metadata.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_metadata_stamper_uses_workspace_shipping_packages -q`:
    `1 passed`.
  - `uv run python scripts/finalize_pypi_metadata.py`:
    `stamped 0`, `skipped 16`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact identity audit

- Code review finding:
  - `scripts/audit_2026/pypi_build_smoke.py` verified aggregate wheel/sdist
    counts for the shipping package set, but it did not prove that the artifact
    directory contained exactly one wheel and one sdist for each expected
    distribution name. A duplicate build artifact could have masked a missing
    non-CLI distribution until publish-time review.
- Action:
  - Added the PyPI distribution name to the shared shipping-package discovery
    model.
  - Added a build-smoke assertion that groups wheels and sdists by normalized
    distribution name, rejects missing, duplicate, or unexpected distributions,
    and then checks each package's `py.typed` marker inside that package's own
    wheel.
  - Added a release ratchet for duplicate/missing artifact detection.
- Verification:
  - `uv run ruff check scripts/audit_2026/package_sets.py scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/package_sets.py scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/package_sets.py scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_missing_or_duplicate_package_artifacts tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified exact
    wheel/sdist identity by shipping distribution, verified wheel `py.typed`
    markers, and completed clean-venv `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## Shipping package identity audit

- Code review finding:
  - The shared `scripts/audit_2026/package_sets.py` helper now feeds PyPI
    build smoke, closed-package coverage, and metadata stamping, but it did
    not fail closed if two shipping workspace members declared the same
    `project.name` or wheel import package. Duplicate identities could make a
    later release gate check the same PyPI/import surface twice while silently
    omitting another package.
- Action:
  - Added a source-of-truth uniqueness guard for shipping distribution names
    and import packages. Distribution-name uniqueness uses PyPI/wheel
    normalization so `flowforge-core` and `flowforge_core` cannot pass as
    distinct release identities.
  - Added a release ratchet that duplicate shipping identities raise
    `SystemExit` before downstream build or coverage gates run.
- Verification:
  - `uv run ruff check scripts/audit_2026/package_sets.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/package_sets.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/package_sets.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_package_set_helper_rejects_duplicate_shipping_identities tests/audit_2026/test_E_73_external_release_gate.py::test_package_set_helper_rejects_ambiguous_wheel_packages -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `23 passed`.
  - `uv run python -c "import sys; sys.path.insert(0, 'scripts/audit_2026'); import package_sets; packages = package_sets.shipping_packages(); print(len(packages)); print(len({package_sets._distribution_key(p.distribution_name) for p in packages})); print(len({p.import_package for p in packages}))"`:
    `16`, `16`, `16`.
  - `uv run python scripts/finalize_pypi_metadata.py`:
    `stamped 0`, `skipped 16`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts and completed clean-venv
    `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## Internal dependency bound ratchet audit

- Code review finding:
  - The PyPI dependency-bound ratchet only checked a hard-coded subset of
    internal Flowforge package names. The current workspace has 46 Python
    packages, so a newly added internal dependency on any omitted package could
    have appeared without the `>=0.1.0,<0.2.0` compatibility bound required for
    publishable wheels.
- Action:
  - Changed the ratchet to derive the internal package-name set from the root
    Python workspace members instead of a local literal.
  - Normalized dependency and project names with the same PyPI/wheel
    distribution-key rules used by package discovery.
  - Added count and representative-package assertions so the test proves it is
    covering the full 46-package internal namespace, including shipping and
    workspace-only domain packages.
- Verification:
  - `uv run ruff check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_internal_python_dependencies_are_compatibly_bounded -q`:
    `1 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `23 passed`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI license file artifact audit

- Code review finding:
  - Shipping packages declare `license-files = ["LICENSE"]`, but the PyPI
    build smoke only relied on `twine check` and metadata-level ratchets. It
    did not inspect the built wheel and sdist payloads to prove that every
    published artifact actually contains the declared license file.
- Action:
  - Hardened `scripts/audit_2026/pypi_build_smoke.py` to inspect each matched
    wheel and sdist and fail closed when a wheel lacks
    `.dist-info/licenses/LICENSE` or an sdist lacks a top-level `LICENSE`.
  - Updated the publishing guide to document license-file payload validation
    as part of `make audit-2026-pypi-build`.
  - Added a focused ratchet that builds minimal license-less wheel/sdist
    artifacts and verifies the smoke helper rejects them.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_artifacts_missing_license_files tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `24 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified declared license
    files in wheel/sdist payloads, and completed clean-venv
    `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI clean-venv import smoke audit

- Code review finding:
  - `make audit-2026-pypi-build` installed only `flowforge-cli` from the built
    artifacts before running `flowforge --help`. That proved the CLI wheel and
    its dependency closure, but not that every shipping wheel could be installed
    and imported by a downstream consumer from a clean environment.
- Action:
  - Changed the PyPI build smoke to install every shipping distribution from
    the built artifact directory into one clean venv.
  - Tightened the smoke to install the exact freshly built wheel file paths
    instead of resolving same-named distributions through `--find-links`, so a
    higher-version package from an index cannot satisfy the release proof.
  - Added an import smoke for every shipping import package before the existing
    `flowforge --help` console-script check.
  - Updated the publishing guide and release ratchets to document and preserve
    the all-shipping-wheel install/import smoke.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors`, `0 warnings`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_installs_and_imports_all_shipping_wheels tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `25 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, installed all 16 freshly
    built wheel files into a clean venv, imported all 16 shipping import
    packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI wheel metadata dependency audit

- Code review finding:
  - The internal dependency-bound ratchet checked source `pyproject.toml`
    manifests, but the PyPI artifact gate did not inspect built wheel
    `METADATA`. A packaging-backend or metadata-generation drift could have
    produced an uploaded wheel with an unbounded internal `Requires-Dist`
    dependency even while source manifests looked correct.
- Action:
  - Hardened `scripts/audit_2026/pypi_build_smoke.py` to read each built
    wheel's `.dist-info/METADATA` and reject internal Flowforge
    `Requires-Dist` entries that lack the `>=0.1.0,<0.2.0` compatibility
    bound.
  - Added a focused ratchet that builds a minimal wheel with an unbounded
    internal `Requires-Dist: flowforge_jtbd` entry and verifies the smoke
    helper rejects it.
  - Updated the publishing guide to document built-wheel dependency metadata
    validation.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `26 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, inspected built wheel
    `Requires-Dist` metadata for bounded internal dependencies, installed all
    16 freshly built wheel files into a clean venv, imported all 16 shipping
    import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## Current-head local release rerun after wheel metadata audit

- Trigger:
  - After committing built-wheel `Requires-Dist` metadata validation, reran the
    local release gate against the new branch head.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local`:
    `audit-2026-release-local: fail-closed local release gate passed`.
  - The run included ratchets, conformance, audit unit tests, property tests,
    integration/e2e, Python and JS cross-runtime parity, edge cases,
    observability, core/property/i18n coverage gates, 16-package
    closed-package coverage at 100% statement/branch, 16-package /
    32-artifact PyPI build and `twine check`, all-shipping-wheel clean-venv
    install/import smoke, `flowforge --help`, and signoff validation.
- Remaining risk:
  - The local gate still correctly records external release checks as required:
    visual DOM baselines, browser Playwright full-stack, reviewed polish-copy
    sidecar, optional downstream UMS parity, and live Postgres
    contention/drain verification.
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI sdist metadata dependency audit

- Code/design audit finding:
  - The artifact dependency-bound check inspected wheel `.dist-info/METADATA`
    but not uploaded sdist `PKG-INFO`. Because Flowforge uploads both wheels
    and sdists, dependency metadata generated into the sdist could have drifted
    from source manifests and published an unbounded internal `Requires-Dist`
    dependency for source-install consumers.
- Action:
  - Hardened `scripts/audit_2026/pypi_build_smoke.py` to parse both wheel
    `METADATA` and sdist `PKG-INFO` for each built artifact.
  - Renamed the dependency metadata gate to artifact scope and made failures
    report whether the unbounded internal dependency came from a wheel or sdist.
  - Extended the focused ratchet to build a minimal wheel and sdist with
    unbounded `Requires-Dist: flowforge_jtbd` metadata and verify the helper
    rejects the artifact pair.
  - Updated the publishing guide to document wheel and sdist dependency
    metadata validation.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_unbounded_internal_artifact_dependencies tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `26 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, inspected wheel `METADATA`
    and sdist `PKG-INFO` for bounded internal dependencies, installed all 16
    freshly built wheel files into a clean venv, imported all 16 shipping
    import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI internal dependency publication audit

- Code/design audit finding:
  - The artifact metadata gate proved internal Flowforge dependencies were
    version-bounded, but it did not separately prove that those internal
    dependencies point only at the 16 distributions actually being published.
    A future generated `Requires-Dist` on a workspace-only domain package could
    have been bounded yet still unusable for PyPI consumers because that
    package is intentionally not shipping.
- Baseline measurement:
  - Current source manifests have `0` shipping-package dependencies on
    workspace-only internal distributions.
- Action:
  - Hardened the artifact dependency metadata gate to reject internal
    dependencies that are not part of the shipping package set.
  - Kept the bound check separate from the shipping-distribution check so
    failures distinguish "unbounded" from "unpublished internal" metadata.
  - Added a focused ratchet that builds minimal wheel and sdist metadata with a
    bounded dependency on `flowforge_jtbd_insurance` and verifies the PyPI
    smoke rejects it when that distribution is not in the shipping set.
  - Updated the publishing guide to document that internal dependency metadata
    must be both bounded and limited to shipping distributions.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_unbounded_internal_artifact_dependencies tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_unpublished_internal_artifact_dependencies tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `3 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `27 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, inspected wheel `METADATA`
    and sdist `PKG-INFO` for bounded internal dependencies limited to shipping
    distributions, installed all 16 freshly built wheel files into a clean
    venv, imported all 16 shipping import packages, and completed
    `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI smoke temp-directory safety audit

- Code review finding:
  - `scripts/audit_2026/pypi_build_smoke.py` rejected custom output or venv
    paths outside the system temp root only after the path already existed. A
    non-existent custom `--dist-dir` or `--venv-dir` outside the temp root
    could still be created before later runs refused to manage it.
- Action:
  - Moved the temp-root containment check ahead of the existence check so all
    custom build and venv paths must resolve under `tempfile.gettempdir()`
    before the helper creates or removes anything.
  - Added a focused ratchet that monkeypatches the temp root, passes a
    non-existent path outside it, and verifies the helper raises before
    creating that path.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_non_temp_output_dirs_before_creation tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `28 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, installed all 16 freshly
    built wheel files into a clean venv, imported all 16 shipping import
    packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI sdist license root audit

- Code review finding:
  - The PyPI artifact license check accepted any sdist member path ending in
    `/LICENSE`. A nested package or fixture license file could have satisfied
    the release gate even if the required top-level `<sdist-root>/LICENSE`
    payload was missing from the uploaded sdist.
- Action:
  - Tightened `scripts/audit_2026/pypi_build_smoke.py` to require the exact
    top-level `LICENSE` path derived from the built sdist filename.
  - Added a focused ratchet with a nested-only sdist license file to prove the
    helper rejects it.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_requires_top_level_sdist_license tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_artifacts_missing_license_files -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `29 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified exact top-level
    sdist `LICENSE` payloads, installed all 16 freshly built wheel files into
    a clean venv, imported all 16 shipping import packages, and completed
    `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI wheel license dist-info audit

- Code review finding:
  - The wheel license check accepted any `.dist-info/licenses/LICENSE` entry,
    not necessarily the license file under the wheel's own `METADATA`
    dist-info directory. A stray or wrong dist-info license path could have
    satisfied the release gate while the actual wheel metadata directory lacked
    the declared license payload.
- Action:
  - Derived the expected wheel license path from the single
    `.dist-info/METADATA` file in each built wheel.
  - Added a focused ratchet where the wheel has
    `flowforge-0.1.0.dist-info/METADATA` but only
    `other-0.1.0.dist-info/licenses/LICENSE`, and verified the helper rejects
    it.
- Verification:
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_requires_license_in_wheel_metadata_dist_info tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_requires_top_level_sdist_license -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `30 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified wheel license paths
    under their own dist-info metadata directories, installed all 16 freshly
    built wheel files into a clean venv, imported all 16 shipping import
    packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI sdist PKG-INFO root audit

- Code review finding:
  - The sdist dependency metadata check accepted any member path ending in
    `/PKG-INFO`. A nested package metadata file could have satisfied or driven
    the dependency gate while the uploaded sdist's top-level
    `<sdist-root>/PKG-INFO` metadata was missing or ignored.
- Action:
  - Tightened `scripts/audit_2026/pypi_build_smoke.py` to read only the exact
    top-level `PKG-INFO` path derived from the built sdist filename.
  - Added a focused ratchet where the sdist contains only
    `src/flowforge_cli.egg-info/PKG-INFO`, proving the dependency gate rejects
    nested-only metadata.
  - Updated the publishing guide and release ratchet expectations to document
    top-level sdist `PKG-INFO` validation.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_requires_top_level_sdist_pkg_info_for_dependencies tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_unbounded_internal_artifact_dependencies tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `3 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `31 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, inspected wheel `METADATA`
    and top-level sdist `PKG-INFO`, installed all 16 freshly built wheel files
    into a clean venv, imported all 16 shipping import packages, and completed
    `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI wheel METADATA ownership audit

- Code review finding:
  - The wheel dependency metadata reader accepted any single
    `.dist-info/METADATA` entry in a wheel. A mismatched dist-info metadata
    directory could have driven the dependency and license checks without
    proving the metadata belonged to the wheel distribution named by the
    artifact.
- Action:
  - Added a shared wheel metadata resolver that requires exactly one
    `.dist-info/METADATA` file and verifies its dist-info distribution name
    matches the wheel filename distribution.
  - Reused that validated metadata path for the wheel license path derivation.
  - Added a focused ratchet where `flowforge_cli-0.1.0-py3-none-any.whl`
    contains only `other-0.1.0.dist-info/METADATA`, proving the dependency
    gate rejects mismatched wheel metadata ownership.
  - Updated the publishing guide and release ratchet expectations to document
    that the gate verifies the wheel's own `.dist-info/METADATA`.
- Verification:
  - `uv run ruff format --check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files already formatted`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_requires_wheel_metadata_for_wheel_distribution tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_requires_license_in_wheel_metadata_dist_info tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `3 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `32 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified wheel metadata
    ownership before dependency and license checks, inspected top-level sdist
    `PKG-INFO`, installed all 16 freshly built wheel files into a clean venv,
    imported all 16 shipping import packages, and completed
    `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI internal dependency exact-bound audit

- Code review finding:
  - The artifact dependency-bound check used substring matching for
    `>=0.1.0` and `<0.2.0`. A requirement such as
    `flowforge_jtbd>=0.1.0,<0.2.0.post1` could satisfy the release gate even
    though it did not carry the intended exact `<0.2.0` compatibility ceiling.
- Action:
  - Added a small internal requirement-specifier parser that removes markers,
    skips extras, normalizes whitespace, and checks the exact
    `>=0.1.0` and `<0.2.0` specifiers.
  - Replaced substring checks in both wheel `METADATA` and top-level sdist
    `PKG-INFO` validation.
  - Added a focused ratchet with imprecise `<0.2.0.post1` bounds in both
    artifact metadata files and verified the gate rejects them as unbounded.
  - Updated the publishing guide and release ratchet expectations to document
    the exact internal compatibility bound.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_imprecise_internal_artifact_bounds tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_unbounded_internal_artifact_dependencies tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `3 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `33 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified exact internal
    dependency bounds in wheel `METADATA` and top-level sdist `PKG-INFO`,
    installed all 16 freshly built wheel files into a clean venv, imported all
    16 shipping import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI internal dependency extra-specifier audit

- Code review finding:
  - After moving from substring checks to parsed specifiers, the internal
    dependency gate still accepted requirements that included the required
    `>=0.1.0` and `<0.2.0` bounds plus additional specifiers. A requirement
    like `flowforge_jtbd>=0.1.0,<0.2.0,!=0.1.3` could narrow the compatibility
    window while still satisfying the release gate.
- Action:
  - Tightened the internal dependency-bound check so the specifier set must be
    exactly `{>=0.1.0, <0.2.0}`.
  - Added a focused wheel and sdist metadata ratchet with an extra `!=0.1.3`
    internal dependency specifier and verified the gate rejects it.
  - Updated the publishing guide to document that extra internal dependency
    specifiers are not allowed in the artifact metadata contract.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_extra_internal_artifact_specifiers tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_imprecise_internal_artifact_bounds tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `3 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `34 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified exact-only internal
    dependency specifiers in wheel `METADATA` and top-level sdist `PKG-INFO`,
    installed all 16 freshly built wheel files into a clean venv, imported all
    16 shipping import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact metadata name audit

- Code review finding:
  - The PyPI smoke verified artifact filenames, wheel dist-info paths, and
    dependency metadata, but it did not separately verify the published
    metadata `Name` fields inside wheel `METADATA` and sdist `PKG-INFO`.
    Correct filenames with mismatched embedded package names could have passed
    the release gate until a downstream installer or index surfaced the drift.
- Action:
  - Added shared wheel and sdist metadata readers.
  - Added an artifact metadata-name gate that verifies wheel `METADATA` and
    top-level sdist `PKG-INFO` `Name` fields normalize to the shipping package
    distribution name.
  - Added a focused ratchet where both artifact filenames are for
    `flowforge-cli` but both embedded metadata `Name` fields are `other`.
  - Updated the publishing guide and release ratchet expectations to document
    artifact metadata-name validation.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_artifact_metadata_name_mismatches tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `35 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified artifact metadata
    names in wheel `METADATA` and top-level sdist `PKG-INFO`, installed all 16
    freshly built wheel files into a clean venv, imported all 16 shipping
    import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact metadata version audit

- Code review finding:
  - The artifact metadata identity gate verified `Name` fields but did not
    verify `Version` fields in wheel `METADATA` or sdist `PKG-INFO`. A built
    artifact filename could carry one version while embedded metadata reported
    another, weakening release evidence and downstream installer/index
    consistency.
- Action:
  - Added wheel and sdist filename-version helpers.
  - Extended the artifact metadata identity gate to compare wheel `METADATA`
    and top-level sdist `PKG-INFO` `Version` fields against their artifact
    filename versions.
  - Added a focused ratchet where both artifact filenames are `0.1.0` but
    embedded metadata reports `0.1.1`.
  - Updated the publishing guide and release ratchet expectations to document
    artifact metadata `Name` / `Version` validation.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_artifact_metadata_version_mismatches tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_artifact_metadata_name_mismatches tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `3 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `36 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts, verified artifact metadata
    names and versions in wheel `METADATA` and top-level sdist `PKG-INFO`,
    installed all 16 freshly built wheel files into a clean venv, imported all
    16 shipping import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## Polish-copy sidecar prompt-hash audit

- Code review finding:
  - The external release sidecar gate required `prompt_sha256` metadata to look
    like a lowercase SHA-256 digest, but it did not recompute the digest from
    the current bundle canonical strings and tone profile. A reviewed sidecar
    could therefore remain green after the bundle copy changed, weakening the
    evidence that the sidecar was generated from the current release prompt.
- Action:
  - Reused the `polish-copy` prompt hash routine and canonical-string builder
    in the sidecar gate.
  - Added an expected-prompt helper that compares the sidecar `prompt_sha256`
    against the current bundle/tone prompt.
  - Required the sidecar to include every current canonical field-label string
    key, while preserving the more specific dead-key diagnostics for invalid
    override keys.
  - Added a focused stale-hash ratchet and release-gate assertions so the
    prompt-hash and completeness checks cannot be removed silently.
- Verification:
  - `uv run ruff format scripts/audit_2026/check_polish_copy_sidecar.py tests/audit_2026/test_E_75_polish_copy_release_gate.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `3 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/check_polish_copy_sidecar.py tests/audit_2026/test_E_75_polish_copy_release_gate.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/check_polish_copy_sidecar.py tests/audit_2026/test_E_75_polish_copy_release_gate.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_75_polish_copy_release_gate.py::test_polish_copy_sidecar_gate_rejects_missing_current_bundle_strings tests/audit_2026/test_E_75_polish_copy_release_gate.py::test_polish_copy_sidecar_gate_rejects_stale_prompt_hash tests/audit_2026/test_E_75_polish_copy_release_gate.py::test_polish_copy_sidecar_gate_accepts_reviewable_sidecar tests/audit_2026/test_E_73_external_release_gate.py::test_external_release_preflight_reports_all_hard_prerequisites -q`:
    `4 passed`.
  - `uv run pytest tests/audit_2026/test_E_75_polish_copy_release_gate.py tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `46 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-polish-copy-sidecar`:
    passed against `examples/insurance_claim/jtbd-bundle.json.overrides.json`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## Aggregate local release gate evidence

- Action:
  - Re-ran the full fail-closed local release gate after the PyPI artifact
    metadata and polish-copy sidecar release-gate hardening slices.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local`:
    passed.
  - Covered ratchets, conformance, audit unit tests, property tests,
    integration/e2e, Python and JavaScript cross-runtime parity, edge cases,
    observability PromQL checks, core coverage, property/i18n coverage, the
    closed-package 100% statement/branch coverage ratchet for all 16 shipping
    packages, PyPI build/twine/install/import/CLI smoke for 16 packages and 32
    artifacts, and signoff verification.
  - The gate still prints the documented external-release checks that remain
    outside standalone local qualification: visual DOM baselines, browser
    Playwright full-stack, reviewed polish-copy sidecar, optional downstream
    UMS parity, and live Postgres contention/drain verification.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.
  - Completion still requires fresh external-release evidence in a
    browser/Postgres-capable release environment before final PyPI publication.

## PyPI publishable dist artifact staging audit

- Code review finding:
  - The publishing guide used `dist/*` for `twine check`, install smoke, and
    upload commands, but the canonical PyPI build smoke wrote to a temporary
    readiness directory by default and rejected non-temp output directories.
    That protected local files but left no guarded way to generate the exact
    validated `dist/` artifact set described by the publish instructions.
- Action:
  - Added an explicit `--allow-repo-dist` flag to the PyPI build smoke. The
    default remains temp-only, while `--dist-dir dist --allow-repo-dist` allows
    exactly the repository `dist/` directory and deletes/recreates it before
    building artifacts.
  - Kept the clean virtualenv smoke directory temp-only.
  - Added ratchets for the default non-temp rejection, the exact repo `dist/`
    publication path, and rejection of nested repo paths even with the explicit
    flag.
  - Updated the publishing guide to distinguish the default temp readiness
    output from the explicit uploadable `dist/` staging command.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_non_temp_output_dirs_before_creation tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_allows_exact_repo_dist_with_explicit_flag tests/audit_2026/test_E_73_external_release_gate.py::test_pypi_build_smoke_rejects_nested_repo_dist_with_explicit_flag -q`:
    `4 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `38 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build`:
    built and checked 16 packages / 32 artifacts in the temp readiness
    directory, installed all 16 freshly built wheel files into a clean venv,
    imported all 16 shipping import packages, and completed `flowforge --help`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run python scripts/audit_2026/pypi_build_smoke.py --dist-dir dist --allow-repo-dist`:
    built the same 16 packages / 32 artifacts into repository `dist/`, passed
    `twine check` on every artifact, installed all 16 wheels into a clean venv,
    imported all 16 shipping import packages, and completed `flowforge --help`.
  - `git diff --check`: clean.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## External release dist artifact qualification audit

- Code review finding:
  - The PyPI smoke script could now stage validated artifacts in repository
    `dist/`, but the fail-closed external release target still called the
    temp-output `audit-2026-pypi-build` target. Release qualification could
    therefore pass without proving that the exact `dist/*` files used by the
    publish commands were the freshly built, checked, and smoke-installed
    artifacts.
- Action:
  - Added `make audit-2026-pypi-build-dist`, which runs the PyPI build smoke
    with `--dist-dir dist --allow-repo-dist`.
  - Switched `audit-2026-release-external` to the publication-staging target
    while keeping `audit-2026-release-local` on the non-destructive temp
    readiness target.
  - Added the generated `dist/*` artifacts to the external release evidence
    upload and evidence summary.
  - Updated the publishing guide and release-gate ratchets so release
    qualification validates the same uploadable `dist/*` files used by the
    `twine upload` commands.
- Verification:
  - `uv run ruff format tests/audit_2026/test_E_73_external_release_gate.py`:
    `1 file reformatted`.
  - `uv run ruff check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_external_release_gate_is_wired_as_manual_release_workflow tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `2 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `38 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build-dist`:
    built 16 packages / 32 artifacts into repository `dist/`, passed
    `twine check` on every artifact, installed all 16 wheels into a clean venv,
    imported all 16 shipping import packages, and completed `flowforge --help`.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI publishing target terminology audit

- Code review finding:
  - After adding the publication-staging target, the publishing guide still
    described the temp-output `audit-2026-pypi-build` target as the canonical
    release gate. That wording could lead operators to run only the
    non-destructive readiness smoke before uploading `dist/*`.
- Action:
  - Clarified that `audit-2026-pypi-build` is the canonical non-destructive
    artifact readiness gate, while `audit-2026-pypi-build-dist` is the
    canonical publication-staging gate for releases.
  - Added release-doc ratchets for those two terms so future edits keep the
    temp and uploadable `dist/*` paths distinct.
- Verification:
  - `uv run ruff format tests/audit_2026/test_E_73_external_release_gate.py`:
    `1 file left unchanged`.
  - `uv run ruff check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_publishing_docs_require_cli_wheel_smoke -q`:
    `1 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `38 passed`.
  - `git diff --check`: clean.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## External release evidence artifact manifest audit

- Code review finding:
  - The external release workflow now uploads the publication-ready `dist/*`
    artifacts, but the external release runbook and evidence template still
    described the artifact bundle as DOM/playwright/sidecar/evidence only.
    Release reviewers could therefore miss whether the uploadable PyPI
    artifacts were retained in the qualification evidence.
- Action:
  - Updated the runbook acceptance criteria to require uploadable PyPI `dist/*`
    artifacts in the `audit-2026-release-external-evidence` artifact.
  - Added explicit evidence-template fields for retained `dist/*` artifacts and
    the `make audit-2026-pypi-build-dist` publication-artifact result.
  - Added ratchets so the runbook and template keep tracking retained PyPI
    artifacts.
- Verification:
  - `uv run ruff format tests/audit_2026/test_E_73_external_release_gate.py`:
    `1 file left unchanged`.
  - `uv run ruff check tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py::test_external_release_evidence_template_tracks_required_proofs -q`:
    `1 passed`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `38 passed`.
  - `git diff --check`: clean.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact checksum manifest audit

- Code review finding:
  - External release evidence retained the uploadable `dist/*` package files,
    but there was no compact checksum manifest recording each artifact's
    filename, size, and SHA-256 digest. Reviewers could confirm files were
    present but lacked a machine-readable byte-level record to compare against
    the artifacts uploaded to TestPyPI/PyPI.
- Action:
  - Added optional checksum-manifest output to the PyPI build smoke. The
    manifest records schema version, artifact count, artifact kind, relative
    path, byte size, and SHA-256 digest for every wheel and sdist after the
    build, `twine check`, clean-venv install, import, and CLI smoke pass.
  - Guarded non-temp manifest writes so the release path may write only
    `docs/audit-2026/external-release-pypi-artifacts-current.json`.
  - Wired `make audit-2026-pypi-build-dist` to emit that manifest and updated
    the external release workflow, runbook, evidence template, publishing guide,
    and ratchets to retain and review it.
- Verification:
  - `uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `1 file reformatted, 1 file left unchanged`.
  - `uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - `uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `40 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build-dist`:
    built 16 packages / 32 artifacts into repository `dist/`, passed
    `twine check` on every artifact, installed all 16 wheels into a clean venv,
    imported all 16 shipping import packages, completed `flowforge --help`, and
    wrote `docs/audit-2026/external-release-pypi-artifacts-current.json`.
  - Manifest inspection:
    `artifact_count == 32`, `len(artifacts) == 32`, and every artifact entry has
    a 64-character SHA-256 digest.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI built metadata fidelity audit

- Code review finding:
  - The release gate verified that shipping-package `pyproject.toml` files
    declared PyPI publication metadata and that built wheel/sdist metadata
    preserved artifact `Name` / `Version`, but it did not prove the built
    artifacts retained the other publication-facing metadata that PyPI users
    see. A packaging backend or project configuration drift could have dropped
    summary, Python requirement, license expression, author/maintainer email,
    classifiers, keywords, project URLs, or README content type while source
    ratchets still passed.
- Action:
  - Added a built-artifact publication-metadata gate to the PyPI smoke. For
    every shipping package, it now compares wheel `METADATA` and top-level
    sdist `PKG-INFO` against the package `pyproject.toml` for Summary,
    Requires-Python, license metadata, declared License-File entries,
    author/maintainer email addresses, keywords, classifiers, required project
    URLs, text/markdown README content type, and a non-empty README body.
  - Added regression tests proving the gate rejects mismatched wheel summary
    metadata and drifted sdist project URLs.
  - Updated the publishing guide and docs ratchets so release operators know
    that the PyPI build gate verifies source-to-artifact metadata fidelity, not
    only source declarations.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff format scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright scripts/audit_2026/pypi_build_smoke.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - Focused metadata/docs tests:
    `4 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `42 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build-dist`:
    built 16 packages / 32 artifacts into repository `dist/`, verified built
    wheel and sdist publication metadata against source `pyproject.toml`,
    passed `twine check` on every artifact, installed all 16 wheels into a
    clean venv, imported all 16 shipping import packages, completed
    `flowforge --help`, and wrote the checksum manifest.
  - `git diff --check`: clean.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact manifest verification audit

- Code review finding:
  - External release evidence retained uploadable `dist/*` artifacts and a
    checksum manifest, but there was no standalone verifier proving that a
    retained manifest still matched the current artifact directory before
    upload or release evidence review. A stale manifest could therefore remain
    attached to evidence after artifacts were regenerated or tampered with.
- Action:
  - Added `scripts/audit_2026/verify_pypi_artifact_manifest.py`, which parses
    the manifest, enforces schema version 1, rejects duplicate/stale/missing
    artifact entries, and independently recomputes artifact kind, path, byte
    size, and SHA-256 digest from `dist/*`.
  - Added `make audit-2026-pypi-artifact-manifest` and wired
    `audit-2026-release-external` to run it immediately after
    `audit-2026-pypi-build-dist`.
  - Updated the release workflow summary, publishing guide, external release
    runbook, evidence template, and ratchets so reviewers and operators must
    verify the manifest against retained artifacts before upload/signoff.
  - Added regression tests proving the verifier accepts matching artifacts,
    rejects digest drift, and rejects artifact-count drift.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff format scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files reformatted`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - Focused manifest/docs/workflow tests:
    `6 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `45 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-artifact-manifest`:
    verified `docs/audit-2026/external-release-pypi-artifacts-current.json`
    against repository `dist/`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build-dist audit-2026-pypi-artifact-manifest`:
    built 16 packages / 32 artifacts into repository `dist/`, passed
    `twine check` on every artifact, installed all 16 wheels into a clean venv,
    imported all 16 shipping packages, completed `flowforge --help`, wrote the
    checksum manifest, and verified that manifest against the retained
    artifacts.
  - `git diff --check`: clean.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact manifest completeness audit

- Code review finding:
  - The standalone PyPI artifact manifest verifier compared the manifest with
    whatever files were currently present in `dist/`, but did not independently
    enforce that the artifact set was complete for the shipping package set. An
    empty or partial `dist/` paired with a matching empty or partial manifest
    could therefore pass the verifier outside the build target that normally
    creates the artifacts.
- Action:
  - Tightened `verify_pypi_artifact_manifest.py` so the default verifier derives
    the expected release artifact count from `shipping_packages()` and requires
    two artifacts per shipping package before comparing manifest entries with
    `dist/*`.
  - Kept small unit-fixture manifests explicit by allowing an
    `expected_artifact_count` override in direct tests.
  - Added a regression proving an empty release manifest/dist pair is rejected
    against the shipping package set.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff format scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - Focused manifest verifier tests:
    `4 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `49 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-build-dist audit-2026-pypi-artifact-manifest`:
    built 16 packages / 32 artifacts into repository `dist/`, passed
    `twine check` on every artifact, installed all 16 wheels into a clean venv,
    imported all 16 shipping packages, completed `flowforge --help`, wrote the
    checksum manifest, and verified the manifest against `dist/*` with the
    shipping package count enforced.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.

## PyPI artifact manifest identity audit

- Code review finding:
  - After enforcing the expected artifact count, the standalone manifest
    verifier still did not prove the retained files represented the expected
    shipping distributions. A matching manifest and `dist/` directory with the
    right number of artifacts but the wrong package names could pass the
    verifier if it was run outside the build smoke that checks package
    identities.
- Action:
  - Added distribution identity checks to
    `verify_pypi_artifact_manifest.py`. The verifier now requires exactly one
    wheel and one sdist for every distribution returned by `shipping_packages()`
    and rejects unexpected distributions.
  - Added direct test coverage for matching fixture artifacts, digest drift,
    missing manifest entries, wrong distribution sets, and empty release sets.
- Verification:
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff format scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `2 files left unchanged`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run ruff check scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    clean.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pyright scripts/audit_2026/verify_pypi_artifact_manifest.py tests/audit_2026/test_E_73_external_release_gate.py`:
    `0 errors, 0 warnings, 0 informations`.
  - Focused manifest verifier tests:
    `5 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_E_73_external_release_gate.py -q`:
    `50 passed`.
  - `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-pypi-artifact-manifest`:
    verified the retained checksum manifest against repository `dist/` with
    package count and distribution identity checks enforced.
- Remaining risk:
  - Push remains blocked locally by missing GitHub HTTPS credentials.
