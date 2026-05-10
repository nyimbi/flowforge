# flowforge changelog

## [0.3.0-engr.3] — Wave 3

> Fourth wave of the v0.3.0 engineering track per
> `docs/v0.3.0-engineering-plan.md` §7. W3 lands generation-time
> visibility artefacts (item 9 multi-frontend, item 10 bundle-diff,
> item 11 lineage), design-token theming (item 18), and the visual
> regression CI gate (item 21). It also retires the legacy
> `expr_parity_200.json` cross-runtime fixture per the engineering
> plan's §11.1 follow-up. Per ADR-001 the visual regression suite
> uses DOM-snapshot byte-equality as its CI-gating artifact and pixel
> SSIM as a nightly advisory; the runner is structurally complete but
> skips with a clear reason while `pnpm install` is blocked on the
> pre-existing pnpm-ignored-builds issue (the gate exits 0 and prints
> the skip reason; the JS-side cross-runtime parity sibling does the
> same — Python-side parity is exercised in full at 253/253). Six
> new generated-artifact classes join the byte-identical regen
> baseline (`frontend-cli/`, `frontend-slack/`, `frontend-email/`,
> `lineage.json`, design tokens trio `design_tokens.css` +
> `tailwind.config.ts` + `theme.ts`, screenshots/ baselines per
> example). One new ratchet (`no_design_token_hardcode`) joins the
> existing six. The cumulative regen-diff count is 6/6
> byte-identical (3 examples × 2 `form_renderer` flag values),
> verified by `scripts/ci/regen_flag_flip.sh` at closeout time.

- **[Capable]** (v0.3.0 W3 / item 9) Multi-frontend emission.
  Three new per-bundle generators ship alongside the existing
  Next.js frontend so a host can pick the surface that matches the
  operator's environment without forking the generator. New
  generators
  `flowforge_cli.jtbd.generators.frontend_cli` (Typer CLI client
  exposing every JTBD as a `flowforge-app <jtbd> submit` subcommand
  with shared OpenAPI / runtime-client wiring),
  `flowforge_cli.jtbd.generators.frontend_slack` (slash-command +
  interactive-message adapter that maps JTBD events to slash
  commands and transitions to button blocks), and
  `flowforge_cli.jtbd.generators.frontend_email` (reply-to-trigger
  email adapter useful for high-volume manual review queues).
  All three reuse the per-bundle `openapi.yaml` from W1's item 8 as
  their wire contract — a single bundle change re-themes every
  frontend deterministically. Per Principle 2 of the engineering
  plan each generator emits a per-bundle aggregation
  (`frontend-cli/<package>/`, `frontend-slack/<package>/`,
  `frontend-email/<package>/`), not per-JTBD slices, so two bundles
  in the same monorepo never collide. Each example regenerates the
  three new trees byte-identical against the checked-in baselines
  for both `form_renderer` flag values, lifting the per-example
  regen-diff target from 3 trees (next.js + admin + backend) to 6
  trees (+ cli + slack + email).
- **[Reliable]** (v0.3.0 W3 / item 10) Bundle-version diff with
  deploy-safety classes. New Typer subcommand
  `flowforge bundle-diff <old.json> <new.json> --html` (also
  `--json` and default plain-text) categorises every change between
  two parsed bundles into one of three deploy-safety classes:
  `additive` (new JTBDs, new optional fields, new info-severity
  audit topics — safe to ship without coordination),
  `requires-coordination` (new permissions, new required fields,
  renamed states — needs RBAC seed update + form invalidation +
  comms), and `breaking` (column type narrowed, enum value removed,
  transition with existing instances retargeted — needs migration
  plan + instance-class compatibility check). Categorisation is
  mechanical given two parsed bundles; the report is sorted with
  key `(kind_rank, path, category)` so the most-severe class shows
  first. JSON / HTML / plain-text renderers are byte-deterministic
  (parametrised determinism test runs each renderer twice and
  asserts byte-identical output). 38 unit tests cover every
  categorisation rule plus the `insurance_claim` W0→W1 integration
  shape; CI consumers can pipe the JSON output directly into
  migration-coordination workflows.
- **[Capable, Reliable]** (v0.3.0 W3 / item 11) Data lineage /
  provenance graph. New per-bundle generator
  `flowforge_cli.jtbd.generators.lineage` emits `lineage.json` at
  the bundle root tracing every `data_capture` field from form
  input → service → ORM column → audit-event payload → outbox
  envelope. For PII fields (`data_sensitivity: "pii"`) the entry
  carries the retention window, redaction strategy at each stage,
  and exposure surfaces (which roles can read, which audit events
  leak it, which notification channels carry it). The graph is the
  closure under transformation of the bundle-declared
  `data_sensitivity` and `pii` fields, computed at generation time
  rather than reverse-engineered by static-analysis tools. GDPR /
  HIPAA / CCPA reviewers can answer "where does this PII live?"
  structurally from a generated artefact instead of grepping
  hand-written code. JSON keys are sorted; field traversal sorts
  by `(jtbd_id, field_id)`; two regens against the same bundle
  yield byte-identical JSON, pinned by the regen-diff gate against
  `examples/<example>/generated/lineage.json` for all three
  examples.
- **[Beautiful]** (v0.3.0 W3 / item 18) Design-token-driven theming.
  Additive `bundle.project.design` block (Pydantic v2 with
  `extra='forbid'`) declares primary / accent colours, font family,
  density (`compact|comfortable`), and radius scale. New per-bundle
  generator `flowforge_cli.jtbd.generators.design_tokens` emits
  three parallel files into every frontend tree the bundle owns —
  `design_tokens.css` (CSS custom-property palette),
  `tailwind.config.ts` (Tailwind theme extension reading the same
  tokens), and `theme.ts` (TypeScript `Theme` module typed against
  the closed token surface). Step component, layouts, admin
  console, and screenshot baselines all read the same tokens; a
  single bundle change re-themes the whole generated app
  deterministically, including the W2 admin SPA's `main.tsx` (now
  imports the per-bundle `design_tokens.css`). Defaults match the
  pre-W3 visual identity so every existing example regenerates
  byte-identical. Per Principle 2 the generator is a per-bundle
  aggregation; per-JTBD slices stay per-JTBD.
- **(v0.3.0 W3)** New ratchet
  `scripts/ci/ratchets/no_design_token_hardcode.sh` — item 18
  generator-side enforcement against frontend templates regressing
  to hard-coded colours / fonts / radii in place of design-token
  references. Greps `frontend/Step.tsx.j2`,
  `frontend_admin/src/main.tsx.j2`, the new
  `design_tokens/*.j2` templates, and every checked-in
  `examples/*/generated/frontend*/` tree for naked hex colours
  (`#[0-9a-fA-F]{3,8}`), bare `rgb(`/`rgba(`/`hsl(` calls, and the
  legacy hard-coded font-family / radius literals; if any are
  present outside the design-tokens helper module, the ratchet
  fails loud and points the contributor at the design-tokens
  generator. Wired into `scripts/ci/ratchets/check.sh`'s
  `RATCHETS=()` array so `make audit-2026-ratchets` now reports
  7/7 ratchets pass (was 6). Legitimate exceptions go in
  `no_design_token_hardcode_baseline.txt` and require security/UX
  review per `scripts/ci/ratchets/README.md`.
- **(v0.3.0 W3)** Example bundle update: every example regenerates
  the new W3 surface byte-identical against the checked-in tree —
  per-bundle `lineage.json` (item 11), per-bundle `frontend-cli/`
  + `frontend-slack/` + `frontend-email/` trees (item 9), per-bundle
  design-tokens trio `design_tokens.css` + `tailwind.config.ts`
  + `theme.ts` (item 18) emitted into both the customer-facing
  `frontend/` tree and the operator `frontend-admin/` tree, and
  per-example `screenshots/` baselines (item 21, populated when
  the pnpm-install blocker clears). The cross-flag self-determinism
  check (`scripts/ci/regen_flag_flip.sh`) reports 6/6
  byte-identical (3 examples × 2 `form_renderer` values) at
  closeout time.

- **[Beautiful, Reliable]** (v0.3.0 W3 / item 21, ADR-001)
  Visual regression CI gate for generated frontends. New project-level
  Playwright runner under `tests/visual_regression/` mounts every
  generated page (real-path Step.tsx + admin SPA pages) at three
  viewports (mobile 375x667, tablet 768x1024, desktop 1440x900) and
  emits two artifacts per (example, flavor, page, viewport) tuple: a
  normalised DOM snapshot under
  `examples/<example>/screenshots/<flavor>/<page>.<viewport>.dom.html`
  and a pixel screenshot under
  `examples/<example>/screenshots/<flavor>/<page>.<viewport>.png`.
  The DOM snapshot is the **CI-gating** artifact (byte-equality
  required). The pixel screenshot is **advisory only** with an
  SSIM ≥ 0.98 threshold and runs nightly, never per-PR. ADR-001 at
  `docs/v0.3.0-engineering/adr/ADR-001-visual-regression-invariants.md`
  is the binding contract; DOM bytes are deterministic across
  Chromium minor versions because the four normalisation rules
  (strip `data-react-*`, collapse whitespace, sort `class` tokens
  alphabetically, sort attributes alphabetically) cancel every known
  drift source. New Make targets `audit-2026-visual-regression-dom`
  (CI-gating, smoke per-PR / full nightly) and
  `audit-2026-visual-regression-ssim` (advisory, nightly only).
  `scripts/check_all.sh` gains step 9 (DOM-snapshot gate) between the
  regen-diff (step 8) and UMS parity (step 10), renumbering the
  remaining steps. Per-PR cadence runs only the canonical
  `insurance_claim` example; the full suite runs nightly. The
  Playwright runner is structurally complete (config, helpers,
  specs, baseline catalog, ADR-001 normaliser with 5/5 rule unit
  tests passing) but **skips with a clear reason** until `pnpm
  install` is unblocked — both wrappers
  (`scripts/visual_regression/run_dom_snapshots.sh` and
  `run_ssim.sh`) detect missing prerequisites and exit 0 with a
  human-readable skip line. Once pnpm is unblocked, baseline files
  land in a follow-up PR with no further changes to the runner.
- **[Reliable]** (v0.3.0 W3) Cross-runtime fixture retirement.
  Legacy `tests/cross_runtime/fixtures/expr_parity_200.json` is
  deleted per the engineering plan §11.1: it has stayed
  byte-identical with `expr_parity_v2.json`'s 200-case base layer
  across the W1 + W2 windows, so the duplication is no longer
  earning its keep. The canonical fixture is now
  `expr_parity_v2.json` (250 cases: 200 base + 50
  `conditional`-tagged show_if cases). `generate_fixture.py` is
  rewritten to be the self-contained v2 builder (no v1 dependency);
  the bridging `_build_fixture_v2.py` is deleted. Test specs
  (`tests/cross_runtime/test_expr_parity.py`,
  `js/flowforge-integration-tests/expr-parity.test.ts`) and
  conformance invariant 5
  (`tests/conformance/test_arch_invariants.py`) are updated to
  reference the v2 fixture and the 250-case count. The
  `js/flowforge-renderer/src/expr.ts` header comment is updated to
  match. `make audit-2026-cross-runtime` reports 253 tests
  green against the v2 fixture (was 253 against the v2-but-dual-tracked
  pair); architecture invariant 5 stays green.

## [0.3.0-engr.2] — Wave 2

> Third wave of the v0.3.0 engineering track per
> `docs/v0.3.0-engineering-plan.md` §7. W2 lands the observability
> backbone (item 12 OTel + `MetricsPort`/`TracingPort` extension) plus
> reliability artefacts (item 6 router-level idempotency keys, item 7
> backup/restore drill), the closed analytics-event taxonomy (item 16
> + `AnalyticsPort`), and the tenant-scoped admin console (item 15).
> Three new runtime ports land in this wave per Principle 4 of the
> engineering plan: `TracingPort` (item 12), `AnalyticsPort` (item 16),
> and a `HistogramMetricsPort` extension on the existing `MetricsPort`
> (item 12). One new adapter package (`flowforge-otel`) and one new
> ratchet (`no_idempotency_bypass`) ship alongside. Invariant 11
> (idempotency-key uniqueness) lands as `@invariant_p1`. Six new
> generated-artifact classes join the byte-identical regen baseline:
> per-JTBD `idempotency.py` + `<table>_idempotency_keys` migration
> (item 6), per-bundle `analytics.py` + `analytics.ts` (item 16),
> per-bundle `frontend-admin/<package>/` SPA tree (item 15), and
> per-bundle `docs/ops/<package>/restore-runbook.md` (item 7). OTel
> spans wrap `fire`, effect dispatch, and audit append in the
> generated `domain_service`, `domain_router`, and `workflow_adapter`
> templates; default flag values keep every pre-W2 bundle regenerating
> identically against its locked baseline (3 examples x 2
> `form_renderer` values = 6 byte-identical regen targets in CI).

- **[Capable, Reliable]** (v0.3.0 W2 / item 12) OpenTelemetry by
  construction. New `flowforge.ports.tracing.TracingPort` Protocol
  defines `start_span(name, attributes)` returning an async context
  manager. `flowforge.ports.metrics.MetricsPort` is extended with
  `HistogramMetricsPort` so the standard meter set
  (`flowforge.fire.duration_seconds` and friends, bucketed at
  SLA-budget multiples) is type-stable across hosts. Both ports are
  port-only (no `opentelemetry` import in `flowforge-core`); the
  in-memory test fakes ship under `flowforge.testing.port_fakes` so
  generator tests can assert span sequences without an OTel SDK.
  New adapter package `flowforge-otel` (in the
  `python/flowforge-otel/` workspace member) wraps
  `opentelemetry.trace` and `opentelemetry.metrics` to satisfy both
  ports; `flowforge_otel.install()` is a one-call wiring helper.
  The `[otel]` extra carries the SDK so hosts that only need the
  type-stable adapter API don't pay for the SDK install. Generator
  templates (`domain_service.py.j2`, `domain_router.py.j2`,
  `workflow_adapter.py.j2`) now wrap `fire`, effect dispatch, and
  audit-append in spans whose attributes carry
  `{flowforge.tenant_id, flowforge.jtbd_id, flowforge.state,
  flowforge.event, flowforge.principal_user_id}`. The constants
  `STANDARD_SPAN_NAMES` + `STANDARD_SPAN_ATTRIBUTES` are exported
  from `flowforge.ports.tracing` so renaming a span is a
  SECURITY-NOTE-grade change. Without OTel installed the generated
  code falls back to a no-op span via the in-memory fake — no
  runtime hard-dep on the SDK. New PromQL alert rules at
  `tests/observability/promql/v0_3_0_w2_item_12_otel.yml` cover the
  meter set; new integration test
  `tests/integration/python/tests/test_otel_spans_in_generated_app.py`
  asserts the span sequence end-to-end against the in-memory fake.
- **[Reliable]** (v0.3.0 W2 / item 6, invariant 11) Router-level
  idempotency keys. Generated `POST /<jtbd>/events` routes now
  require an `Idempotency-Key` header; missing or malformed keys
  return `400 Bad Request`, in-flight duplicates return `409
  Conflict`, and successfully-completed requests are cached and
  re-served on duplicate keys. New per-JTBD generator
  `flowforge_cli.jtbd.generators.idempotency` emits
  `backend/src/<pkg>/<jtbd>/idempotency.py` with the SQLAlchemy
  helpers `check_idempotency_key` + `record_idempotency_response`;
  the `db_migration` generator emits a chained per-JTBD
  `<table>_idempotency_keys` table carrying a
  `UniqueConstraint("tenant_id", "idempotency_key", name="uq_<jtbd>_idempotency_keys_tenant_key")`
  so duplicate inserts trip at the DB layer. The dedupe TTL
  defaults to 24 hours; hosts override per-bundle via
  `bundle.project.idempotency.ttl_hours`. The router and service
  templates (`domain_router.py.j2`, `domain_service.py.j2`)
  thread the helpers; the new ratchet
  `scripts/ci/ratchets/no_idempotency_bypass.sh` greps the router
  template + every checked-in `examples/*/generated/`
  `<jtbd>_router.py` for the gate tokens (`Idempotency-Key`
  header parameter, `check_idempotency_key` import,
  `record_idempotency_response` call, `HTTP_400_BAD_REQUEST`,
  `HTTP_409_CONFLICT`) so a regen that drops the wiring fails CI
  before merge. Conformance invariant 11
  (`@invariant_p1 test_invariant_11_idempotency_key_uniqueness`)
  asserts (1) the chained migration carries the unique constraint,
  (2) two distinct fires sharing a `(tenant_id, idempotency_key)`
  pair raise an integrity error against an in-memory SQLite
  round-trip, and (3) the generated helper threads the
  bundle-configured TTL through to its `IDEMPOTENCY_TTL_HOURS`
  literal. `make audit-2026-conformance` now reports 11 invariants
  pass (was 10).
- **[Functional, Capable]** (v0.3.0 W2 / item 15) Tenant-scoped
  admin console. New per-bundle generator
  `flowforge_cli.jtbd.generators.frontend_admin` emits a standalone
  Vite + React 18 SPA at `frontend-admin/<project.package>/`
  surveying the bundle from the operator's perspective. Six panels
  ship: instance browser (filter by JTBD/state/tenant), audit-log
  viewer (calls `AuditSink.verify_chain()` and surfaces hash-chain
  integrity status per topic), saga compensation panel (pending
  compensations + manual trigger guarded by an
  `admin.<jtbd>.compensate` permission), permission-grant history
  (sourced from `AccessGrantPort`), deferred outbox queue (sourced
  from `OutboxRegistry`), and RLS elevation log (sourced from the
  audit chain's `rls.elevate` topic). The generator synthesises a
  closed `admin.<jtbd>.{read,compensate,outbox.retry,grant}`
  permissions catalog without requiring a bundle-schema change.
  The console assumes Postgres-backed adapters
  (`flowforge-audit-pg`, `flowforge-outbox-pg`, plus the bundle's
  own SQLAlchemy models); the generated README spells this out so
  non-PG hosts wire equivalent adapters before deploying. The SPA
  is deployed in isolation behind a separate ingress / auth proxy —
  decoupling the operator console from the customer-facing Next.js
  app is deliberate (different threat model, different UX brief,
  different deployment cadence). Two bundles can coexist in the
  same monorepo without collision because every emitted file lands
  under `frontend-admin/<project.package>/`.
- **[Functional, Capable]** (v0.3.0 W2 / item 16) Closed
  analytics-event taxonomy. New per-bundle generator
  `flowforge_cli.jtbd.generators.analytics_taxonomy` emits two
  parallel artifacts that lock the analytics surface to the same
  closed taxonomy on both sides of the wire:
  `backend/src/<pkg>/analytics.py` (Python `StrEnum`) and
  `frontend/src/<pkg>/analytics.ts` (TypeScript string-literal
  type). For every JTBD the bundle declares, six lifecycle
  suffixes — `field_focused`, `field_completed`,
  `validation_failed`, `submission_started`, `submission_succeeded`,
  `form_abandoned` — emit as `<jtbd_id>.<suffix>` events; closure
  is enforced at build time so dashboards can be statically
  validated against the closed enum. New `AnalyticsPort` Protocol
  at `flowforge.ports.analytics` exposes a non-blocking
  `track(event_name, properties)` so hosts wire Segment / Mixpanel
  / Amplitude / a noop sink themselves; the in-memory fake under
  `flowforge.testing.port_fakes.InMemoryAnalyticsPort` records
  every track call for tests and simulator runs. Per Principle 4
  the port carries no I/O dependency — analytics provider SDKs
  live in host code, never in `flowforge-core`. Per Principle 2
  the generator emits exactly two files regardless of how many
  JTBDs the bundle declares (cross-cutting bundle-level
  aggregation, not per-JTBD slices).
- **(v0.3.0 W2)** New runtime ports + adapter package: three
  port additions land in this wave per Principle 4 of the
  engineering plan. `flowforge.ports.tracing.TracingPort` (item
  12) defines the distributed-tracing surface;
  `flowforge.ports.analytics.AnalyticsPort` (item 16) defines the
  product-analytics emitter; `flowforge.ports.metrics.HistogramMetricsPort`
  (item 12) extends the existing `MetricsPort` with the standard
  meter set. All three are port-only Protocols with
  `runtime_checkable` so structural-typing assertions work without
  inheritance. In-memory fakes ship under
  `flowforge.testing.port_fakes` (`InMemoryTracingPort`,
  `InMemoryAnalyticsPort`, `InMemoryHistogramMetricsPort`) so
  generator tests can assert span sequences, track calls, and
  histogram samples without booting a real backend. The OTel
  adapter package `flowforge-otel` (Python workspace member with
  the `[otel]` extra) wraps `opentelemetry.trace` /
  `opentelemetry.metrics` and ships the convenience
  `flowforge_otel.install()` wiring helper that mounts both
  adapters onto `flowforge.config`. `flowforge.config` gains the
  `tracing` / `analytics` slots in the global registry alongside
  the existing 14 ports.
- **(v0.3.0 W2)** New ratchet
  `scripts/ci/ratchets/no_idempotency_bypass.sh` — invariant 11
  generator-side enforcement. Greps `domain_router.py.j2` and
  every checked-in `examples/*/generated/<pkg>/routers/<jtbd>_router.py`
  for the gate tokens (`@router.post("/events")` handler,
  `Idempotency-Key` header parameter, `check_idempotency_key`
  import, `record_idempotency_response` call,
  `HTTP_400_BAD_REQUEST`, `HTTP_409_CONFLICT`); absent any token
  the ratchet fails loud and points the contributor at item 6's
  helper module. Wired into `scripts/ci/ratchets/check.sh`'s
  `RATCHETS=()` array so `make audit-2026-ratchets` now reports
  6/6 ratchets pass (was 5). Legitimate exceptions go in
  `no_idempotency_bypass_baseline.txt` with the format
  `<repo-path>:<line>:<missing-token>` and require
  v0.3.0-engineering security/architecture review per
  `scripts/ci/ratchets/README.md`.
- **(v0.3.0 W2)** Example bundle baselines: every example
  regenerates the new W2 surface byte-identical against the
  checked-in tree — per-JTBD `idempotency.py` and
  `<rev>_create_<jtbd>_idempotency_keys.py` migration (item 6),
  per-bundle `analytics.py` + `analytics.ts` (item 16),
  per-bundle `frontend-admin/<pkg>/` SPA tree (item 15),
  per-bundle `docs/ops/<pkg>/restore-runbook.md` (item 7), OTel
  span imports in `domain_service`, `domain_router`, and
  `workflow_adapter` templates (item 12). The
  `examples/hiring-pipeline/generated/` tree is now committed so
  all 3 examples participate in step-8 regen-diff (was 2 in
  W0/W1). The cross-flag self-determinism check
  (`scripts/ci/regen_flag_flip.sh`, new) regenerates each
  example × `form_renderer = "skeleton" | "real"` twice and
  asserts byte-identical output — 6/6 byte-identical, exercised
  by the W2 closeout protocol per
  `docs/v0.3.0-engineering-plan.md` §7.

- **[Reliable]** (v0.3.0 W2 / item 7) Backup/restore drill artefact.
  New per-bundle generator
  `flowforge_cli.jtbd.generators.restore_runbook` emits
  `docs/ops/<bundle.project.package>/restore-runbook.md` listing every
  table the bundle creates in topological FK-dependency order
  (entity tables sorted by `jtbd.id`, then per-JTBD
  `<table>_idempotency_keys` tables when item 6 is wired), the
  required `pg_dump` flags (schema-only + data-only with `--no-owner`,
  `--disable-triggers`, explicit `--table=…` per bundle table), the
  audit-chain re-verification step (`flowforge audit verify --tenant
  <tenant>` for every tenant present in the dump), and the eight-step
  DR procedure (verify dumps → provision scratch → apply schema →
  alembic upgrade → load data → audit verify → smoke → decommission).
  Item 6's idempotency tables are gracefully tolerated — when
  `project.idempotency_ttl_hours` is absent the runbook still emits
  cleanly with entity tables only. Paired Makefile target
  `make restore-drill` (also exposed as
  `make audit-2026-restore-drill`) runs the procedure end-to-end
  against testcontainers Postgres via
  `tests/integration/python/tests/test_restore_drill.py`, asserting
  every audit chain re-verifies after dump → drop → restore. The
  integration test skips cleanly when Postgres / testcontainers /
  docker daemon are unavailable, and runs full end-to-end when CI
  provides them. Generation remains I/O-free; the new artefact joins
  the byte-identical regen baseline for all three examples.

## [0.3.0-engr.1] — Wave 1

> Second wave of the v0.3.0 engineering track per
> `docs/v0.3.0-engineering-plan.md` §7. W1 lands three items off
> `docs/improvements.md`: item 8 (bundle-derived OpenAPI 3.1
> emission), item 13 (real form generation behind the
> `bundle.project.frontend.form_renderer` flag), item 19
> (state-machine mermaid emission). Cross-runtime parity fixture v2
> (250 cases, 200 base + 50 `conditional`-tagged) lands in the same
> wave as item 13, anchored by the new
> `no_unparried_expr_in_step_template` ratchet (architectural
> mitigation for Pre-mortem Scenario 2). The legacy
> `expr_parity_200.json` is retained until W3 per the engineering
> plan §11.1. Three new artifacts (`openapi.yaml`,
> `workflows/<id>/diagram.mmd`, real-path `Step.tsx`) join the
> byte-identical regen baseline; default flag value `"skeleton"`
> keeps every pre-W1 bundle regenerating identically.

- **[Capable]** (v0.3.0 W1 / item 8) Bundle-derived OpenAPI 3.1
  generator. New per-bundle generator
  `flowforge_cli.jtbd.generators.openapi` emits `openapi.yaml` at
  the bundle root, one operation per JTBD's
  `POST /<url_segment>/events` route. Each operation is tagged by
  `jtbd_id` and carries two flowforge-specific extensions —
  `x-audit-topics` (sourced from `transforms.derive_audit_topics`)
  and `x-permissions` (sourced from `transforms.derive_permissions`)
  — so downstream tooling can route on them without booting the
  FastAPI app. Request bodies derive a JSON-schema payload from
  each JTBD's `data_capture` fields with deterministic `example`
  values built from each field's kind + `validation` range.
  Operation-level fields are sorted into a stable key order
  (`tags` → `summary` → `operationId` → `requestBody` →
  `responses` → `x-audit-topics` → `x-permissions`) so two regens
  against the same bundle yield byte-identical YAML. Generation
  remains I/O-free — no FastAPI introspection — keeping the
  cross-runtime fixture and audit-2026 invariants untouched.
- **[Functional, Beautiful]** (v0.3.0 W1 / item 13) Real form
  generation behind `bundle.project.frontend.form_renderer`.
  Additive `JtbdFrontend` schema (Pydantic v2 with
  `extra='forbid'`) introduces a single knob with two values:
  `"skeleton"` (default — the legacy stub `Step.tsx` that renders
  field labels with `<dd>—</dd>` placeholders, byte-identical to
  pre-W1 emission) and `"real"` (working `FormRenderer` invocation
  against the per-JTBD `form_spec.json` plus client-side validators
  derived from `data_capture[].validation`, `show_if` conditional
  visibility via the engine's whitelisted `var` operator,
  default-masked PII fields with eye-toggle, and inline error
  linking via `aria-describedby`). The skeleton path is preserved
  to honour byte-identical regen for every pre-W1 bundle. The real
  path's `show_if` shape — `{var: "context.<edge_id>"}` — uses the
  same expression operator `branch` already uses, so no new
  operator enters the cross-runtime registry. The
  `examples/insurance_claim/jtbd-bundle.json` sets
  `project.frontend.form_renderer = "real"` to lock the real-path
  baseline going forward; `examples/building-permit/jtbd-bundle.json`
  and `examples/hiring-pipeline/jtbd-bundle.json` retain the
  default skeleton path to exercise both regen targets in CI.
- **[Beautiful, Functional]** (v0.3.0 W1 / item 19) State-machine
  diagram emission. New per-JTBD generator
  `flowforge_cli.jtbd.generators.diagram` emits
  `workflows/<jtbd>/diagram.mmd` — a deterministic mermaid
  `stateDiagram-v2` source for the synthesised state machine.
  Swimlanes are coloured by actor role from a fixed palette in
  sorted-unique order; terminal states are distinguished by kind
  (`terminal_success` green, `terminal_fail` red, the
  W0-synthesised `compensated` state overridden to a blue-dashed
  `compensation` class so saga lanes read as separate from
  rejects); transitions carry priority glyphs (● solid for
  priority 0, ┄ dashed for 5..9, ┈ dotted for 10+, ⤺ blue saga
  marker for compensate transitions); SLA budgets render as
  `note right of review` annotations when
  `jtbd.sla_breach_seconds` is set. The generator deliberately
  emits `.mmd` source only — pre-rendering SVG via `mermaid-cli`
  would break byte-identical regen across mermaid-cli versions
  (Principle 1 of the engineering plan); hosts run
  `mmdc -i workflows/<id>/diagram.mmd -o diagram.svg` themselves
  on the deterministic source. The generated README's mermaid
  block embeds the diagram inline so doc readers see the state
  machine without a separate viewer.
- **(v0.3.0 W1)** Cross-runtime expression parity fixture v2.
  New `tests/cross_runtime/fixtures/expr_parity_v2.json` ships 250
  `(expr, ctx, expected)` tuples — the 200 base cases that
  `expr_parity_200.json` already pinned plus 50 new
  `conditional`-tagged cases that exercise the `show_if`-shaped
  fragments the W1 real-form path may emit. Generated
  deterministically by `tests/cross_runtime/_build_fixture_v2.py`.
  `tests/cross_runtime/test_expr_parity.py` is repointed at
  fixture v2 (line 23 `FIXTURE_PATH` constant; lines 33-35 case
  count assertion bumped to 250; lines 50-63 required-tags set
  adds `"conditional"`). The legacy `expr_parity_200.json` is
  retained until W3 per the engineering plan §11.1 — both
  fixtures co-exist while production hosts migrate. The TS
  evaluator in `@flowforge/renderer` reads fixture v2 via the
  vitest sibling and asserts byte-identical agreement; invariant
  5 (cross-runtime parity) stays green against the new corpus.
- **(v0.3.0 W1)** New ratchet
  `scripts/ci/ratchets/no_unparried_expr_in_step_template.sh` —
  Pre-mortem Scenario 2 mitigation. Greps the W1 real-form
  `Step.tsx.j2` template for JSON-DSL expression-shaped tokens
  (`{"var":`, `{"==": [`, `{"!=": [`, `{"and": [`, `{"or": [`,
  `{"not": [`, `{"if": [`); if any are present, asserts that
  fixture v2 exists with ≥ 50 `conditional`-tagged cases. Failure
  is loud and points the contributor at fixture v2 plus the
  PR-template "Touches expr evaluator?" checkbox. Wired into
  `scripts/ci/ratchets/check.sh`'s `RATCHETS=()` array so
  `make audit-2026-ratchets` now reports 5/5 ratchets pass (4
  audit-2026 ratchets + this new one). Legitimate exceptions go
  in `no_unparried_expr_in_step_template_baseline.txt` and
  require security-team review per `scripts/ci/ratchets/README.md`.
- **(v0.3.0 W1)** Example bundle update:
  `examples/insurance_claim/jtbd-bundle.json` declares the new
  `project.frontend = {form_renderer: "real"}` block so the
  regen-diff gate exercises the real-form path going forward.
  `examples/building-permit/jtbd-bundle.json` and
  `examples/hiring-pipeline/jtbd-bundle.json` are unchanged —
  they default to `"skeleton"` and continue to regenerate
  byte-identical to their checked-in trees. Three new artifact
  classes (`openapi.yaml`, `workflows/<id>/diagram.mmd`,
  real-path `ClaimIntakeStep.tsx`) enter the byte-identical
  regen baseline at `scripts/check_all.sh` step 8.

## [0.3.0-engr.0] — Wave 0

> First wave of the v0.3.0 engineering track per
> `docs/v0.3.0-engineering-plan.md`. W0 lands two reliability
> enhancements (item 1 migration safety analyzer; item 2 compensation
> synthesis) plus the matching conformance invariant (10) and a
> stale-docstring fix in the conformance suite header. The track is
> orthogonal to the v0.2.0 content track and to the audit-2026
> follow-ups under `## Unreleased`. Selected as W0 because both items
> close documented gaps with mostly-existing primitives, share no file
> surface (item 1 touches `db_migration` + a new per-bundle generator;
> item 2 touches `transforms.derive_*` + `workflow_adapter` template +
> a new per-JTBD generator), and together unblock the cross-runtime
> fixture v2 work in W1.

- **[Reliable]** (v0.3.0 W0 / item 1) Migration safety analyzer.
  Static rules now run against every emitted alembic migration and
  emit `backend/migrations/safety/<rev>.md` per migration with
  severity-graded findings (NOT NULL backfill on a hinted-large table,
  `CREATE INDEX` without `CONCURRENTLY` on Postgres, type narrowing,
  column drop with no deprecation window). New per-bundle generator
  `flowforge_cli.jtbd.generators.migration_safety`, new
  `flowforge migration-safety` Typer subcommand, new
  `scripts/ci/ratchets/migration_safety_baseline.txt` so generation-time
  catches regressions before any deploy decision. Hooked into
  `flowforge pre-upgrade-check` as a subcheck so the host's CI gate
  surfaces the same advisories operators would otherwise discover by
  hand at PR-review time. Generation stays deterministic — the
  analyzer is a read-only pass over the migration AST.
- **[Reliable, Capable]** (v0.3.0 W0 / item 2) Compensation synthesis.
  `EDGE_HANDLE_TO_STATE_KIND["compensate"]` is now wired through to
  `derive_states` + `derive_transitions`: any JTBD declaring
  `edge_case.handle == "compensate"` gains a singleton `compensated`
  terminal_fail state plus per-edge `<jtbd>_<edge_id>_compensate`
  transitions firing from `review` on event `compensate`, guarded by
  `context.<edge_id>` (same expr shape `branch` already uses, so the
  cross-runtime parity fixture stays untouched). Each compensate
  transition's effects are paired with the *forward* saga in **LIFO**
  order: every `create_entity` → `compensate_delete` (carries the
  forward `entity` field), every `notify` →
  `notify_cancellation` (template `<jtbd>.<event>.cancelled`).
  Effects use the canonical workflow_def schema
  `kind: "compensate"` with `compensation_kind` naming the saga-step
  kind the host registers a handler for (matches engine
  `fire.py`'s saga ledger append). New per-JTBD generator
  `compensation_handlers.py` emits a stub registering the synthesised
  kinds against `flowforge.engine.saga.CompensationWorker`, and
  `workflow_adapter.py.j2` gates a `register_compensations(worker)`
  entrypoint behind `_compensate_transitions` so JTBDs that don't
  opt in regenerate byte-identical.
- **[Reliable]** (v0.3.0 W0 / invariant 10) Conformance invariant 10
  — compensation symmetry. New `@invariant_p1`
  `test_invariant_10_compensation_symmetry` parses
  `tests/conformance/fixtures/compensation_symmetry/jtbd-bundle.json`,
  runs the synthesiser via `normalize`, and asserts that for every
  JTBD with a synthesised `compensate` event the count of
  `compensate_delete` saga steps matches the count of forward
  `create_entity` effects and that the relative order is LIFO. Also
  exercises `_PER_JTBD_GENERATORS[workflow_adapter]` to pin the
  `CompensationWorker` import gate. `make audit-2026-conformance`
  now reports 10 invariants pass.
- **(v0.3.0 W0)** Stale-docstring fix at
  `tests/conformance/test_arch_invariants.py:9`. The header had said
  "8 architectural invariants" since audit-2026; with the E-74
  follow-up adding invariant 9 and W0 adding invariant 10 the count
  drifted twice. The header now reads "10 architectural invariants"
  and references the v0.3.0 signoff checklist alongside the
  audit-2026 one. Bundled with invariant 10 because both edits land
  in the same file.
- **(v0.3.0 W0)** Example bundle update: `examples/insurance_claim/`
  declares a `fraud_detected` edge_case with `handle: "compensate"`
  so the regen-diff gate exercises the compensation synthesiser
  going forward. The other two examples (`hiring-pipeline`,
  `building-permit`) regenerate byte-identical to their checked-in
  trees because they don't declare compensate.

## Unreleased

- **(audit-2026 follow-up)** v0.1.0 release-health pivot: Grafana plan replaced with a tooling-agnostic CLI. Removed `infra/grafana/dashboards/audit-2026-*.json` and the generation script (this stack does not run Grafana). Replaced with `flowforge audit-2026 health` CLI command — probes Prometheus directly, emits PASS/WARN/FAIL per ticket, exits non-zero on any required-probe failure; designed as a post-deploy gate or periodic ops cron. PromQL alert rules in `framework/tests/observability/promql/audit-2026.yml` strengthened from `vector(0)` placeholders to real expressions feeding Alertmanager. Soak test runner + runbook landed (`scripts/ops/audit-2026-soak.sh`, `framework/docs/ops/audit-2026-soak-test.md`); per direction, the 24h soak is treated as complete in the close-out report. Signoff-checklist rows updated to reference the CLI instead of Grafana URLs; close-out criteria 7 & 8 promoted from DEFERRED to ✅.
- **(audit-2026 follow-up E-73)** jtbd-hub per-user RBAC landed. New `flowforge_jtbd_hub.rbac` module exports `Principal`, `Permission` (PACKAGE_PUBLISH/UNPUBLISH/INSTALL, ADMIN_READ/WRITE, AUDIT_READ), `Role` (HUB_ADMIN, PACKAGE_PUBLISHER, PACKAGE_CONSUMER, AUDITOR), and the `PrincipalExtractor` protocol. `create_app(principal_extractor=...)` enforces per-route permission gates; admin routes (demote, set-verified) now require `Permission.ADMIN_WRITE` — 401 on unauthenticated, 403 on authenticated-but-unauthorised. The E-58 `admin_token=` legacy bridge (single-token + comma-separated rotation list) maps valid bearer to the synthetic `LEGACY_ADMIN_PRINCIPAL`; both modes can be configured together for staged migration. Audit events that flow through the registry's `audit_hook` continue unchanged (per-user identity recording is E-73 phase 4, follow-up). 15 new acceptance tests at `framework/python/flowforge-jtbd-hub/tests/test_E_73_rbac.py`.
- **(audit-2026 follow-up E-74)** parallel_fork engine token primitives + invariant 9. Phase 1 of the E-74 design (`framework/docs/design/E-74-parallel-fork-engine-wiring.md`) lands: `flowforge.engine._fork` exposes `make_fork_tokens`, `all_branches_joined`, `consume_token`, `RegionStillForkedError`, `TokenAlreadyConsumedError` for adapters that manage tokens externally (existing host-managed pattern at `tests/integration/python/tests/test_parallel_regions.py` is preserved unchanged). New conformance invariant 9 (`test_invariant_9_parallel_fork_token_primitives_safe`) pins token uniqueness, region-drain semantics, replay-safety, and deepcopy survival. Engine-side wiring through `fire()` (Phases 2–5: per-token transition dispatch, join barrier collapse, e2e test upgrade) remains a follow-up to avoid regressing the audit-2026 invariants 2/3/4.
- **(audit-2026 follow-up)** AU-01 alembic ordinal backfill: out-of-band migration script at `framework/python/flowforge-audit-pg/src/flowforge_audit_pg/migrations/audit_ordinal_backfill.py` (4-step idempotent: add-column → backfill under per-tenant advisory lock → add-constraint → verify) for in-place upgrade of pre-E-37 deployed environments. Fresh deploys via `create_tables()` already have the column.
- **(audit-2026 follow-up CI)** GitHub Actions workflow `.github/workflows/audit-2026.yml` runs `make audit-2026-{unit,conformance,property,edge,cross-runtime,e2e}` as a 6-target matrix on every push/PR plus the ratchet + signoff CI gates. Required-green for merge to main.

## [0.1.0] — 2026-05-08 — audit-2026 release

> First versioned release. Closes all 77 findings from the audit-2026
> sprint (E-32..E-72) under DELIBERATE-mode signoff. **Includes one
> SECURITY-BREAKING change** (E-34: HMAC default secret removed; opt-in
> bridge available for one minor — see SECURITY-NOTE.md and the
> upgrade checklist at `docs/release/v0.1.0-upgrade.md`).
>
> 8/8 architectural invariants conformance-tested. 4/4 security
> ratchets. 11/11 ticket signoffs landed. Full report at
> `docs/audit-2026/close-out.md`.

- **[SECURITY] (audit-2026 E-72, P3)** Audit-2026 sprint close-out. All 77 audit findings closed; 9/9 architecture invariants conformance-tested (8 audit-2026 + invariant 9 parallel_fork token primitives shipped post-tag); ratchets 4/4 PASS; signoff-checklist signed for every active ticket E-32..E-72; framework-level CHANGELOG carries `[SECURITY]` entries for every P0 and the AU-03 escalation. Per-fix observability ships as `flowforge audit-2026 health` CLI (queries Prometheus directly; this stack does not run Grafana). 24h soak runner at `scripts/ops/audit-2026-soak.sh`; runbook at `framework/docs/ops/audit-2026-soak-test.md`. Close-out report at `framework/docs/audit-2026/close-out.md`.
- **[SECURITY] (audit-2026 E-38, P0)** flowforge-jtbd alembic RLS DDL — table-name allow-list + `quoted_name` (J-01). The migration enumerator now compares every target table against an immutable `_KNOWN_TABLES` allow-list before splicing into RLS `CREATE POLICY` / `DROP POLICY` DDL; an attempt to drive the migration over a monkey-patched malicious table list raises `ValueError` before any SQL is emitted. Names are wrapped in `sqlalchemy.sql.quoted_name(..., quote=True)` so even allow-listed values cannot inject across DDL boundaries. Alembic dry-run on prod-shape SQLite asserts upgrade + downgrade are reversible. Closes finding J-01 atomically; pins architecture invariant 8 (migration RLS DDL safety). See `framework/docs/audit-2026/signoff-checklist.md` E-38 row.
- **[SECURITY] (audit-2026 E-37, P0+escalated AU-03)** flowforge-audit-pg — append-only chain hardening (AU-01, AU-02, AU-03 escalated). AU-01: `record()` now wraps the chain-head fetch + insert in a per-tenant advisory lock so 100 concurrent records for one tenant produce ZERO chain forks; new `UNIQUE(tenant_id, ordinal)` constraint catches duplicate ordinals at the DB layer. AU-02: `verify_chain()` streams in `VERIFY_CHUNK_SIZE` keyset-paginated chunks; `tracemalloc` peak is < 256 MB on a 10M-row chain (was unbounded). AU-03 (escalated to P1 SOX/HIPAA gate): canonical golden-bytes fixture committed at `framework/tests/audit_2026/fixtures/canonical_golden.bin`; verify against committed bytes refuses to load on hash mismatch — guards against silent canonical-form drift. Closes findings AU-01, AU-02, AU-03 atomically; pins architecture invariant 7 (audit-chain monotonicity). See `framework/docs/audit-2026/signoff-checklist.md` E-37 row.
- **[SECURITY] (audit-2026 E-36, P0)** flowforge-tenancy hardening (T-01, T-02, T-03). T-01: `_set_config(...)` validates the GUC key against `^[a-zA-Z_][a-zA-Z_0-9.]*$` and binds BOTH the key and value as `:k` / `:v` parameters into the constant SQL `SELECT set_config(:k, :v, true)` — string interpolation across either is structurally impossible. T-02: `_elevated` is a per-instance `ContextVar`; concurrent `elevated_scope()` calls in async tasks observe their own scope only (20-task gather test pins). T-03: `bind_session()` asserts `session.in_transaction()` before any `_set_config` call, raising `AssertionError` if the binder is invoked outside a tx. Closes findings T-01, T-02, T-03 atomically; pins architecture invariant 1 (tenant isolation). See `framework/docs/audit-2026/signoff-checklist.md` E-36 row.
- **[SECURITY] (audit-2026 E-41, P1/P2)** flowforge-fastapi + WS hardening (FA-01..FA-06). FA-01: `CookiePrincipalExtractor` verify canonicalises base64 padding before recomputing the HMAC so re-padded cookies survive intermediaries that normalise `=` padding. FA-02: `issue_csrf_token` defaults `secure=True`; passing `secure=False` raises the new `flowforge_fastapi.ConfigError` unless the caller also passes `dev_mode=True`. FA-03: new `WSPrincipalExtractor` protocol takes `WebSocket` directly via `build_ws_router(ws_principal_extractor=…)`; the legacy "spoof scope['type']='http'" trampoline is gone — the WS scope is never mutated, and an HTTP-only extractor wraps in `_HTTPOnlyAdapter` which constructs a fresh faux Request from a defensive copy of the WS scope. FA-04: `WorkflowEventsHub` is request-scoped at the app level — each `mount_routers` call attaches a fresh hub to `app.state.flowforge_events_hub` and overrides `get_events_hub` per app, so two FastAPI apps in the same process never share subscribers. FA-05: `engine_fire(...)` + `store.put(instance)` ship as one unit of work via the new `_fire_with_unit_of_work` helper that deep-copies the pre-fire snapshot and restores the in-memory `Instance` if `store.put` raises. FA-06: `CookiePrincipalExtractor` now embeds `iat` + `exp` (24 h default; configurable via `ttl_seconds=`); verify rejects expired cookies with 401 (pre-FA-06 cookies without `exp` remain valid — additive, not breaking). See `framework/docs/audit-2026/signoff-checklist.md` E-41 row for evidence trail.
- **[SECURITY] (audit-2026 E-37b, P0)** flowforge-jtbd-hub — explicit signed-at-publish trust gate (JH-01). `Package.signed_at_publish: bool` is now persisted at publish time; default install raises `UnsignedPackageRejected` for any package with `signed_at_publish=False`. Callers must opt in explicitly via `install(..., accept_unsigned=True)`, which routes through the new optional `PackageRegistry(audit_hook=…)` constructor hook (or per-call `audit_emit=…`) and emits a `PACKAGE_INSTALL_UNSIGNED` audit event so operators can attribute the decision. The signature-trust gate is now skipped for accepted-unsigned packages (no signature exists to evaluate) while the `verified_publishers_only` gate still applies. `UnsignedPackageRejected` and `UntrustedSignatureError` messages no longer leak the rejected internal `key_id` — pre-fix the cleartext message gave an attacker partial enumeration of the hub's trust set. Closes finding JH-01 atomically. See `framework/docs/audit-2026/signoff-checklist.md` E-37b row for evidence trail.
- **[SECURITY-BREAKING] (audit-2026 E-34, P0)** flowforge-signing-kms — HMAC default secret removed (SK-01), per-`key_id` signed map (SK-02), and KMS transient-vs-invalid distinction (SK-03). `HmacDevSigning()` with no `FLOWFORGE_SIGNING_SECRET` env var now raises `RuntimeError("explicit secret required …")` instead of silently using the hard-coded `"flowforge-dev-secret-not-for-production"` default. Operators may opt in to the legacy default for one minor-version deprecation window via `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`, which logs a loud `WARNING` and increments the new `flowforge_signing_secret_default_used_total` counter (alert on `> 0` in production). New `HmacDevSigning(keys={kid: secret}, current_key_id=kid)` form carries multiple keys for rotation; `verify(key_id="unknown", ...)` raises `flowforge_signing_kms.UnknownKeyId` rather than silently mismatching. `AwsKmsSigning` / `GcpKmsSigning` now classify provider exceptions: throttling/network/internal → `KmsTransientError` (caller retries with backoff); `NotFoundException` / `NotFound` → `UnknownKeyId`; permanent invalid signature → `verify()` returns `False`. New `flowforge pre-upgrade-check signing` CLI command (F-7 mitigation) verifies host readiness; CI ratchet `scripts/ci/ratchets/no_default_secret.sh` keeps the legacy default from being reintroduced. Migration guidance: `framework/docs/audit-2026/SECURITY-NOTE.md` E-34 row. Closes findings SK-01, SK-02, SK-03 atomically. See `framework/docs/audit-2026/signoff-checklist.md` E-34 row for evidence trail.
- **[SECURITY] (audit-2026 E-32, P0)** flowforge-core engine `fire()` is now per-instance serialised and rolls back on dispatch failure. Concurrent fires for the same `instance.id` raise `ConcurrentFireRejected` (in-flight gate). Outbox or audit-port raises during fire restore the Instance to its pre-fire snapshot (state, context, history, created_entities, saga) and surface `OutboxDispatchError` with the original transport error chained as `__cause__` — no more silent swallow. Closes findings C-01 (`engine/fire.py:283-288`) + C-04 (`engine/fire.py:223-251`) atomically and pins architecture invariant 2 (engine fire two-phase atomicity). Outbox is dispatched before audit so a failure leaves the audit log free of orphan transition rows. See `framework/docs/audit-2026/signoff-checklist.md` E-32 row for evidence trail.
- **[SECURITY] (audit-2026 E-35, P0)** flowforge-core expression registry is now frozen at module-init. Post-startup `register_op(...)` raises `RegistryFrozenError`. Each operator declares an arity at registration; mismatched calls raise `ArityMismatchError` (compile-time via `flowforge.compiler.validate`, runtime fallback in `flowforge.expr.evaluate`). Closes findings C-06 + C-07 atomically and pins architecture invariant 3 (replay determinism) — same DSL across two evaluator instances yields byte-identical guard outcomes. See `framework/docs/audit-2026/signoff-checklist.md` for evidence trail.
- **(audit-2026 E-63, P2)** JS integration-test coverage. New `framework/js/flowforge-integration-tests/ws-reconnect-collab.test.ts` exercises `FlowforgeWsClient` reconnect under a hand-rolled `WebSocketImpl` mock (transient close → backoff → re-emit; `close()` short-circuits reconnect; backoff scales) and the simultaneous-edit collab conflict path (`safeRedo` blocks redo with a user-facing collaboration message after `applyRemotePatch`, the post-conflict undo+redo cycle still works, vanilla undo+redo is fully reversible). Stale `start`/`task`/`review`/`decision`/`wait`/`end` state-kind references left over from JS-05 cleaned up in `Canvas.tsx`, `PropertyPanel.tsx`, `fixtures.ts`, `__tests__/designer.test.tsx`, and `designer-runtime-integration.spec.ts`.
- **(audit-2026 E-66, P3)** Workspace privacy ratchet. All `flowforge-*` JS packages already carry `"private": true`; new `framework/js/flowforge-integration-tests/private-ratchet.test.ts` test pins the invariant so an accidental `npm publish` can't leak workspace code to the registry.
- **(audit-2026 E-62, P2)** flowforge-designer + renderer hardening. JS-04: undo entries embed a monotonic `version` counter; new `safeRedo(store)` helper refuses redo (with a user-facing collaboration-conflict message) when `applyRemotePatch(store, …)` lands while undo state is pending. JS-05: `WorkflowStateKind` aligned with the canonical Python DSL kinds (`manual_review`, `automatic`, `parallel_fork`, `parallel_join`, `timer`, `signal_wait`, `subworkflow`, `terminal_success`, `terminal_fail`); the dead `start` branch in `addState` is gone — first-added state seeds `initial_state` regardless of kind. JS-06: `JsonField`'s `JSON.parse` already wrapped with try/catch and surfaces a `parseError` to `FieldShell`; pinned by acceptance test.
- **(audit-2026 E-61, P2)** flowforge-core DSL hygiene. C-11: `Guard.expr` is now `Annotated[Any, AfterValidator(_validate_expr_shape)]`; multi-key dicts raise `ValidationError` at parse time. C-12: `InMemorySnapshotStore` switched to copy-on-read — `put` records a single shallow clone, `get` returns another shallow clone so caller mutations stay isolated. 200 puts of a 200-key context complete in <250ms (was multi-second under the old per-put-five-clones path).
- **(audit-2026 E-57, P1/P2)** flowforge-cli quality. CL-01 confirmed: `domain_router`, `audit_taxonomy`, `sa_model` generators delegate to substantive Jinja templates; acceptance tests pin >30 LoC output. CL-02: subprocess invocations route through `tutorial._validated_cwd` which rejects relative or missing directories — `Path(".")` call sites replaced with `Path.cwd().resolve()`. CL-03: `new._jtbd_schema` loads exclusively via `importlib.resources.files("flowforge.dsl.schema")`; the `flowforge.__file__` fallback is gone. CL-04: bare `except Exception` in `new._jtbd_schema` replaced with narrowed catch (FileNotFoundError, ModuleNotFoundError, JSONDecodeError, OSError) plus `log.error` and `raise from exc` chained `RuntimeError`.
- **(audit-2026 E-47, P1/P2)** flowforge-jtbd intelligence quality. J-02 conflict-lint pre-buckets writers by `(entity, signature)` so 10K-JTBD inputs lint in <5s (was ~50s). J-03 `BagOfWordsEmbeddingProvider` gains `fit/transform/freeze`; post-freeze `embed()` raises `EmbeddingProviderFrozenError` on unknown tokens, `transform()` drops them silently for replay determinism. J-04 `InMemoryEmbeddingStore` emits a one-shot `PerformanceWarning` pointing to pgvector. J-05 50-prompt adversarial bank with ≥45/50 catch threshold; residual-risk note at `framework/docs/security/nl-injection.md`. J-06 dead `"HIPAA, GDPR"` placeholder removed. J-07 `_extract_json` now uses `json.JSONDecoder.raw_decode`. J-08 `JtbdLockfile.canonical_body()` uses an explicit `_BODY_KEYS` allow-list — new top-level fields require explicit registration. J-09 `_semver` is backed by `packaging.version.Version`; `"1.0.0-"` and `"1.0.0+"` (empty pre-release/build) are rejected.
- **(audit-2026 E-42, P1/P2)** flowforge-outbox-pg hardening. `DrainWorker(table=...)` is regex-whitelisted (OB-01); `sqlite_compat=True` with `pool_size > 1` raises `RuntimeError` (OB-02); a new `reconnect_factory` callback and `worker.reconnects` counter let `run_loop` survive connection-loss exceptions (OB-03); and `last_error` is truncated by a UTF-8 byte budget that never cuts mid-codepoint (OB-04). See per-package CHANGELOG for details.
- **(audit-2026 E-43, P1)** Cross-runtime evaluator parity. The TS evaluator in `@flowforge/renderer` no longer throws on unknown operators (returns `false` — JS-01 fix), uses strict equality only (`===` / `!==` — JS-02 fix), and resolves missing var paths to `null` for parity with Python's `None`. Same-type comparisons (string vs string, number vs number) use native ordering instead of forced `toNumber` coercion. A 200-input cross-runtime conformance fixture lives at `framework/tests/cross_runtime/fixtures/expr_parity_200.json` and is exercised by both `framework/tests/cross_runtime/test_expr_parity.py` (pytest) and `framework/js/flowforge-integration-tests/expr-parity.test.ts` (vitest). The `useFlowforgeWorkflow` hook has a React 19 contract test (`use-flowforge-workflow.test.tsx`, JS-03) that mounts under R19's actual hook implementations via a vitest `react19` alias. Pins architecture invariant 5 (cross-runtime parity).
- Workspace skeleton (uv + pnpm) created.
- flowforge-core: port ABCs, DSL types, JSON schemas, expression evaluator, two-phase fire engine, simulator, in-memory port fakes, unit tests.
