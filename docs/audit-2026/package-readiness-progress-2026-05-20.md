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
    from `python/flowforge-cli`: `771 passed`, `1 skipped`, overall package
    coverage 77%.

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
    from `python/flowforge-cli`: `773 passed`, `1 skipped`, overall package
    coverage 77%.

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
    from `python/flowforge-cli`: `776 passed`, `1 skipped`, overall package
    coverage 78%.
