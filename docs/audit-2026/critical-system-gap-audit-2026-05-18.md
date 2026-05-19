# Critical system gap audit - 2026-05-18

Scope: full repository review of `flowforge` as a portable workflow framework and generated application scaffold. This audit focuses on capability gaps, incomplete code, UI/UX debt, workflow improvements, code quality, reliability, security, performance, and design risks.

Verdict: not ready to describe as exhaustively tested or completely correct. The repository contains strong deterministic-generator work and useful conformance tests, but several current "green" claims rely on skips, host-side assumptions, in-memory defaults, and starter stubs. Multi-platform production use needs a fail-closed release lane before this can be considered critical-system safe.

## Remediation Snapshot - 2026-05-18

This report is the original exhaustive audit plus remediation progress from the same work session. The verdict remains conditional because a reviewed real-key `polish-copy` sidecar and final external-release bundle still need to run in the release environment, but the DOM visual baseline and browser Playwright full-stack lanes now have browser-capable GitHub Actions evidence.

The prompt-to-artifact completion checklist for the current state lives at
`docs/audit-2026/completion-audit-2026-05-19.md`.

Fixed or materially hardened:

- FastAPI router mounting now fails closed without explicit principal and tenant wiring, and runtime routes resolve tenant from host context rather than trusting request bodies.
- Runtime snapshot and saga SQLAlchemy helpers now apply tenant predicates for cross-tenant collision cases; saga appends also verify tenant ownership before insert and surface index collisions as explicit conflicts.
- SQLAlchemy workflow child tables now use tenant-scoped foreign keys/unique constraints for instance-owned rows; the snapshot store exposes `compare_and_put(instance, expected_seq=...)`, and FastAPI runtime persistence prefers CAS-capable stores when available, rejecting stale multi-process snapshot writes instead of silently losing updates.
- SQLAlchemy hosts now have `fire_and_commit(...)`, a transactional fire path that writes the workflow event, snapshot CAS update, instance row state, audit-chain rows, and durable outbox rows together; FastAPI prefers this path when a store exposes it.
- Audit-chain verification now tracks independent per-tenant chain heads and covers interleaved tenants.
- A fail-closed live Postgres release target now exists for multi-session snapshot contention, Postgres `FOR UPDATE SKIP LOCKED` outbox drain, and interleaved-tenant audit verification.
- A fail-closed external release bundle now exists: `make audit-2026-release-external` runs DOM visual baselines, browser Playwright full-stack, real-key polish-copy sidecar verification, UMS workflow-def parity, and live Postgres checks, while rejecting local skip escape hatches.
- Engine audit/outbox ordering now prevents audit failure after escaped immediate outbox dispatch.
- `scripts/check_all.sh` now discovers the real workspace, runs package tests across 46 Python packages and 7 JS packages, includes Python and JS dependency audits, and is noninteractive-safe for pnpm install.
- JS `fast-uri` advisory is remediated through a workspace override and refreshed lockfile.
- Visual DOM regression is fail-closed by default; `VISREG_ALLOW_SKIP=1` is now an explicit local-bootstrap escape hatch only.
- The visual-regression harness now routes pages by example identity rather than shared admin path alone.
- A DOM baseline-generation workflow now runs smoke cadence on pull requests and full cadence through manual dispatch, using Playwright Chromium in GitHub Actions and uploading reviewable candidate `.dom.html` baselines as an artifact; this is a helper for review, not release qualification.
- A browser full-stack Playwright lane now exists for the generated insurance-claim workflow: it starts a generated FastAPI-router HTTP bridge, starts the generated frontend harness in API mode, fills the generated claim-intake form in Chromium, and verifies `submit`/`approve` requests plus `Idempotency-Key`, `X-Tenant-Id`, and `review -> done` responses.
- A dedicated `Audit 2026 browser full-stack e2e` pull-request workflow now provisions Playwright Chromium and runs that generated browser flow in GitHub Actions; PR evidence includes passing run `26078965980`.
- fr-CA sidecar/i18n validation and W4b generator property coverage were added.
- JTBD hub publish/rating paths now require authenticated permissions, and rating user identity is bound to the principal.
- WebSocket subscriber queues are bounded.
- Core config now has app-scoped `RuntimeConfig` context wiring for engine fire audit/outbox ports, plus `validate_production_config(...)` to reject missing or in-memory/noop critical ports at startup.
- SES delivery now signs requests with SigV4; webhook and Slack transports validate HTTPS hosts and block private/local URLs; webhook signing no longer defaults to `dev-secret`.
- S3 presigned PUT is disabled unless hosts explicitly opt into the unvalidated path; presigned POST/regular `put` remain the safe paths.
- Outbox handlers can raise `PermanentDispatchError` to dead-letter unrecoverable rows without retry churn, and `DrainWorker.health()` now exposes status plus cumulative dispatch/retry/dead/no-handler/reconnect/run-error counters.
- Generated backend routers no longer create anonymous principals or default tenants; hosts must override `require_principal` and provide `X-Tenant-Id`.
- Generated backend event flow no longer always starts from a fresh workflow instance: frontend payloads, routers, services, and adapters now carry `instance_id`, the default generated adapter keeps a tenant-scoped in-memory latest snapshot for multi-event demo/test flows, and the workflow definition path was fixed to load from the generated root.
- Generated idempotency helpers no longer raise `NotImplementedError`: they provide an in-memory demo/test store plus `configure_idempotency_session_factory(...)` for durable SQLAlchemy-backed idempotency rows.
- Generated admin consoles and renderer forms now ship real CSS instead of class names with no stylesheet.
- Generated Step components no longer show raw workflow state/instance diagnostics by default; diagnostics are opt-in via `developerMode`, and PII reveal now requires a reason, uses an icon-only control with accessible labels/tooltips, and can call an optional `onPiiReveal` audit hook before data is unmasked.
- The closed analytics taxonomy now includes `pii_revealed` for every JTBD, with regenerated Python and TypeScript enum outputs.
- Focused SQLAlchemy/FastAPI CAS verification passed: SQLAlchemy package tests `20 passed, 1 skipped`, storage/full-stack integration checks `10 passed`, hardening/audit subset `40 passed, 1 skipped`, plus ruff and pyright clean on touched persistence/runtime files.
- Focused transactional UoW verification passed: core/FastAPI/storage focused subset `25 passed`, SQLAlchemy package `20 passed, 1 skipped`, audit-pg package `38 passed, 2 skipped`, FastAPI package `21 passed`, and integration gate `65 Python + 291 JS + 4 e2e = 360` with 0 failures.
- Focused outbox reconciliation verification passed: `fire_and_commit(...)` rows inserted by SQLAlchemy were drained by `flowforge_outbox_pg.DrainWorker` against the same database file, with the row ending in `dispatched`.

Latest verification evidence:

- `VISREG_ALLOW_SKIP=1 UV_CACHE_DIR=/private/tmp/flowforge-uv-cache bash scripts/check_all.sh`
  - Result: `U24 gate PASSED`, 46 Python packages, 7 JS packages, 2,664 counted tests/assertions, Python dependency audit clean, JS production dependency audit clean, byte-identical regen clean, elapsed 97 seconds on the latest rerun.
  - Integration evidence: Stage 3 now runs the audit e2e pytest flows; integration summary from the latest direct run reports 66 Python tests, 295 JS assertions, 4 e2e tests, 365 total, 0 failed, with the browser lane explicitly marked `EXTERNAL`.
  - Caveats: this intentionally set `VISREG_ALLOW_SKIP=1` because Chromium cannot launch in this sandbox. Current release evidence for DOM/browser execution comes from GitHub Actions runs where Playwright Chromium can launch.
- GitHub PR release-gate evidence:
  - `flowforge gate (U24)` run `26078965998` passed with committed DOM smoke baselines and Playwright Chromium installed in CI.
  - `Audit 2026 DOM baseline generation` run `26078965977` passed in a browser-capable runner.
  - `Audit 2026 browser full-stack e2e` run `26078965980` passed in a browser-capable runner.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-local`
  - Result: fail-closed local release gate passed. Covered ratchets, conformance, audit unit tests, property tests, integration/e2e, Python+JS cross-runtime parity, edge cases, observability PromQL lint, W4b property coverage, i18n coverage, and signoff mapping.
  - Caveats: the target explicitly prints the external release checks that are outside standalone local qualification: browser DOM baselines, browser Playwright full-stack, real-key polish-copy sidecar, UMS parity, and live Postgres contention/drain verification. UMS parity and live Postgres have since passed in this session with explicit environment wiring.
- `uv run pytest tests/audit_2026 -q --tb=short`
  - Result: `200 passed`, including config-scoping/production-validation coverage for MEDIUM-05, generated SQLAlchemy runtime coverage for CRITICAL-08, browser full-stack e2e wiring coverage for HIGH-10, fail-closed external release-gate ratchets, fail-closed external preflight ratchets, fail-closed polish-copy sidecar ratchets, external release evidence-template ratchets, manual external-release workflow wiring, DOM-baseline/sidecar helper workflow ratchets, workflow YAML parse coverage, CI `check_all.sh` parallelism, tracked uv cache inputs, Node 22 / pnpm 11.1.3 pinning, and SnapshotConflict retry-policy documentation coverage.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend make audit-2026-ums-parity`
  - Result: `156 passed` in `tests/test_workflow_def_parity.py` against the real UMS backend checkout.
- Generated backend smoke:
  - Result: insurance-claim generated adapter loaded the workflow from the generated root and advanced `instance_id="demo"` through `submit -> approve`, ending in `done` with two history entries.
- Generated idempotency smoke:
  - Result: insurance-claim generated helper returned `miss -> in_flight -> replay` through both its in-memory store and a SQLite SQLAlchemy session-factory wiring.
- Generated Step/analytics UI hardening:
  - Result: `uv run pytest python/flowforge-cli/tests/test_form_renderer_flag.py python/flowforge-cli/tests/test_analytics_taxonomy.py python/flowforge-cli/tests/test_jtbd_generators.py::test_generated_tsx_balances_braces_and_parses_with_tsc -q --tb=short` passed with `23 passed`.
  - Result: `uv run ruff check python/flowforge-cli/src/flowforge_cli/jtbd/generators/analytics_taxonomy.py python/flowforge-cli/tests/test_form_renderer_flag.py python/flowforge-cli/tests/test_analytics_taxonomy.py` passed.
- Copy-polish sidecar auditability:
  - Result: `uv sync --all-packages --all-extras` installed the optional LLM dependency set, and `uv run python -c "import anthropic; print('anthropic import ok')"` passed. The current local blocker is now the absent reviewed sidecar plus no usable funded Anthropic/Claude key, not a missing optional package.
  - Result: `uv run pytest python/flowforge-cli/tests/test_polish_copy.py -q --tb=short` passed with `30 passed`, including LLM sidecar `llm_provider` / `llm_model` / `prompt_sha256` metadata coverage via an injected deterministic polish function, no-key / missing-extra `--require-llm` failure coverage, provider-format failure coverage, unexpected provider/auth failure coverage without a traceback, no-op `--require-llm` failure coverage, and preservation of existing reviewed sidecars when a polish pass returns canonical copy.
  - Result: `uv run pyright python/flowforge-cli/src/flowforge_cli/commands/polish_copy.py python/flowforge-cli/src/flowforge_cli/jtbd/overrides.py python/flowforge-cli/tests/test_polish_copy.py --pythonversion 3.11` reported `0 errors, 0 warnings, 0 informations`.
  - Result: the full local gate's `uv run pytest python/flowforge-cli/tests -q --tb=short` lane passed with `599 passed, 1 skipped`; the same package test command outside the full gate now passes with `601 passed, 1 skipped`.
  - Result: `uv run pytest tests/audit_2026/test_E_75_polish_copy_release_gate.py -q --tb=short` passed with `7 passed`, covering release-bundle wiring, valid sidecar acceptance, empty strings, missing metadata, invalid prompt hash, and dead override keys; `uv run flowforge polish-copy --bundle examples/insurance_claim/jtbd-bundle.json --tone formal-professional --require-llm --commit` fails closed when no usable funded Anthropic/Claude key is available and writes no sidecar. A discovered local config key reached Anthropic but failed with an insufficient-credit billing error, still writing no sidecar. `uv run python scripts/audit_2026/check_polish_copy_sidecar.py` and `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-polish-copy-sidecar` fail closed because `examples/insurance_claim/jtbd-bundle.json.overrides.json` is absent.
- WebSocket hub drop-metrics hardening:
  - Result: `uv run pytest python/flowforge-fastapi/tests/test_ws.py tests/audit_2026/test_E_41_fastapi_ws_hardening.py -q --tb=short` passed with `24 passed`.
  - Result: `uv run pytest python/flowforge-fastapi/tests -q --tb=short` passed with `22 passed`.
  - Result: `uv run pyright python/flowforge-fastapi/src/flowforge_fastapi/ws.py python/flowforge-fastapi/tests/test_ws.py --pythonversion 3.11` reported `0 errors, 0 warnings, 0 informations`.
- Snapshot conflict host guidance:
  - Result: `uv run pytest tests/audit_2026/test_E_74_snapshot_conflict_retry_docs.py -q --tb=short` passed with `1 passed`.
- `UPDATE_BASELINES=1 bash scripts/visual_regression/run_dom_snapshots.sh smoke`
  - Result: the local Vite harness started and reported `http://127.0.0.1:5173/`; the three DOM metadata/catalog tests passed, but all 21 browser-backed DOM snapshot cases failed because Chromium headless cannot launch in this sandbox: `MachPortRendezvousServer ... Permission denied`. The unsandboxed baseline-generation rerun request was rejected by the approval layer.
- `bash scripts/visual_regression/run_dom_snapshots.sh smoke`
  - Result: fails by default when DOM baselines are missing; `find examples -path '*screenshots*' -name '*.dom.html' -print` currently returns no checked-in `.dom.html` baselines.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache bash scripts/run_integration.sh`
  - Result: `66 passed, 3 skipped` Python integration, `295` JS tests/assertions, `4` audit e2e tests, 365 total, 0 failed, with Browser e2e reported as `EXTERNAL`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache RUN_BROWSER_E2E=1 BROWSER_E2E_ALLOW_SKIP=1 bash scripts/run_integration.sh`
  - Result: Python/JS/audit e2e still passed, the generated backend bridge and frontend harness started, and the browser lane was skipped only after Chromium failed to launch with `MachPortRendezvousServer ... Permission denied` in local bootstrap mode.
- Generated browser-backend bridge smoke:
  - Result: direct `POST /claim-intake/events` through `tests/integration/browser/generated_backend_server.py` returned `{"state":"review","matched":true}` and the request log recorded `Content-Type`, `Idempotency-Key`, `X-Tenant-Id`, the expected body, and 200 response.
- Browser e2e static/type verification:
  - Result: `pnpm --dir tests/visual_regression exec tsc --noEmit`, `pnpm --dir tests/visual_regression exec playwright test --project=browser-full-stack --list`, and `uv run pytest tests/audit_2026/test_E_72_browser_full_stack_e2e.py -q` passed.
- Browser e2e release execution:
  - Result: `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-browser-e2e` starts the generated backend and frontend harnesses, then fails when Chromium launches with `MachPortRendezvousServer ... Permission denied`; the unsandboxed rerun request was rejected by the approval layer.
- JS private package tarball-content verification:
  - Result: `pnpm --dir js/flowforge-integration-tests test private-ratchet.test.ts` passed with `7 tests`, including isolated-cache `npm pack --dry-run --json` checks that declared source-first entrypoints and the renderer stylesheet export are present in packed package contents.
  - Result: `pnpm --dir js/flowforge-integration-tests typecheck` passed.
- Live Postgres release target:
  - Result: `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache FLOWFORGE_TEST_PG_URL=postgresql://127.0.0.1:5432/postgres make audit-2026-live-postgres` passed with `4 passed`, covering stale snapshot rejection, `FOR UPDATE SKIP LOCKED` outbox drain, interleaved-tenant audit-chain verification, and tenant/ordinal index-plan coverage against a real local Postgres service.
- External release-target dry run:
  - Result: `make audit-2026-release-external` now exists and fails closed if `VISREG_ALLOW_SKIP=1`, `BROWSER_E2E_ALLOW_SKIP=1`, missing DOM baselines, missing browser execution, missing real-key polish-copy sidecar metadata, missing `BACKEND_ROOT`, or missing `FLOWFORGE_TEST_PG_URL` would make release evidence incomplete.
  - Result: `VISREG_ALLOW_SKIP=1 make audit-2026-release-external` exits nonzero with `VISREG_ALLOW_SKIP=1 is forbidden for release qualification`; `BROWSER_E2E_ALLOW_SKIP=1 make audit-2026-release-external` exits nonzero with `BROWSER_E2E_ALLOW_SKIP=1 is forbidden for release qualification`.
- External release preflight:
  - Result: `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-release-external-preflight` fails closed and reports all currently missing persistent prerequisites together. With `BACKEND_ROOT=/Users/nyimbiodero/src/pjs/ums/backend` and `FLOWFORGE_TEST_PG_URL` supplied, the remaining preflight blocker is only the real-key sidecar; the sidecar message requires `uv run flowforge polish-copy --require-llm --commit` with a key and `flowforge-cli[llm]` installed. The success path explicitly states browser execution is verified by `make audit-2026-release-external`, so preflight alone cannot be mistaken for release qualification.
- External release CI wiring:
  - Result: `.github/workflows/audit-2026-release-external.yml` now provides a manual release-qualification workflow that checks out flowforge plus a caller-supplied UMS backend repo/ref, starts a disposable Postgres service, pins pnpm 11.1.3 to match the repo's `allowBuilds` semantics, installs the flowforge workspace with all extras, installs Playwright Chromium, wires `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY`, and runs `make audit-2026-release-external` without local skip flags.
- External release evidence retention:
  - Result: `docs/audit-2026/external-release-evidence-template.md` now records the fields required to retain DOM baseline review, release skip-flag absence, preflight caveat acknowledgement, `anthropic` import preflight, `uv run flowforge polish-copy --require-llm --commit` output review, real-key sidecar review, manual workflow run URL, artifact URL, UMS parity, browser e2e, and live Postgres evidence. The manual external workflow uploads an `audit-2026-release-external-evidence` artifact with DOM baselines, Playwright reports/results, the reviewed sidecar, and evidence docs when present.
- Real-key sidecar authoring helper:
  - Result: `.github/workflows/audit-2026-polish-copy-sidecar.yml` now runs `uv sync --all-packages --all-extras`, verifies `anthropic` import, executes `uv run flowforge polish-copy --require-llm --commit` with repository secrets, runs `make audit-2026-polish-copy-sidecar`, prints the sidecar diff, and uploads the candidate sidecar for review. This remains an authoring helper; the reviewed sidecar must still be committed before release qualification.

Remaining release blockers:

- A real-key `polish-copy` authoring pass still needs to run with a valid funded `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`, be reviewed, and commit its sidecar if accepted.
- The final `make audit-2026-release-external` / manual external-release workflow must run after the reviewed sidecar is committed so one retained release artifact ties together DOM, browser e2e, sidecar, UMS parity, and live Postgres evidence.
- The exact external execution sequence is documented in `docs/audit-2026/external-release-runbook.md`.

Release CI execution still required:

- UMS workflow-def parity has passed against `/Users/nyimbiodero/src/pjs/ums/backend`; the manual release workflow now checks out a caller-supplied backend repository/ref and sets `BACKEND_ROOT`, but it still needs to be run in the release environment.
- The generated backend now supports stable multi-event demo/test flows by `instance_id`; idempotency can be wired to SQLAlchemy; and generated adapters expose `configure_runtime_session_factory(...)` to run `SqlAlchemySnapshotStore.fire_and_commit(...)` for durable workflow instance rows, snapshots, workflow events, audit rows, and outbox rows.
- SQLAlchemy-backed hosts now have a transactional fire commit path for event log, snapshot CAS, audit rows, and durable outbox enqueue. The local integration lane proves those rows can be drained by `DrainWorker`, and `audit-2026-live-postgres` has now passed against a real local Postgres service. The manual release workflow now supplies an isolated disposable Postgres service; critical deployments still need to execute that workflow and retain the evidence.

## Audit Method

Inputs reviewed:

- `HANDOVER.md`
- `docs/v0.3.0-engineering/close-out.md`
- `docs/v0.3.0-engineering/signoff-checklist.md`
- `scripts/check_all.sh`, `scripts/run_integration.sh`, `Makefile`
- Core engine and config under `python/flowforge-core`
- FastAPI, SQLAlchemy, audit, outbox, S3 documents, signing, notification, OTel, JTBD hub, CLI/generator packages
- Generated examples under `examples/*/generated`
- JS workspace under `js`
- Visual-regression harness under `tests/visual_regression`

Commands run during this audit:

- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/flowforge-cli/tests -q --tb=short`
  - Result: `1 failed, 586 passed in 6.20s`.
  - Failure: `test_mmdc_parses_every_emitted_diagram`, caused by Chromium/Puppeteer failing to launch in the current sandbox (`MachPortRendezvousServer ... Permission denied`).
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache bash scripts/check_all.sh`
  - Result: failed in step 5 while testing `flowforge-cli`. The wrapper exited without surfacing the captured pytest failure detail because the failing pytest run occurs inside command substitution.
- `pnpm audit --prod --lockfile-dir js`
  - Result: one high severity vulnerability, `fast-uri <=3.1.1`, advisory `GHSA-v39h-62p7-jpjc`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/conformance/test_arch_invariants.py -q --tb=short`
  - Result: `11 passed`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/flowforge-fastapi/tests -q --tb=short`
  - Result: `18 passed`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/flowforge-audit-pg/tests/test_sink.py::test_verify_chain_multiple_rows python/flowforge-audit-pg/tests/test_sink.py::test_redact_preserves_chain_validity -q`
  - Result: `2 passed`.
- Custom multi-tenant audit-chain probe using `PgAuditSink` with tenants `a` and `b`
  - Result: `Verdict(ok=False, first_bad_event_id=..., checked_count=2, unsupported=False)`.
- `bash scripts/visual_regression/run_dom_snapshots.sh smoke`
  - Initial result: exited 0 with `[SKIP] visual-regression-dom: DOM baselines are not checked in yet`.
  - Superseded by latest runner behavior: missing DOM baselines now fail closed unless `VISREG_ALLOW_SKIP=1` is explicitly set for local bootstrap.
- `pnpm -C tests/visual_regression typecheck`
  - Result: passed.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache make audit-2026-i18n-coverage`
  - Result: `0 error(s), 0 warning(s) across 3 example(s)`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest tests/audit_2026/test_property_coverage_gate.py tests/property/generators/test_i18n_properties.py tests/property/generators/test_operator_manual_properties.py -q`
  - Result: `3 passed`.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pip-audit --version`
  - Result: `pip-audit` not installed.
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv tool run pip-audit --version`
  - Initial result: blocked by sandbox writing to the user uv tool directory; escalation request was rejected by the execution environment.
  - Superseded by latest full local gate evidence: `scripts/check_all.sh` now runs `uv run --with pip-audit pip-audit --skip-editable` with a writable cache and reported the Python dependency audit clean.

## Release-Blocking Findings

### CRITICAL-01: FastAPI adapters fail open when auth is omitted

Status: remediated. `mount_routers(...)`, `build_runtime_router(...)`, `build_designer_router(...)`, and `build_ws_router(...)` now require an explicit principal extractor unless the caller opts into `allow_test_defaults=True`; runtime mounting also requires an explicit tenant resolver unless test defaults are enabled. The package tests cover production mounting failure on omitted auth/tenant wiring.

Files:

- `python/flowforge-fastapi/src/flowforge_fastapi/__init__.py:52`
- `python/flowforge-fastapi/src/flowforge_fastapi/__init__.py:67`
- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:143`
- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:154`
- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:151`
- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:181`

`mount_routers()` previously accepted `principal_extractor=None`, documented that the default returned a `"system"` principal for unit tests, and passed that default into runtime and WebSocket routers. A host that forgot to wire auth could get create/read/fire APIs and WebSocket subscription under a synthetic privileged identity. That unsafe path now raises `ConfigError` unless test defaults are explicit.

Impact:

- Remote unauthenticated access if a host mounts the adapter with defaults.
- Cross-tenant and state mutation bugs become remotely reachable.
- The default is convenient for tests but unsafe for critical systems.

Required fix:

- Keep production use fail-closed and preserve the tests that `mount_routers(app)` without explicit auth/tenant wiring raises outside explicit test mode.
- Continue auditing generated host scaffolds so they do not reintroduce anonymous principals.

### CRITICAL-02: Runtime routes trust client-supplied tenant and instance IDs

Status: remediated for the FastAPI and SQLAlchemy adapters. Runtime routes now resolve tenant from a host-supplied `TenantResolver` and use tenant-scoped store methods for create, read, and fire; body `tenant_id` is ignored for authority. The SQLAlchemy snapshot store reads and writes by `(tenant_id, instance_id)` and raises tenant mismatch/conflict errors instead of treating instance IDs as global authority tokens.

Files:

- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:86`
- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:101`
- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:217`
- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:240`
- `python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py:275`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:32`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:48`

`CreateInstanceRequest` and `FireEventRequest` still expose optional `tenant_id` for backward-compatible request shapes, but route authority now comes from the host resolver. `fire_event()` and `read_instance()` fetch snapshots with the resolved tenant. The SQLAlchemy snapshot store no longer depends on host-level RLS as the only tenant boundary.

Impact:

- If RLS is absent, misbound, disabled in tests, or bypassed by an admin path, instance IDs become cross-tenant access tokens.
- The route layer has no defense in depth.
- Tenant identity is controlled by the caller rather than resolved from authenticated principal/session context.

Required fix:

- Keep tenant resolution bound to trusted host context, not request bodies.
- Keep route and adapter tests proving cross-tenant read/fire is forbidden.
- Keep RLS as a second layer, not the only layer.

### CRITICAL-03: Audit-chain verification is broken for multiple tenants

Status: remediated for global verification, with live Postgres gate added. `verify_chain()` now tracks an independent previous hash per tenant and orders by tenant plus per-tenant ordinal, so interleaved tenant rows verify correctly. The package tests cover interleaved tenants and `since` verification. Concurrent writers are serialized per tenant through advisory locks on Postgres and, for the SQLite test path, an asyncio lock held through the `record()` transaction commit so a second writer cannot read a pre-commit chain head. `audit-2026-live-postgres` now includes interleaved-tenant audit verification and tenant/ordinal index-plan coverage against a caller-supplied Postgres database.

Files:

- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:207`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:221`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:244`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:250`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:284`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:288`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:341`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:359`

`record()` builds a separate hash chain per tenant by reading `_chain_head(conn, event.tenant_id)`. `verify_chain()` previously streamed all rows in global `(occurred_at, event_id)` order with one `prev_sha`; two tenants interleaved in time caused the second tenant row to be verified against the first tenant's prior hash. Verification now keeps `prev_by_tenant`, preserving independent tenant chain heads.

Original probe:

- Insert one event for tenant `a`, then one for tenant `b`.
- `verify_chain()` returns `ok=False` at the second row.

Impact:

- `Audit-chain monotonicity` conformance is green for the exercised shape, but the adapter fails a fundamental multi-tenant production shape.
- Operators cannot trust global `verify_chain()` output in multi-tenant deployments.
- This undercuts the repository's "multi-tenant by default" claim.

Required fix:

- Keep per-tenant verification semantics stable when adding new audit query modes.
- Run `make audit-2026-live-postgres` with `FLOWFORGE_TEST_PG_URL` before release qualification.

### CRITICAL-04: Engine outbox side effects can escape a rolled-back transition

Status: remediated for SQLAlchemy-backed critical hosts. `fire(..., dispatch_ports=False)` now returns audit/outbox effects without calling global ports; `SqlAlchemySnapshotStore.fire_and_commit(...)` writes workflow event, snapshot CAS update, current instance state, audit-chain rows via `PgAuditSink.record_in_connection(...)`, and pending outbox rows in one SQLAlchemy transaction. FastAPI `_fire_with_unit_of_work` prefers stores exposing `fire_and_commit`. The integration suite now proves `fire_and_commit(...)` outbox rows are schema-compatible with `flowforge_outbox_pg.DrainWorker` and can be marked `dispatched`. Direct `fire()` with global `config.outbox` still performs immediate port dispatch and must be treated as non-atomic demo/custom-host behavior.

Files:

- `python/flowforge-core/src/flowforge/engine/fire.py:448`
- `python/flowforge-core/src/flowforge/engine/fire.py:454`
- `python/flowforge-core/src/flowforge/engine/fire.py:462`
- `python/flowforge-core/src/flowforge/engine/fire.py:466`
- `tests/audit_2026/test_E_32_engine_hotfix.py:107`

The direct engine path can dispatch outbox envelopes through `config.outbox`. If hosts wire that port to a network sender instead of a durable enqueue adapter, external effects can escape local rollback. The SQLAlchemy critical path avoids this by disabling port dispatch during `fire()` and inserting pending outbox rows in the same database transaction.

Impact:

- Direct port dispatch remains unsafe for critical workflows unless every outbox target is idempotent, reversible, and reconciled.
- Hosts not using `SqlAlchemySnapshotStore.fire_and_commit(...)` still need their own transactional outbox boundary.

Required fix:

- Keep `audit-2026-live-postgres` in release qualification; it has passed locally against a real Postgres service and should run in CI against an isolated disposable database.

### CRITICAL-05: Per-instance fire serialization is in-process only

Status: materially remediated for SQLAlchemy-backed hosts. `SqlAlchemySnapshotStore.compare_and_put()` provides a durable optimistic-lock write keyed by `(tenant_id, instance_id, seq)`, and `fire_and_commit(...)` applies that CAS inside a transaction that also writes the workflow event, audit rows, and durable outbox rows. FastAPI runtime persistence prefers `fire_and_commit` when present, then falls back to CAS, then legacy `put`. The SQLAlchemy README now documents the required `SnapshotConflict` host policy: use idempotency keys, discard stale in-memory instances, re-read the latest snapshot, retry the whole fire operation with a small jittered budget, and surface `409 Conflict` after exhaustion.

Files:

- `python/flowforge-core/src/flowforge/engine/fire.py:47`
- `python/flowforge-core/src/flowforge/engine/fire.py:54`
- `python/flowforge-core/src/flowforge/engine/fire.py:360`
- `python/flowforge-core/src/flowforge/engine/fire.py:367`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:62`
- `python/flowforge-sqlalchemy/README.md:52`
- `tests/audit_2026/test_E_74_snapshot_conflict_retry_docs.py:1`

The direct engine concurrency gate remains a module-level Python `set`. It serializes coroutines in one interpreter, but it does not protect multiple processes, containers, machines, or task workers. SQLAlchemy-backed hosts now get durable optimistic locking through `compare_and_put`/`fire_and_commit`.

Impact:

- Two workers on different hosts can fire the same instance concurrently.
- Existing concurrency tests still mostly prove the single-process gate; SQLAlchemy CAS coverage is present, and the live Postgres target has now executed the multi-session stale-snapshot check against a real local Postgres service. The manual external release workflow now provides a disposable Postgres service for CI execution.

Required fix:

- Run `audit-2026-live-postgres` with a disposable Postgres URL in release CI.
- Keep the documented `SnapshotConflict` retry policy ratcheted.

### CRITICAL-06: `scripts/check_all.sh` does not cover the actual workspace and currently fails

Status: remediated for standalone flowforge execution and fail-closed release qualification. `scripts/check_workspace.py` now discovers 46 Python packages and 7 JS packages from the workspace manifests, and `scripts/check_all.sh` streams package test output through `tee` instead of hiding failure details in command substitution. The full local gate has passed in this session with `VISREG_ALLOW_SKIP=1`; standalone checkouts skip UMS parity with a reason instead of failing on a hardcoded adjacent backend path. Release qualification must use `make audit-2026-ums-parity` or the bundled `make audit-2026-release-external`, both of which fail if `BACKEND_ROOT` is absent.

Files:

- `scripts/check_all.sh:40`
- `scripts/check_all.sh:56`
- `scripts/check_workspace.py:15`
- `scripts/check_workspace.py:31`
- `pyproject.toml:54`
- `pyproject.toml:88`

The repo has 46 Python packages and 7 JS packages. `scripts/check_all.sh` and `scripts/check_workspace.py` previously covered 13 Python packages and 5 JS packages. Omitted from the old local full gate: `flowforge-otel`, `flowforge-jtbd`, `flowforge-jtbd-hub`, 30 domain JTBD packages, `flowforge-jtbd-editor`, and `flowforge-integration-tests`.

Original `check_all.sh` behavior:

- Step 3 prints `workspace OK: 13 python pkgs, 5 js pkgs`.
- Step 5 fails at `flowforge-cli`.
- The failure detail is suppressed because pytest output is captured in `result=$(...)` and `set -e` exits before printing the captured text.

Impact:

- The "full local gate" now covers the actual workspace package list.
- Package drift is less likely to land outside the main gate because package lists are manifest-derived.
- External layers are now explicitly classified: visual DOM baselines, browser full-stack e2e, UMS parity, and live Postgres checks are fail-closed release targets, while local standalone bootstraps may only skip them through documented local gates.

Required fix:

- Keep manifest-derived package discovery and streamed diagnostics.
- Keep `audit-2026-release-local` and `audit-2026-release-external` separate so standalone local checks do not overclaim browser/LLM/UMS/Postgres release evidence.

### CRITICAL-07: Visual regression gate exits green without baselines

Status: remediated for the smoke release lane. The DOM snapshot wrapper now fails closed by default when node modules, Playwright, Vite, dev-server harness startup, or checked-in DOM baselines are missing. A local workstation may opt into `VISREG_ALLOW_SKIP=1`, but release gates must not set it. Reviewed smoke DOM baselines are now committed under `examples/insurance_claim/screenshots/**`, and U24 run `26078965998` passed with those baselines in GitHub Actions. Full-cadence baselines remain a release-authoring expansion path through the DOM baseline helper workflow.

Files:

- `scripts/visual_regression/run_dom_snapshots.sh:35`
- `scripts/visual_regression/run_dom_snapshots.sh:62`
- `scripts/visual_regression/run_dom_snapshots.sh:64`
- `examples/building-permit/screenshots/frontend/.gitkeep`
- `examples/hiring-pipeline/screenshots/frontend/.gitkeep`
- `examples/insurance_claim/screenshots/frontend/.gitkeep`

The DOM visual regression wrapper previously exited 0 when no DOM baselines were checked in. The wrapper now treats missing baselines as a failure unless `VISREG_ALLOW_SKIP=1` is explicitly set, and the canonical insurance-claim smoke tree contains committed `.dom.html` baselines.

Current result:

- `flowforge gate (U24)` run `26078965998` passed the smoke DOM gate in CI.
- `Audit 2026 DOM baseline generation` run `26078965977` passed in CI and continues to upload candidate baselines for review.
- Local browser-backed DOM execution still cannot launch Chromium in this macOS sandbox, so local developers must not use `VISREG_ALLOW_SKIP=1` as release evidence.

Impact:

- The canonical smoke visual path now blocks PRs through U24 when DOM output drifts.
- Full-cadence visual coverage is still a separate nightly/manual expansion target.

Required fix:

- In CI, missing baselines must fail, not skip.
- Keep local developer skip only behind explicit `VISREG_ALLOW_SKIP=1`.

### CRITICAL-08: Generated backend event flow is not production-functional

Status: materially remediated for SQLAlchemy-backed generated hosts. The generated frontend/router/service/adapter path now carries `instance_id`, the default adapter keeps a tenant-scoped in-memory latest snapshot for local demos/tests, and hosts can call `configure_runtime_session_factory(...)` to switch `fire_event(...)` to the existing `SqlAlchemySnapshotStore.fire_and_commit(...)` path. That path persists the workflow instance row, latest snapshot, workflow event log, audit rows when a transactional audit sink is supplied, and durable outbox rows in the same persistence boundary. Generated idempotency helpers also work in memory for demo/test flow and expose SQLAlchemy session-factory wiring for durable idempotency rows. Remaining production work is operational: hosts must call the generated configuration hooks at boot, apply the generated/flowforge SQLAlchemy migrations, and run the new live Postgres contention/drain release target.

Files:

- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/workflow_adapter.py.j2:69`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/workflow_adapter.py.j2:164`
- `tests/audit_2026/test_E_71_generated_sqlalchemy_runtime.py:77`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/adapters/claim_intake_adapter.py:70`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/adapters/claim_intake_adapter.py:77`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/adapters/claim_intake_adapter.py:83`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/adapters/claim_intake_adapter.py:84`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/routers/claim_intake_router.py:99`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/claim_intake/idempotency.py:55`
- `examples/insurance_claim/generated/backend/src/insurance_claim_demo/claim_intake/idempotency.py:75`

Generated `fire_event()` previously had only an in-memory latest-snapshot map, so generated apps still needed a host rewrite for durable workflow runtime state. The router no longer creates an anonymous principal inline, and idempotency helpers no longer raise `NotImplementedError`; both idempotency and runtime snapshots now have SQLAlchemy session-factory wiring.

Impact:

- A sequence like submit -> approve can now operate on the same persisted instance when the host configures the generated SQLAlchemy runtime hook.
- Idempotency and runtime state are still in-memory by default so generated examples remain runnable without a database.
- Critical deployments must treat the generated app as requiring boot-time adapter wiring, migration application, and live database verification, not as a zero-config production service.

Required fix:

- Keep generated auth/principal and tenant dependencies fail-closed.
- Keep SQLAlchemy runtime/idempotency configuration hooks covered by generated-content tests.
- Run `make audit-2026-live-postgres` with `FLOWFORGE_TEST_PG_URL` before release qualification.

## Security Findings

### HIGH-01: JTBD hub package publish endpoint is unauthenticated

Status: remediated. `POST /api/jtbd-hub/packages` now requires `Permission.PACKAGE_PUBLISH`, and hub permission tests cover anonymous/insufficient-role rejection paths.

Files:

- `python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py:380`
- `python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py:385`

`POST /api/jtbd-hub/packages` previously did not require `_require_permission(Permission.PACKAGE_PUBLISH)`.

Impact:

- Namespace squatting, malicious package upload attempts, storage abuse.

Required fix:

- Keep publish permission mandatory.
- Preserve negative tests for anonymous and insufficient-role callers.

### HIGH-02: JS dependency audit has a high severity advisory

Status: remediated. The JS lock graph has been refreshed with a `fast-uri` override, and `scripts/check_all.sh` now runs `pnpm audit --prod` as part of the local gate.

Files:

- `js/pnpm-lock.yaml:1444`

`pnpm audit --prod --lockfile-dir js` previously reported `fast-uri <=3.1.1`, patched in `>=3.1.2`, through `flowforge-renderer > ajv` and `flowforge-renderer > ajv-formats > ajv`.

Required fix:

- Keep `pnpm audit --prod` in the release gate.
- Keep any advisory allowlist explicit.

### HIGH-03: Notification SES adapter has placeholder authentication

Status: remediated. The SES adapter now signs requests with AWS SigV4, including canonical payload hash, credential scope, signed headers, and optional session token. The notification transport tests cover the signed request shape.

Files:

- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:182`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:223`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:235`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:236`

The SES adapter previously sent a placeholder `X-Amz-Access-Key-Id` header instead of a SigV4 `Authorization` header.

Impact:

- This is not production SES authentication.
- Hosts may assume the adapter is production-ready because it is in a strategic package.

Required fix:

- Keep SigV4 request-shape tests.
- Add an AWS-compatible stub test if SES behavior expands.

### HIGH-04: Webhook and Slack adapters can post to arbitrary URLs

Status: remediated for default behavior. Webhook delivery now requires an explicit HMAC secret, checks HTTPS URLs against an allowlist or an explicit public-host opt-in, and rejects private/local/link-local hosts. Slack delivery defaults to Slack webhook hosts and applies the same URL safety checks.

Files:

- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:406`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:426`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:445`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:503`
- `python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py:511`

Webhook recipient URL and Slack webhook URL can come from metadata/recipient, but they are now validated before dispatch. Webhook no longer defaults to `dev-secret`.

Impact:

- SSRF risk if untrusted workflow metadata reaches notification dispatch.
- Default webhook secret is unsafe outside tests/dev.

Required fix:

- Keep explicit secret and URL allowlist requirements.
- Treat `allow_any_public_host=True` as an audited host-level decision, not a safe default.

### MEDIUM-01: Ratings endpoint trusts caller-provided user identity

Status: remediated. Ratings now bind `user_id` to the authenticated principal authorized for package install, rather than accepting caller-provided identity from the request body.

Files:

- `python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py:427`
- `python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py:437`
- `python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/registry.py:523`

The ratings API previously accepted `payload.user_id` and passed it to `registry.rate()`.

Impact:

- Reputation manipulation and impersonated ratings.

Required fix:

- Keep ratings bound to the authenticated principal.
- Preserve one-rating-per-authenticated-user behavior.

### MEDIUM-02: Python dependency CVE audit is not established

Status: remediated in the local gate. `scripts/check_all.sh` now runs `uv run --with pip-audit pip-audit --skip-editable` with cache directories under `/tmp`/`UV_CACHE_DIR`, and the latest full gate run reported the Python dependency audit clean.

Required fix:

- Keep the committed dependency-audit job in CI with a known install/cache path.
- Capture advisory allowlists with expiry dates if exceptions are ever needed.

## Reliability and Correctness Findings

### HIGH-05: SQLAlchemy saga queries do not filter by tenant and are race-prone

Status: remediated for tenant isolation and explicit conflict surfacing. Saga list/mark/pending queries now predicate on `(tenant_id, instance_id)`, appends verify the instance belongs to the helper tenant before inserting, the initial Alembic bundle declares `(tenant_id, instance_id, idx)` uniqueness, and append unique-key races raise `SagaConflict` instead of silently corrupting the ledger. Hosts that require wait-free concurrent saga writes should still add a retry policy around `SagaConflict`.

Files:

- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/saga_queries.py:49`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/saga_queries.py:52`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/saga_queries.py:71`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/saga_queries.py:83`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/saga_queries.py:101`

`SagaQueries` stores `_tenant_id` on append, but list/mark/pending queries filter only by `instance_id` and sometimes `idx`. `append()` computes `next_idx` by reading all existing idx rows without tenant filtering or durable locking.

Impact:

- Cross-tenant saga leakage if instance IDs collide.
- Concurrent append can compute duplicate indices unless a DB constraint catches it.

Required fix:

- Filter by `(tenant_id, instance_id)` everywhere.
- Add unique constraint `(tenant_id, instance_id, idx)`.
- Use transaction isolation or advisory locks for append.

### HIGH-06: Snapshot store overwrites cross-tenant rows and has no compare-and-swap

Status: remediated for the SQLAlchemy adapter. Reads/writes are tenant-scoped, wrong-tenant writes raise `SnapshotTenantMismatch`, and `compare_and_put()` raises `SnapshotConflict` on stale `seq`. The initial Alembic bundle now declares tenant-scoped instance foreign keys and unique constraints for snapshot, event, saga, token, and quarantine rows.

Files:

- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:48`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:62`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:67`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py:88`

`put()` looks up existing rows by instance ID only and overwrites them. `seq` is assigned from `len(instance.history)` but is not used for optimistic locking.

Impact:

- Cross-tenant overwrite if instance IDs collide.
- Lost update under concurrent fires.

Required fix:

- Use `(tenant_id, instance_id)` uniqueness.
- Add expected version/seq to `put()`.
- Raise conflict on stale writes and retry at route/service layer.

### HIGH-07: S3 document adapter advertises durable blobs but keeps metadata in memory

Status: materially remediated for hosts that can use local SQLite metadata. The canonical class name remains `S3DocumentPortInMemory` for the zero-config/default path, the legacy `S3DocumentPort` import emits a deprecation warning, and presigned PUT is disabled unless hosts explicitly opt into `allow_unvalidated_presigned_put=True`; presigned POST is available for policy-constrained uploads. The adapter now accepts a `DocumentIndexStore`, ships `InMemoryDocumentIndex` as the default, and ships `SQLiteDocumentIndex` for dependency-free durable metadata plus subject attachments.

Files:

- `python/flowforge-documents-s3/src/flowforge_documents_s3/port.py:1`
- `python/flowforge-documents-s3/src/flowforge_documents_s3/port.py:4`
- `python/flowforge-documents-s3/src/flowforge_documents_s3/port.py:270`
- `python/flowforge-documents-s3/src/flowforge_documents_s3/port.py:326`
- `python/flowforge-documents-s3/tests/test_port.py:161`

The adapter previously had only process-local dictionaries for metadata and the subject index. Metadata and subject lookups could disappear while S3 blobs remained durable. `SQLiteDocumentIndex` now persists `document_meta` and `document_subjects` with idempotent subject attachment ordering, and the package tests prove metadata, subject listing, classification lookup, and S3 reads survive adapter restart.

Impact:

- Production hosts have a built-in durable metadata/index option without adding a service dependency.
- Compliance queries by subject can survive process restarts when hosts configure `SQLiteDocumentIndex`.
- Presigned PUT path still bypasses adapter-side magic-byte validation and remains explicit opt-in.

Required fix:

- Keep `SQLiteDocumentIndex` covered by restart-persistence tests.
- Prefer presigned POST with content-type policy for production.
- Add object-store reconciliation/integrity checks for deployments that need to detect S3/index drift.

### HIGH-08: Outbox worker hides permanent failures in an infinite loop

Status: remediated for worker behavior and host observability hooks. Handlers
can raise `PermanentDispatchError` to move unrecoverable rows directly to
`dead` without retry churn, no-handler rows are dead-lettered with explicit
error text, and `DrainWorker.health()` exposes `ok`/`degraded` status, last
error, last run timestamp, reconnect count, run-error count, cumulative
dispatched/retried/dead/no-handler counters, and the most recent
`DrainResult`. Hosts now also get dependency-free `readiness_payload(...)` and
`prometheus_text(...)` helpers for readiness endpoints and Prometheus-style
collectors. Tests cover healthy dispatch counters, no-handler distinction,
permanent-dead distinction, degraded claim-error status, readiness HTTP mapping,
and metrics exposition.

Files:

- `python/flowforge-outbox-pg/src/flowforge_outbox_pg/worker.py:369`
- `python/flowforge-outbox-pg/src/flowforge_outbox_pg/worker.py:394`
- `python/flowforge-outbox-pg/src/flowforge_outbox_pg/worker.py:470`
- `python/flowforge-outbox-pg/src/flowforge_outbox_pg/health.py:1`
- `python/flowforge-outbox-pg/src/flowforge_outbox_pg/__init__.py:12`
- `python/flowforge-outbox-pg/tests/test_worker.py:1`

The worker catches broad loop exceptions, logs, sleeps, and continues. Missing handlers can move envelopes to dead letter immediately, and operators can now poll `health()` rather than scrape logs to distinguish transient retries, permanent failures, no-handler deployment lag, reconnects, and run-loop/claim errors.

Impact:

- Misconfiguration can now be detected from `health().status == "degraded"` or no-handler/dead counters.
- Operator visibility no longer depends only on log scraping.

Required fix:

- Mount `readiness_payload(...)` / `prometheus_text(...)` in each concrete host
  service and keep static deployment validation fail-fast before worker startup.

### MEDIUM-03: Audit redaction comments contradict test behavior

Status: remediated for documentation consistency. The sink docstring now matches the tests and current behavior: redaction is a post-write payload mutation, hash columns are left intact, and verification can detect the mutation for auditor cross-reference.

Files:

- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:301`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:304`
- `python/flowforge-audit-pg/tests/test_hash_chain.py:216`
- `python/flowforge-audit-pg/tests/test_sink.py:199`

The sink previously said redaction leaves hash columns intact so verification continues to pass. Tests say redaction may break/flag the row. The tests match current verifier behavior, and the code comment now says so.

Impact:

- Operator/auditor expectations are unclear.
- Redaction semantics are not production-defined.

Required fix:

- Add a separate append-only redaction audit event if operators need a stronger redaction proof than reason metadata on the mutated row.

### MEDIUM-04: WebSocket hub uses unbounded per-subscriber queues

Status: remediated for the in-process hub. `WorkflowEventsHub` now uses bounded queues with a positive `max_queue_size`, drops to slow subscribers with a warning when full, and exposes dependency-free metrics for current subscribers plus published, delivered, and dropped envelopes. The hub also renders Prometheus text for hosts that want to mount those counters directly.

Files:

- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:61`
- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:71`
- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:77`
- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:90`
- `python/flowforge-fastapi/tests/test_ws.py:185`

`subscribe()` previously created unbounded `asyncio.Queue()` instances. A slow WebSocket consumer could accumulate unlimited envelopes.

Impact:

- Memory pressure under slow or abandoned clients.

Required fix:

- Keep bounded queues, explicit slow-subscriber behavior, and dropped-envelope metrics covered by tests.

### MEDIUM-05: Global mutable core config is not app-scoped

Status: materially remediated for engine fire and generated-app runtime wiring.
`flowforge.config.RuntimeConfig` plus `use_runtime_config(...)` provide a
context-local app-scoped wiring hook, and `fire(...)` reads audit/outbox ports
from the active scoped config instead of directly using module globals.
Generated workflow adapters now record metrics through `config.current()`, and
`JtbdAuditLogger` dispatches through the scoped audit sink. Production
configuration validation fails closed on missing critical ports or default
testing fakes/noop RLS. Existing module-global assignment remains for
compatibility and explicit startup wiring.

Files:

- `python/flowforge-core/src/flowforge/config.py:1`
- `python/flowforge-core/src/flowforge/config.py:32`
- `python/flowforge-core/src/flowforge/config.py:57`
- `python/flowforge-core/src/flowforge/config.py:67`
- `python/flowforge-core/src/flowforge/engine/fire.py:465`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/workflow_adapter.py.j2:197`
- `python/flowforge-jtbd/src/flowforge_jtbd/audit.py:209`
- `python/flowforge-jtbd/tests/test_jtbd_audit.py:232`
- `tests/integration/python/tests/test_otel_spans_in_generated_app.py:190`
- `tests/audit_2026/test_E_70_config_scoping.py:1`

All ports are mutable module globals typed as `Any`. `reset_to_fakes()` installs permissive in-memory fakes and noop RLS.

Impact:

- Multiple apps in one process can cross-talk.
- Tests can hide production wiring omissions.
- Type checking cannot enforce port contracts through config.

Remaining fix:

- Continue migrating any future direct `flowforge.config.<port>` consumers that
  need multi-app isolation to `config.current()`.
- Keep global fakes reserved for explicit tests and simulators.

## Test and CI Gaps

### HIGH-09: Makefile audit targets skip/defer critical layers

Status: materially remediated for local and external release gating. `audit-2026-integration` now runs `scripts/run_integration.sh`, so the Makefile target covers Python integration, JS integration, and the non-browser audit e2e flows through one shared summary. `audit-2026-e2e` now fails when `tests/integration/e2e` is missing instead of green-skipping. `audit-2026-observability` now fails if PromQL rules are present and `promtool` is missing; in this environment `promtool` validated 15 committed rules. `audit-2026-cross-runtime` now runs both the Python fixture suite and the JS `expr-parity.test.ts` directly instead of hiding a missing JS script behind `|| echo`. `audit-2026-browser-e2e`, `audit-2026-ums-parity`, and `audit-2026-live-postgres` now exist as fail-closed external release targets. `audit-2026-release-local` is the fail-closed local release target and passed in this session; `audit-2026-release-external` is the fail-closed external release bundle and rejects local skip escape hatches.

Files:

- `Makefile:82`
- `Makefile:87`
- `Makefile:98`
- `Makefile:106`
- `Makefile:126`
- `Makefile:138`
- `Makefile:199`
- `Makefile:268`

Examples:

- `audit-2026-e2e` previously exited green when no e2e suites existed.
- JS cross-runtime parity previously used `|| echo`, so a missing script could look non-fatal.
- Observability rule lint previously skipped if `promtool` was absent even when committed PromQL rules existed.
- Visual-regression and property-coverage comments were updated to match current gate behavior.

Required fix:

- Keep `audit-2026-release-local` passing as the fail-closed local release check.
- Run `make audit-2026-release-external` in target environments before critical-system release.

### HIGH-10: Browser Playwright full-stack lane was missing from integration

Status: remediated for browser-capable PR evidence. Stage 3 now runs `tests/integration/e2e` and the summary splits Python, JS, and e2e counters correctly. Stage 4 now reports the browser lane as `EXTERNAL` by default and can run it with `RUN_BROWSER_E2E=1`. The dedicated `audit-2026-browser-e2e` target starts a generated FastAPI-router HTTP bridge, starts the generated frontend harness in API mode, and runs a real Playwright Chromium spec through the generated claim-intake submit/approve path. The `Audit 2026 browser full-stack e2e` workflow provisions Chromium and passed in GitHub Actions run `26078965980`; this sandbox still blocks local Chromium with `MachPortRendezvousServer ... Permission denied`.

Files:

- `scripts/run_integration.sh`
- `scripts/run_browser_full_stack.sh`
- `tests/integration/browser/generated_backend_server.py`
- `tests/visual_regression/tests/e2e_full_stack.spec.ts`
- `tests/visual_regression/playwright.config.ts`
- `tests/visual_regression/harness/vite.config.ts`
- `tests/audit_2026/test_E_72_browser_full_stack_e2e.py`

Stage 3 previously deferred unconditionally. It now runs the non-browser audit e2e suite (`fire -> audit -> verify`, `fire -> outbox -> ack`, `fork -> replay`) and reports separate Python, JS, and e2e counters. The browser lane is no longer a placeholder: the Playwright spec fills the generated claim-intake form, posts `submit` and `approve`, and verifies the generated router saw the tenant, idempotency keys, payloads, and `review -> done` responses. The generated backend bridge forwards HTTP into Starlette `TestClient`, so the generated FastAPI router, auth dependency override, idempotency helper, and generated service code run instead of a JS network mock.

Impact:

- Cross-package integration gate now states when browser coverage is external instead of silently implying it.
- `make audit-2026` includes the browser e2e target; `make audit-2026-release-local` continues to exclude it and prints it as a documented external release check.
- Pull requests now have a focused browser-capable workflow so the external browser lane can be proven before final release qualification.

Required fix:

- Keep the focused browser-capable workflow green, and run `make audit-2026-browser-e2e` again as part of the final external release bundle after the reviewed sidecar is committed.

### HIGH-11: Browser-dependent checks fail in the current execution environment

Status: materially remediated for local/package-test determinism and browser-capable PR evidence. Mermaid diagrams now have syntax/shape coverage independent of browser rendering, and the optional `mmdc` round-trip skips with an actionable reason when Chromium cannot launch unless `FLOWFORGE_REQUIRE_MMDC=1` is set in browser-capable CI. The visual DOM wrapper fails closed by default for missing baselines/prerequisites, with `VISREG_ALLOW_SKIP=1` limited to explicit local bootstrap, and the focused browser full-stack workflow has now passed in GitHub Actions.

Files:

- `python/flowforge-cli/tests/test_jtbd_diagram_generator.py:452`
- `python/flowforge-cli/tests/test_jtbd_diagram_generator.py:478`
- `scripts/visual_regression/run_dom_snapshots.sh:85`

`mmdc` may be installed on a workstation where Chromium/Puppeteer cannot launch. That no longer fails the package test nondeterministically unless the environment opts into requiring it. Visual baseline generation still cannot be completed here for the same class of browser-launch issue.

Required fix:

- Keep syntax-only mermaid validation separate from browser-backed rendering.
- Set `FLOWFORGE_REQUIRE_MMDC=1` only in CI environments where Chromium is expected to launch.
- Keep committed DOM baselines and browser workflow evidence current before claiming visual/browser coverage complete.

### MEDIUM-06: `check_all.sh` duplicates integration work

Status: remediated. `run_integration.sh` now emits a compact JSON summary with Python, JS, e2e, total passed, and total failed counters. `check_all.sh` consumes the integration summary instead of rerunning only the Python integration subset.

Files:

- `scripts/check_all.sh:237`
- `scripts/check_all.sh:240`

Step 11 runs `scripts/run_integration.sh`, then runs Python integration pytest again just to count tests.

Impact:

- Longer runtime.
- Possible inconsistent results if second run sees different state.

Required fix:

- Make `run_integration.sh` emit machine-readable JSON summary.

### MEDIUM-07: Many JS lint scripts are placeholders

Status: remediated without adding a new JS lint dependency. Placeholder package lint scripts now run the existing TypeScript static checks, and the integration ratchet rejects missing lint scripts plus placeholder forms like `echo`, `exit 0`, `true`, or `no lint`.

Files:

- `js/flowforge-designer/package.json:15`
- `js/flowforge-jtbd-editor/package.json:15`
- `js/flowforge-renderer/package.json:18`
- `js/flowforge-integration-tests/package.json:11`
- `js/flowforge-integration-tests/private-ratchet.test.ts:107`
- `js/flowforge-integration-tests/private-ratchet.test.ts:123`

Several package lint scripts were `echo ... && exit 0`.

Impact:

- JS packages now have at least a real static typecheck-backed lint gate.
- This is not a stylistic ESLint/Biome layer; adding one remains a separate dependency and convention decision.
- Code quality claims rely on typecheck only.

Required fix:

- Keep `pnpm -r lint` green and keep the ratchet preventing placeholder lint scripts.
- Add ESLint/Biome only as an explicit follow-up dependency decision.

## Capability and Feature Gaps

### HIGH-12: 30 domain JTBD packages are registered but package=false starters

Status: remediated for repository claims and ratcheted against drift. The 25
non-strategic domains are explicitly suffixed `-starter`, carry scaffold-only
metadata, and have README disclaimers. The five strategic content candidates
now have package-level README files disclosing that they are workspace-only,
not publishable, not SME-reviewed, and not part of the critical-system support
matrix until named SME signoff, release review, and `package = true` are
completed.

Files:

- `pyproject.toml:70`
- `pyproject.toml:88`
- `python/flowforge-jtbd-banking/pyproject.toml:23`
- `python/flowforge-jtbd-healthcare/pyproject.toml:23`
- `python/flowforge-jtbd-insurance/pyproject.toml:23`
- `python/flowforge-jtbd-hr/pyproject.toml:23`
- `python/flowforge-jtbd-banking/README.md:1`
- `python/flowforge-jtbd-gov/README.md:1`
- `python/flowforge-jtbd-healthcare/README.md:1`
- `python/flowforge-jtbd-hr/README.md:1`
- `python/flowforge-jtbd-insurance/README.md:1`
- `tests/audit_2026/test_E_48a_domain_rebrand.py:121`

There are 30 domain packages with `[tool.uv] package = false`. Some strategic-looking names (`banking`, `healthcare`, `gov`, `hr`, `insurance`) are not suffixed `-starter` but are still disabled.

Impact:

- Capability surface looks broader than ship-ready package surface.
- Domain quality is mostly smoke-tested, not SME-validated.

Required fix:

- Keep the README/package-doc status disclosures and rebrand ratchets in place.
- Do not move a strategic package to release marketing or critical-system
  support matrices until named SME signoff, publishable packaging, and release
  verification evidence exist.

### MEDIUM-08: JS packages are all private

Status: documented and ratcheted. The JS workspace now has a README declaring the packages private/source-first, and the integration ratchet enforces that every workspace package is `private: true`. Placeholder JS build scripts are also forbidden, and `@flowforge/step-adapters` now runs `tsc --noEmit` for build instead of echoing a no-op. The ratchet also runs `npm pack --dry-run --json` with an isolated temp npm cache and verifies each private package tarball would contain the declared source-first entrypoints. This is acceptable for the current repository contract; publishing any JS package remains a separate release-design task.

Files:

- `js/README.md:1`
- `js/flowforge-integration-tests/private-ratchet.test.ts:41`
- `js/flowforge-integration-tests/private-ratchet.test.ts:109`
- `js/flowforge-integration-tests/private-ratchet.test.ts:137`
- `js/flowforge-types/package.json:4`
- `js/flowforge-renderer/package.json:4`
- `js/flowforge-runtime-client/package.json:4`
- `js/flowforge-step-adapters/package.json:4`
- `js/flowforge-step-adapters/package.json:10`
- `js/flowforge-designer/package.json:4`
- `js/flowforge-jtbd-editor/package.json:4`

Every JS package is `"private": true`, and the ratchet prevents accidental removal of that protection. Every package build script now performs a real static/build check rather than an echo-only placeholder. The current private tarball dry-run smoke proves declared package entrypoints and stylesheet exports are not omitted from package contents.

Current decision:

- No JS package is a published artifact for this release qualification.
- The JS workspace is private/source-first only; external package-manager
  consumption is explicitly unsupported until a separate publishability design
  changes that contract.

Impact:

- Cross-platform JS consumption is workspace-only unless copied vendored.
- Broad platform claims must not imply npm/package-manager availability for
  these packages.

Future expansion gate:

- Add `dist` build outputs, release automation, and installed-consumer fixture tests before removing `private: true`.

### MEDIUM-09: `polish-copy` first run remains blocked without an LLM key

Status: materially remediated for fail-closed release authoring. The default
no-key path still intentionally produces no sidecar so CI and local dry-runs can
remain clean, but release authors can now pass `--require-llm` to fail instead
of silently taking the no-op path. The real LLM commit path records
`llm_provider`, `llm_model`, and `prompt_sha256` metadata in the sidecar, and
tests cover that metadata through an injected deterministic polish function.
Additional release-hardening tests now verify that malformed provider output
and unexpected provider/auth failures fail the command instead of falling back
to canonical strings or printing a traceback, that `--require-llm --commit`
fails when a configured provider produces no sidecar-worthy changes, and that a
canonical/no-op polish pass preserves an existing reviewed sidecar instead of
overwriting it. A real authoring pass with an actual Anthropic/Claude key
remains external.

Files:

- `python/flowforge-cli/src/flowforge_cli/commands/polish_copy.py:92`
- `python/flowforge-cli/src/flowforge_cli/commands/polish_copy.py:94`
- `python/flowforge-cli/src/flowforge_cli/commands/polish_copy.py:120`
- `python/flowforge-cli/src/flowforge_cli/commands/polish_copy.py:129`
- `python/flowforge-cli/src/flowforge_cli/jtbd/overrides.py:120`
- `python/flowforge-cli/tests/test_polish_copy.py:430`
- `docs/v0.3.0-engineering/close-out.md:239`

The current first sidecar run produced no committed `<bundle>.overrides.json`
because no usable funded Anthropic/Claude key is available. In release-authoring mode,
`--require-llm` fails closed before writing anything when credentials/extras are
missing, invalid, or the provider returns unusable output, which makes the
credential/dependency or provider failure explicit without treating it as a
canonical no-op. The first real authoring pass is still not completed. When
that pass is run, committed sidecars now carry model and full-prompt checksum
metadata for review.

Required fix:

- Run with an actual key in a controlled environment, review diff, and commit sidecar.
- Keep sidecar model/checksum metadata covered by tests.

### MEDIUM-10: Override schema accepts more surfaces than generator applies

Status: remediated by making the sidecar schema fail closed. `JtbdCopyOverrides` now accepts only `<jtbd_id>.field.<field_id>.label`, the namespace that generators actually apply today. Helper text, button text, notification template, and error message namespaces are documented as future work and will not validate until they are wired into generated artifacts.

Files:

- `docs/v0.3.0-engineering/adr/ADR-002-copy-override-sidecar.md:13`
- `docs/v0.3.0-engineering/adr/ADR-002-copy-override-sidecar.md:49`
- `docs/v0.3.0-engineering/close-out.md:259`
- `python/flowforge-cli/src/flowforge_cli/jtbd/overrides.py:5`
- `python/flowforge-cli/src/flowforge_cli/jtbd/overrides.py:89`
- `python/flowforge-cli/src/flowforge_cli/jtbd/overrides.py:100`
- `python/flowforge-cli/tests/test_polish_copy.py:99`
- `python/flowforge-cli/tests/test_polish_copy.py:126`

Close-out previously documented that helper text, button text, notification template, and error message overrides were accepted by schema but not all applied by generators.

Impact:

- Authors can no longer commit a valid sidecar override for unapplied namespaces.
- The remaining future work is explicit: wire a namespace first, then admit it to the schema.

Required fix:

- Keep schema acceptance aligned with generated artifact application.

## UI and UX Findings

### HIGH-13: Generated admin console has class names but no actual stylesheet

Status: remediated for generated artifacts and ratcheted in generator tests.
The admin generator now emits `src/admin.css`, the admin entrypoint imports it
before design tokens, generated examples carry the stylesheet, and the generator
test asserts key operator UI selectors for layout, navigation, tables, status
pills, and responsive behavior.

Files:

- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/App.tsx:89`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/OutboxQueue.tsx:71`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/design_tokens.css:10`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/main.tsx:12`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/admin.css:42`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/src/admin.css.j2:42`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/src/main.tsx.j2:7`
- `python/flowforge-cli/tests/test_frontend_admin_generator.py:142`

Original gap: the admin app imported `design_tokens.css`, which defined
variables only, while components used `ff-admin-*` classes with no stylesheet
for layout, table density, status pills, panels, nav, error states, or
responsive behavior. The generated `admin.css` now covers those classes.

Impact:

- The admin console is no longer browser-default, but browser visual baselines
  and interaction checks still need to prove the rendered result across
  viewports before release.

Required fix:

- Keep `admin.css` generated, imported, and covered by the generator ratchet.
- Add browser visual-regression baselines after the browser-capable baseline
  environment is available.
- Add deeper keyboard/focus/table-overflow checks as part of the browser e2e
  lane.

### HIGH-14: Renderer package emits class names but ships no CSS

Status: remediated for private workspace use. `@flowforge/renderer` now ships
`src/styles.css`, exports it as `@flowforge/renderer/styles.css`, generated
real-form Step components import it, and JS/Python ratchets assert the export,
stylesheet selectors, and generated import. Publishing remains intentionally
blocked while JS packages are private/source-first.

Files:

- `js/flowforge-renderer/src/FormRenderer.tsx:293`
- `js/flowforge-renderer/src/FormRenderer.tsx:300`
- `js/flowforge-renderer/src/fields/common.tsx:34`
- `js/flowforge-renderer/package.json:8`
- `js/flowforge-renderer/package.json:13`
- `js/flowforge-renderer/src/styles.css:1`
- `js/flowforge-renderer/README.md:12`
- `js/flowforge-integration-tests/private-ratchet.test.ts:128`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:6`
- `python/flowforge-cli/tests/test_form_renderer_flag.py:109`

Original gap: `@flowforge/renderer` used classes like `ff-form`, `ff-field`,
and `ff-input`, but no CSS file existed under `js/flowforge-renderer/src`.
`src/styles.css` is now shipped and exported for private workspace consumers.

Impact:

- Generated "real form" paths now have baseline styling when hosts import
  `@flowforge/renderer/styles.css`.
- The private source-first tarball dry-run smoke now proves the renderer
  stylesheet export is included in packed package contents. Public package
  distribution still needs a dist build and installed-consumer fixture before
  these JS packages become publishable.

Required fix:

- Keep the renderer CSS export and generated real-form import covered by tests.
- Keep the private tarball dry-run smoke proving the CSS export is present in
  package contents.
- When JS packages become publishable, add a built `dist` tarball
  installed-consumer test.

### HIGH-15: Visual-regression harness routes shared admin URLs to the wrong example

Status: remediated for harness routing. The harness URL now encodes
`/__flowforge_visreg/{example}/{flavor}/{page}` and the route resolver rejects
legacy shared paths like `/audit` as ambiguous. DOM and SSIM tests navigate via
`harnessUrl(...)`, and meta tests assert harness URLs are unique and include
example identity.

Files:

- `tests/visual_regression/harness/src/main.tsx:18`
- `tests/visual_regression/harness/src/main.tsx:56`
- `tests/visual_regression/lib/page_catalog.ts:86`
- `tests/visual_regression/lib/page_catalog.ts:173`
- `tests/visual_regression/tests/dom_snapshot.spec.ts:53`
- `tests/visual_regression/tests/pixel_ssim.spec.ts:53`
- `tests/visual_regression/lib/page_catalog.ts:59`
- `tests/visual_regression/tests/dom_snapshot.spec.ts:139`
- `tests/visual_regression/tests/dom_snapshot.spec.ts:150`

The harness matches only `window.location.pathname`. Admin URLs like `/audit`, `/instances`, `/outbox`, `/rls`, `/saga`, and `/permissions` are reused across examples. In full cadence, building-permit and hiring-pipeline admin pages can mount the first matching example while writing baselines under their own example names.

Impact:

- Baselines can be generated or validated against the wrong component.
- Full-suite visual coverage is misleading.

Required fix:

- Keep visual tests using `harnessUrl(...)` rather than legacy shared page URLs.
- Browser DOM baselines still need to be generated and committed in a
  browser-capable environment before this lane can be considered release
  complete.

### MEDIUM-11: Generated Step UI exposes implementation state to users

Status: remediated for generated Step components. Real and skeleton generated Step paths now hide workflow diagnostics unless the host explicitly passes `developerMode={true}`. The tests assert the raw `<p>State:` / `<p>Instance:` user-facing lines are gone while the developer-only diagnostics remain accessible by label.

Files:

- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:48`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:258`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:414`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:48`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:260`

Original gap: the customer-facing component rendered raw `State:` and `Instance:` lines. This was useful for debugging, not for end users.

Required fix:

- Keep diagnostic metadata behind developer mode.
- Replace developer-only state values with richer user-facing progress/status labels when a production runtime client is generated.

### MEDIUM-12: Generated frontend page is still a demo stub

Status: remediated for generated frontend wiring and browser-capable PR evidence. Generated pages
now default to API-backed runtime calls through a generated
`runtimeClient.ts`, pass `Idempotency-Key` and `X-Tenant-Id`, and keep local
demo state transitions behind the explicit
`NEXT_PUBLIC_FLOWFORGE_DEMO_MODE=1` branch. Checked-in examples were
regenerated and no longer contain `instanceId = "demo"` or unconditional local
`setState("review")` / `setState("done")` stubs. A browser-backed
full-stack spec now proves the intended client/backend contract in Chromium;
GitHub Actions run `26078965980` passed.

Files:

- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/page.tsx.j2:10`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/page.tsx.j2:14`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/runtimeClient.ts.j2:1`
- `python/flowforge-cli/src/flowforge_cli/jtbd/generators/frontend.py:56`
- `examples/insurance_claim/generated/frontend/src/app/claim-intake/page.tsx:10`
- `examples/insurance_claim/generated/frontend/src/app/claim-intake/page.tsx:14`
- `examples/insurance_claim/generated/frontend/src/insurance_claim_demo/runtimeClient.ts:1`
- `python/flowforge-cli/tests/test_form_renderer_flag.py:142`

The generated page uses `instanceId = "demo"` and local state transitions instead of real runtime fetches.

Required fix:

- Keep `audit-2026-browser-e2e` in browser-capable release CI so the runtime-client
  path remains executed by Chromium, not just statically ratcheted.

### MEDIUM-13: PII reveal controls are text-only and not polished

Status: remediated for generated real-form Step components. PII values remain masked by default; reveal now requires a non-empty reason, disables while an optional audit hook is pending, refuses to reveal if that hook throws, emits the closed `pii_revealed` analytics event with non-sensitive metadata, and uses an icon-only button with `aria-label`/`title` rather than visible `Show` / `Hide` text.

Files:

- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:33`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:76`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:143`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:306`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:314`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend/Step.tsx.j2:349`
- `python/flowforge-cli/src/flowforge_cli/jtbd/generators/analytics_taxonomy.py:45`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:32`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:79`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:146`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:308`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:316`
- `examples/insurance_claim/generated/frontend/src/components/claim-intake/ClaimIntakeStep.tsx:351`

Original gap: PII controls used `Show` / `Hide` text buttons with no icon affordance, tooltip, audit logging for reveal, or per-field reveal reason.

Required fix:

- Keep the reason gate, optional `onPiiReveal` hook, and `pii_revealed` taxonomy event covered by generator tests.
- Add host-side persistence for `onPiiReveal` events in generated production runtime clients when MEDIUM-12 is addressed.

### MEDIUM-14: Generated UI contains visible explanatory text that belongs in docs/tooltips

Status: remediated for generated admin console hot spots. The long visible explanatory paragraphs in Audit Log, Outbox Queue, and Saga Compensations were removed from the templates and regenerated examples. Context now lives in compact `title` tooltips on headings/actions, keeping the repeated-use operator screens denser.

Files:

- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/src/pages/OutboxQueue.tsx.j2:54`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/src/pages/SagaPanel.tsx.j2:62`
- `python/flowforge-cli/src/flowforge_cli/jtbd/templates/frontend_admin/src/pages/AuditLogViewer.tsx.j2:58`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/OutboxQueue.tsx:54`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/SagaPanel.tsx:62`
- `examples/insurance_claim/generated/frontend-admin/insurance_claim_demo/src/pages/AuditLogViewer.tsx:58`

Admin pages previously included long instructional prose in the main UI. For a repeated-use operator console, this added clutter. The templates now render compact screen headings and action controls without visible explanatory paragraphs.

Required follow-up:

- Keep core screens dense, scannable, and action-oriented.

## Code Quality and Maintainability Findings

### MEDIUM-15: Tests and docs overclaim current status

Status: remediated for the stale close-out claim. This audit report carries the current source of truth, and the older v0.3.0 engineering close-out now has an explicit current-status addendum warning readers that it is historical evidence, not current critical-release qualification. The addendum records that `check_all.sh` local browser behavior needs an explicit visual bootstrap skip in this macOS sandbox, `make audit-2026-release-local` still excludes external release checks, DOM/browser execution now has GitHub Actions evidence, and i18n coverage is now 0 errors / 0 warnings after fr-CA fill. UMS parity and live Postgres are now separately verified with explicit environment wiring.

Files:

- `docs/v0.3.0-engineering/close-out.md:12`
- `docs/v0.3.0-engineering/close-out.md:16`
- `docs/v0.3.0-engineering/close-out.md:18`
- `docs/v0.3.0-engineering/close-out.md:22`
- `docs/v0.3.0-engineering/close-out.md:24`
- `docs/audit-2026/critical-system-gap-audit-2026-05-18.md:43`
- `docs/audit-2026/critical-system-gap-audit-2026-05-18.md:63`

The close-out says `check_all.sh` passed at closeout and describes blockers that have changed. Current reality is recorded in this audit addendum:

- `check_all.sh` passes locally with `VISREG_ALLOW_SKIP=1`, which is explicitly not a release setting.
- pnpm install blocker is no longer the visual-regression blocker; missing baselines and browser launch are.
- i18n warnings are now 0 after fr-CA fill, not the documented 20.

Required fix:

- Keep historical close-out reports clearly marked when later audit evidence supersedes them.
- Use generated status summary from current gates to avoid stale claims.

### MEDIUM-16: Sidecar i18n files with unknown locale names are silently ignored

Status: remediated. `load_i18n_sidecars(...)` now accepts `declared_languages` and raises on sidecar stems that are not declared in `project.languages`, so a typo like `fr_CA.json` fails instead of being silently ignored.

Files:

- `python/flowforge-cli/src/flowforge_cli/jtbd/i18n_sidecars.py:28`
- `python/flowforge-cli/src/flowforge_cli/jtbd/i18n_sidecars.py:39`
- `python/flowforge-cli/src/flowforge_cli/jtbd/generators/i18n.py:295`
- `python/flowforge-cli/src/flowforge_cli/jtbd/generators/i18n.py:298`
- `python/flowforge-cli/src/flowforge_cli/jtbd/generators/i18n.py:304`

The loader previously accepted every `i18n/*.json` and keyed by stem while the generator consumed only declared `project.languages`. A typo like `fr_CA.json` could succeed but be ignored.

Required fix:

- Keep sidecar stems validated against declared languages before generation.

### MEDIUM-17: JS and TS packages export TypeScript source directly

Status: documented and ratcheted as private-only. Package `main`/`exports` entries can continue pointing at `src/*.ts` while the packages are private workspace-only artifacts. The integration ratchet now explicitly fails any source-first TypeScript package that is not `private: true`, that adds `publishConfig` before a real dist build exists, or that carries an echo-only placeholder build script. It also dry-runs npm packing for every private source-first package and verifies declared entrypoints are included in the package contents.

Files:

- `js/README.md:1`
- `js/flowforge-integration-tests/private-ratchet.test.ts:48`
- `js/flowforge-integration-tests/private-ratchet.test.ts:109`
- `js/flowforge-integration-tests/private-ratchet.test.ts:137`
- `js/flowforge-renderer/package.json:6`
- `js/flowforge-renderer/package.json:8`
- `js/flowforge-designer/package.json:6`
- `js/flowforge-jtbd-editor/package.json:6`

Package `main` and exports point at `src/index.ts`. This is fine for workspace tooling but not for general consumers.

Verification:

- `pnpm --dir js/flowforge-step-adapters build` passed.
- `pnpm --dir js/flowforge-integration-tests test private-ratchet.test.ts` passed with 7 tests, including the isolated-cache npm pack dry-run tarball-content smoke.

Remaining fix:

- Before publishing any JS package, add build artifacts, export `dist`, and test installed packed packages in a consumer fixture.

### LOW-01: Stale comments in visual and Makefile gates

Status: remediated for the identified comments. Visual-regression comments now describe fail-closed baseline/prerequisite behavior plus explicit local `VISREG_ALLOW_SKIP=1`; property-coverage comments now refer to W0-W4b required generators rather than W0-W3-only coverage.

Files:

- `scripts/visual_regression/run_dom_snapshots.sh:12`
- `scripts/visual_regression/run_dom_snapshots.sh:52`
- `Makefile:199`
- `Makefile:268`

Several comments previously referred to pnpm install being blocked or W0-W3-only property coverage.

Required fix:

- Keep comments updated alongside gate behavior changes.

## Performance and Scalability Concerns

### MEDIUM-18: Audit verification orders by time globally

Status: materially remediated. Verification now orders by tenant, ordinal, time, and event id; fresh tables declare explicit read-path indexes on `(tenant_id, ordinal)` and `(tenant_id, occurred_at, event_id)`, and the ordinal backfill migration creates/verifies those indexes for existing Postgres deployments.

Files:

- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:265`
- `python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:267`

The original concern was that global time ordering across large tenants is not the best index pattern for per-tenant chains. Verification now uses tenant plus ordinal ordering, and the table has matching read-path indexes.

Required fix:

- Keep the live Postgres explain-plan coverage in `audit-2026-live-postgres` so index regressions fail release qualification.

### MEDIUM-19: `check_all.sh` scales poorly by serial pyright and package tests

Status: materially remediated for local and CI execution. `scripts/check_all.sh` now validates `FLOWFORGE_CHECK_JOBS` and runs independent per-package pyright and pytest checks in bounded batches, defaulting to four concurrent package jobs. The latest full local gate rerun passed with the default parallelism, reporting 46 Python packages, 7 JS packages, 2,665 counted tests/assertions, and 86 seconds elapsed. `flowforge-gate.yml` now pins `FLOWFORGE_CHECK_JOBS=4`, uses tracked `pyproject.toml` uv cache inputs, runs pyright through `uv run --with pyright`, and runs pnpm 11.1.3 on Node 22 while keeping uv and pnpm caches enabled. The ratchet verifies it does not set `VISREG_ALLOW_SKIP`; standard CI remains fail-closed on DOM prerequisites while local bootstrap runs must opt into the skip explicitly.

Files:

- `scripts/check_all.sh:40`
- `scripts/check_all.sh:112`

The script previously serialized pyright and pytest across every discovered Python package. Once all 46 Python packages were included, runtime grew sharply and the local gate became harder to run frequently. The current harness keeps output grouped by package while executing independent checks concurrently.

Required fix:

- Keep bounded package parallelism and grouped diagnostics.
- Split release gates by package class if CI runtime still exceeds budget.
- Cache uv/pyright outputs in CI.

## Recommended Release Criteria

Do not claim "critical-system ready" until all of these are true:

1. `scripts/check_all.sh` or a replacement release gate auto-discovers all packages and passes in CI.
2. Browser-backed tests have a known CI environment and do not fail/skip accidentally.
3. DOM visual baselines are committed and missing baselines fail in CI.
4. FastAPI adapters fail closed without explicit auth/principal extraction.
5. Runtime routes bind tenant to principal/session and snapshot store enforces tenant predicates.
6. Snapshot store has durable optimistic concurrency.
7. Audit-chain verification passes interleaved multi-tenant tests.
8. Outbox dispatch is transactional or explicitly non-atomic with reconciliation.
9. JTBD hub publish/rating endpoints require authenticated principals.
10. JS and Python dependency audits run in CI.
11. Generated backend has a production mode with persistent instances, auth, and idempotency implemented.
12. Admin and renderer UI ship real CSS and visual baselines.
13. Domain packages are clearly classified as starter vs SME-reviewed vs publishable.
14. A real-key `polish-copy` sidecar has been generated, reviewed, and committed.
15. The external release bundle has run with retained DOM, browser e2e, sidecar, UMS parity, and live Postgres evidence.

Current status: criteria 1-13 are materially satisfied for the repository and
browser-capable PR evidence described above. Criteria 14 and 15 remain blocked
until a valid Anthropic/Claude key is available, the reviewed sidecar is
committed, and the external release workflow is run.

## Suggested Remediation Plan

### Lane 1: Stop unsafe defaults

- Completed for FastAPI router mounting and runtime tenant authority.
- Engine and generated-app runtime paths use scoped runtime config where needed.
- Keep future config consumers on `config.current()` rather than reintroducing
  global mutable port reads.

### Lane 2: Fix durable correctness

- Completed for SQLAlchemy-backed hosts: tenant predicates, CAS, saga tenant
  filtering, multi-tenant audit verification, and transactional fire commits
  are implemented and covered by local plus live Postgres checks.
- Hosts that bypass `fire_and_commit(...)` must still provide their own
  transactional outbox boundary.

### Lane 3: Make the release gate honest

- Completed for workspace discovery, local/external gate separation, dependency
  audits, machine-readable integration summaries, and fail-closed release
  targets.
- The external release bundle remains intentionally blocked until the reviewed
  real-key sidecar is committed.

### Lane 4: Finish generated app production path

- Completed for generated SQLAlchemy runtime hooks, idempotency wiring, explicit
  auth/principal dependencies, and demo-mode separation.
- Critical deployments must still call the generated configuration hooks, apply
  migrations, and retain live database release evidence.

### Lane 5: UI readiness

- Completed for renderer/admin CSS, example-identity harness routing, smoke DOM
  baselines, PII reveal hardening, and removal of long inline operator text.
- Full-cadence visual coverage and deeper keyboard/focus/table-overflow checks
  remain future expansion, not current release blockers.

### Lane 6: Platform packaging

- Current repository contract is private/source-first JS packages and
  starter-classified domain packages, with ratchets preventing accidental
  publishable claims.
- Publishable JS dist outputs, installed-consumer fixtures, and SME promotion of
  domain packages remain separate release-design work.

## Current Strengths Worth Preserving

- Core DSL and generator determinism are treated seriously.
- `tests/conformance/test_arch_invariants.py` is valuable and should be expanded.
- The sidecar approach for non-deterministic LLM polish preserves canonical bundle determinism.
- The package separation between core and adapters is a good architectural boundary.
- The new i18n sidecar flow and property coverage additions are pointed in the right direction.
- The visual regression harness now has committed smoke baselines and
  browser-capable PR execution; the final external release bundle still needs
  to run after the real-key sidecar is committed.

## Bottom Line

Flowforge is materially harder than the original audit snapshot: auth and
tenant routing fail closed, SQLAlchemy-backed hosts have optimistic concurrency
plus transactional fire commits, multi-tenant audit verification is fixed,
dependency audits run, local gate coverage spans the real workspace, generated
Step diagnostics/PII reveal are hardened, generated pages default to API-backed
runtime-client calls, outbox worker health has readiness/Prometheus hooks, and
engine/generated-app paths now use scoped runtime config where it matters. DOM
smoke baselines and browser full-stack e2e now have browser-capable GitHub
Actions evidence. It is still not honest to call the system completely
critical-ready until the remaining external and production-mode gap is closed:
real-key `polish-copy` review, followed by the final external-release workflow
run with retained evidence. UMS parity and live Postgres have passed with
explicit environment wiring; the manual external-release workflow now encodes
those paths but still needs to run in the release environment after the sidecar
is committed. JS
packages remain intentionally private/source-first and must not be represented
as npm-publishable until a separate dist/consumer-fixture release design lands.
