# Generation pipeline improvements

Twenty-two proposed enhancements to the JTBD-to-application generation pipeline (`flowforge_cli/jtbd/`), grouped by which property each one most directly serves: **reliable**, **capable**, **functional**, **beautiful**.

Each item is a generation-time enhancement: author once in the bundle, get the property forever. Each item integrates with the existing deterministic pipeline (parse → normalize → 15 generators → write) rather than replacing it. Each is justified by a gap that hand-written equivalents currently leave open.

This is a planning doc, not a commitment. Items are independent; they can land in any order. Effort estimates are not included here because they depend on adapter availability and on whether each item ships its own runtime port (e.g. `AnalyticsPort` for item 16).

Read this together with [`jtbd-generation.md`](jtbd-generation.md) (current pipeline) and [`flowforge-evolution.md`](flowforge-evolution.md) (forward roadmap).

---

## Reliable

### 1. Migration safety analyzer

Static check on every emitted alembic migration against a configured `table_size_hints.json`. Flags `NOT NULL` backfills on tables over a threshold, `CREATE INDEX` without `CONCURRENTLY` on Postgres, type narrowings, column drops with no deprecation window. Emits `migrations/safety/<rev>.md` per migration with severity, blast radius, and suggested rewrites (e.g. "split into two migrations: nullable add → backfill → NOT NULL").

**Justification.** Alembic migrations are the most common single cause of production incidents in flowforge-shaped systems. Generation time is the cheapest place to catch this — pre-commit, before any deploy decision. The rules are encodable as a small static analyzer; the alternative is each operator catching them by hand on review.

**Properties served.** Reliable. Touches: `db_migration` generator + new `migration_safety` per-bundle generator + new `flowforge migration-safety` CLI.

### 2. Compensating-action synthesis

`transforms.EDGE_HANDLE_TO_STATE_KIND` maps `compensate` to `manual_review` and `derive_transitions` emits no compensation effects: the synthesiser slot is empty. Wire it: `compensate` triggers paired effect generation. Each `create_entity` gets a `compensate_delete`; each `notify` gets a `notify_cancellation` template; each external-call effect (when added) gets a documented retraction. Compensations populate `flowforge.engine.SagaLedger` in LIFO order on rollback; durable persistence flows through `flowforge_sqlalchemy.saga_queries.SagaQueries`, and hosts wire the generated map into `CompensationWorker.register(...)`.

**Justification.** The engine already has saga primitives; the JTBD spec already has a `compensate` handle; the gap is the synthesiser. Closing it makes "what happens when this fails halfway?" answerable from the bundle rather than requiring host-supplied compensation maps.

**Properties served.** Reliable, capable. Touches: `transforms.derive_transitions` + `workflow_adapter` template + new compensation-handler stub generator + `CompensationWorker` host wire-up surface.

### 3. Property-test bank per JTBD

Generate a hypothesis property suite per JTBD: any legal event sequence from the initial state must terminate, audit chain stays monotonic, every fire either commits effects atomically or restores the snapshot, no orphan entities. Hypothesis stateful machines map cleanly to the synthesised `workflow_def`.

**Justification.** `tests/property/` exists framework-wide but per-JTBD coverage is generated only if you write it by hand. Auto-emission means every new domain logic ships with its own fuzz suite without authoring discipline. The synthesised state machine already constrains the legal action space — generation can derive the property tests directly.

**Properties served.** Reliable. Touches: new `property_tests` per-JTBD generator + a hypothesis stateful template.

### 4. Guard-aware reachability checker

Beyond the topology check the compiler does today, evaluate guards symbolically (`z3-solver` is already declared under `[dependency-groups] dev`): is every transition reachable under *some* assignment to `context.*`? Are there guards that contradict the workflow's effects (a guard reads `context.X` but no transition writes it)? Emit `workflows/<id>/reachability.json` plus a per-bundle `reachability_summary.md`.

**Justification.** A JTBD whose `large_loss` branch can never fire because nobody populates `context.large_loss` is silently broken at production time. Symbolic reachability proves the gap before deploy. The cost is one z3 invocation per JTBD at generation time.

**Properties served.** Reliable, functional. Touches: new `reachability` per-JTBD generator that imports z3. Note: shipping this as a generator-time check requires moving `z3-solver` from `[dependency-groups] dev` to a `flowforge-cli` runtime extra (or making the check opt-in when the dep is present), since `flowforge jtbd-generate` is invoked from non-dev installs.

### 5. SLA stress harness

Per JTBD with `sla.breach_seconds`, generate a k6 or Locust load test that fires events at the rate implied by the breach budget and asserts the generated app stays under the budget at p95. Generated against the in-memory port fakes for fast loops; can be re-pointed at a staging URL via `--target`.

**Justification.** SLAs declared in bundles are aspirational unless tested. A generated harness makes them empirically testable on every bundle revision and in every PR's CI. The framework already produces deterministic synthetic load — the gap is the harness format.

**Properties served.** Reliable. Touches: new `sla_loadtest` per-JTBD generator + per-JTBD k6 / Locust template.

### 6. Router-level idempotency keys

Generate the router and service to require an `Idempotency-Key` header on every `POST /<jtbd>/events` request and dedupe against a per-tenant `idempotency_keys` table. Successful responses are cached and re-served on duplicate keys; in-flight duplicates return `409 Conflict` rather than racing the engine. Migration is emitted alongside the entity table; the dedupe TTL defaults to 24 hours and is configurable per JTBD.

**Justification.** Network retries, browser double-submits, and saga retry loops all produce duplicate events. Without idempotency keys, the engine's per-instance serialisation surfaces duplicates as `ConcurrentFireRejected` rather than as a clean "already processed" response. Generating the dedupe machinery once means every JTBD inherits it; hand-wiring it per project is one of the most reliably-skipped reliability tasks.

**Properties served.** Reliable. Touches: `domain_router` template + `domain_service` template + `db_migration` generator (extra `idempotency_keys` table per JTBD) + new `idempotency` per-bundle generator for the lookup helper.

### 7. Backup / restore drill artefact

Generate `docs/ops/<bundle>/restore-runbook.md` listing every table the bundle creates, their FK dependency order, the required `pg_dump` flags, the audit-chain re-verification step (`flowforge audit verify --tenant ...`), and a `make restore-drill` target that runs the runbook against a scratch database and asserts every audit chain re-verifies. Designed for the monthly DR tabletop.

**Justification.** Disaster-recovery drills sit in audit checklists but are usually skipped because writing the runbook is bespoke per project. The bundle already declares every entity and every audit topic; the runbook is derivable. Generating it converts "restore from backup and prove it works" from a half-day project into a one-command exercise. Adjacent to item 15 (admin console) but distinct: the admin console operates on a running system; this artefact operates on cold storage.

**Properties served.** Reliable, functional. Touches: new `restore_runbook` per-bundle generator + `Makefile` target.

---

## Capable

### 8. Bundle-derived OpenAPI 3.1

Emit `openapi.yaml` directly from the bundle, not via FastAPI introspection. Operations are tagged by JTBD id; request bodies pull `examples` from `data_capture.validation` ranges; responses document the audit topics each operation emits via an `x-audit-topics` extension; `x-permissions` lists the gate each operation evaluates.

**Justification.** A static spec drives downstream client SDK generation, contract testing, postman collections, and AI tool descriptors — none of which require booting the FastAPI app. Today's choice (FastAPI introspection) means consumers must reverse-engineer the workflow surface. Bundle-derived emission is a one-shot, cacheable artifact.

**Properties served.** Capable. Touches: new `openapi` per-bundle generator.

### 9. Multi-frontend emission

Today the frontend generator emits Next.js. Add: a Typer CLI client (`flowforge-app claim_intake submit --policy-number ...`); a Slack adapter (events as slash commands, transitions as interactive messages); an email-driven adapter (transitions by replying to notification emails — useful for high-frequency manual review). All four share the OpenAPI spec from item 8 and the runtime-client.

**Justification.** Enterprise ops, support, and customer surfaces are different surfaces. Right now flowforge generates one. Multi-frontend is the gap between "demo" and "real deployment", and is one of the more common reasons projects fork the generator.

**Properties served.** Capable. Touches: new `frontend_cli`, `frontend_slack`, `frontend_email` per-bundle generators.

### 10. Bundle-version diff with deploy-safety classes

`flowforge bundle-diff old.json new.json --html` produces a categorised report:

- **Additive** (new JTBDs, optional fields, info-severity audit topics) — safe to ship without coordination.
- **Requires-coordination** (new permissions, new required fields, renamed states) — needs RBAC seed update + form invalidation + comms.
- **Breaking** (column type narrowed, enum value removed, transition with existing instances retargeted) — needs migration plan + instance-class compatibility check.

**Justification.** Bundles will evolve in production; categorising each change by its deploy-safety class lets reviewers route the right ones through migration-coordination workflows and ship the rest without ceremony. The classification rules are mechanical given two parsed bundles.

**Properties served.** Reliable. Touches: new `flowforge bundle-diff` CLI + a diff library invokable from CI.

### 11. Data lineage / provenance graph

Emit `lineage.json` tracing every `data_capture` field from form input → service → ORM column → audit-event payload → outbox envelope. For PII fields, annotate retention window, redaction strategy at each stage, and exposure surfaces (which roles can read, which audit events leak it, which notification channels carry it).

**Justification.** GDPR / HIPAA / CCPA audits ask "where does this PII live?". A generated graph answers structurally rather than relying on a static-analysis pass over hand-written code. The bundle already declares `data_sensitivity` and `pii`; the graph is the closure under transformation.

**Properties served.** Capable, reliable. Touches: new `lineage` per-bundle generator.

### 12. OpenTelemetry by construction

Wrap every `fire`, every effect dispatch, every audit append in OTel spans carrying `tenant_id`, `jtbd_id`, `state`, `event`, `principal_user_id` as attributes. The `MetricsPort` adapter exports OTel meters with consistent naming (`flowforge.fire.duration_seconds`, histogram bucketed at SLA-budget multiples). Generated `service.py`, `router.py`, and the outbox worker all carry instrumentation by default.

**Justification.** Every flowforge app needs distributed tracing in production; baking it in at generation time means consistency across deployments rather than per-project ad-hoc wiring. The naming convention also makes cross-project dashboards reusable.

**Properties served.** Capable, reliable. Touches: `domain_service`, `domain_router`, `workflow_adapter` templates + new `flowforge-otel` adapter package.

---

## Functional

### 13. Real form generation, not skeleton

The current frontend templates self-describe the component as "dumb" (`Step.tsx.j2` line 19) and the generated TSX renders field labels with `<dd>—</dd>` placeholders, no inputs. Replace with a working `FormRenderer` invocation against the generated `form_spec.json` plus generated client-side validators from `data_capture.validation` (regex, min/max, custom). Add conditional visibility (`show_if: context.large_loss`), per-field PII visual treatment (default-masked with eye-toggle), and inline error linking via `aria-describedby`.

**Justification.** The template names this a stub by design; the cost of going stub → working form is low and the UX delta is large. Hosts currently have to either rebuild the form by hand or hand-wire `FormRenderer` themselves.

**Properties served.** Functional, beautiful. Touches: `frontend` per-JTBD generator + `@flowforge/renderer` integration.

### 14. Faker-driven seed data

Per JTBD, emit ten rows per state with realistic values: `Faker.email()` for `email` kinds, `Faker.name()` for `text` of label "claimant_name", `Faker.address()` for `address`, ranges from `validation` for `number` / `money`. Loaded through the service layer (so RLS, audit chain, and permissions engage). Available via `make seed` in the generated app.

**Justification.** Empty databases are useless for demoing or iterating UI. Hand-writing seed data is one of the most repeatedly-skipped tasks in flowforge-style apps; generation closes the gap once.

**Properties served.** Functional. Touches: new `seed_data` per-bundle generator + `Makefile` target.

### 15. Tenant-scoped admin console

A second generated frontend: per-instance browser, audit-log viewer with hash-chain verification (calls `AuditSink.verify_chain`), saga compensation panel, permission-grant history, deferred outbox queue, RLS elevation log. Reuses the same `permissions.py` for who-can-see-what.

**Justification.** Every operational ticket starts with "what state is instance X in, who touched it last, did its audit chain verify?". Building this once per project is wasteful; building it once at generation time is universal. The data-source primitives exist as ports (`AuditSink`, `OutboxRegistry`, `SagaLedger`) plus the Postgres adapters (`flowforge-audit-pg`, `flowforge-outbox-pg`, `flowforge_sqlalchemy.SagaQueries`). The generated console will assume Postgres-backed hosts; non-PG storage backends would need their own adapter or a host shim.

**Properties served.** Functional, capable. Touches: new `frontend_admin` per-bundle generator + per-bundle React app.

### 16. Closed analytics-event taxonomy

Generate `analytics.py` (and a TS sibling) with a `StrEnum` of every analytics event the JTBD emits: `claim_intake.field_focused`, `claim_intake.field_completed`, `claim_intake.validation_failed`, `claim_intake.submission_started`, `claim_intake.submission_succeeded`, `claim_intake.form_abandoned`. Step-component lifecycle hooks fire the events through an `AnalyticsPort` (Segment / Mixpanel / Amplitude / noop).

**Justification.** Product analytics taxonomies drift from workflow taxonomies in every system that doesn't generate both. Generating both from the same bundle keeps them locked. Closed enums also let dashboards be statically validated.

**Properties served.** Functional, capable. Touches: new `analytics_taxonomy` per-bundle generator + new `AnalyticsPort` ABC.

### 17. i18n scaffolding with empty-translation lint

`bundle.project.languages = ["en", "fr-CA"]` is already declared. Emit a JSON catalog per language keyed by field labels, button text, audit-event human-readable templates, SLA-warning copy. The React step component reads via a generated `useT()` hook with type-safe keys. The bundle linter flags untranslated keys per language with severity by `compliance` (Quebec workflows with `compliance: [...]` and missing `fr-CA` strings get `error`).

**Justification.** Enterprise rollouts almost always need ≥2 languages; retrofitting i18n is one of the most expensive refactors in workflow apps. The bundle already declares languages — generating the plumbing closes a wide gap for low cost.

**Properties served.** Functional, capable. Touches: new `i18n` per-bundle generator + linter rule + `frontend` template.

---

## Beautiful

### 18. Design-token-driven theming

Add a `bundle.project.design` block: primary / accent colours, font family, density (`compact|comfortable`), radius scale. Generate a CSS variable palette + Tailwind config + a TS theme module. Step component, layouts, admin console, screenshots all read the same tokens. A single colour change re-themes the entire generated app deterministically.

**Justification.** Generated apps from different bundles look identical today. A token block is cheap to author and lets every JTBD bundle ship a distinct visual identity without forking templates. It also makes design-system contributions tractable — a single PR to the token defaults re-themes every downstream app on regen.

**Properties served.** Beautiful. Touches: bundle schema (additive), `frontend` and `frontend_admin` templates, new `design_tokens` per-bundle generator.

### 19. State-machine diagram emission

During generation, render `workflows/<id>/diagram.svg` (and a `.mmd` mermaid source) of the synthesised state machine. Swimlanes coloured by actor role, edge-case transitions visually overlaid by priority, terminal states distinguished by kind, SLA budgets annotated on long-running states. Embedded into the generated README and the user-doc page.

**Justification.** A diagram next to the JSON DSL is the fastest mental model for a new contributor; auto-generation means it can never drift from the workflow_def. The framework already constructs the state machine in `transforms.derive_states` — rendering it is a small additional step.

**Properties served.** Beautiful, functional. Touches: new `diagram` per-JTBD generator (mermaid CLI + SVG export).

### 20. Per-JTBD operator manual

Generate `docs/jtbd/<id>.mdx` from the bundle: `situation` / `motivation` / `outcome` as the introduction, `success_criteria` as the "how to know it worked" section, the synthesised state diagram embedded, the generated form rendered statically as a screenshot, every audit topic listed with its human-readable template.

**Justification.** Enterprise rollouts always have a training-material line item; the JTBD already contains the source prose. Generating the manual closes a content gap that's currently filled by hand or skipped entirely. The output is a presentable user-facing document.

**Properties served.** Beautiful, functional. Touches: new `operator_manual` per-JTBD generator.

### 21. Visual regression as a CI gate

Render every generated frontend page through Playwright at three viewports (mobile, tablet, desktop) and commit baseline screenshots to `examples/<example>/screenshots/`. A `flowforge-screenshot-diff` step in CI compares against baselines and posts the diff as a PR comment. Add to `scripts/check_all.sh` step 8 alongside the byte-identical regen check.

**Justification.** Visual regressions in generated frontends are otherwise invisible until an operator notices in production. Adding visual snapshots to the regen-diff gate catches them at PR time, when fixing them is cheapest. Per-JTBD Playwright spec files are already emitted by the generator (`tests/e2e/<id>.spec.ts`); a project-level Playwright runner is still deferred per `tests/integration/README.md` and would land alongside this item.

**Properties served.** Beautiful, reliable. Touches: `scripts/check_all.sh`, new `tests/visual_regression/` layer, baseline screenshot directory per example.

### 22. Last-mile copy polish via opt-in LLM

A `flowforge polish-copy --tone <profile>` command runs an offline LLM pass over the bundle's user-facing strings: field labels, helper text, button labels, error messages, notification templates. Tone profiles (`formal-professional`, `friendly-direct`, `regulator-compliant`) shape the rewrite. Results are written *back into the bundle* as overrides — never into generated code, never to canonical fields like `success_criteria`. Gated behind explicit opt-in with a dry-run / diff preview.

**Justification.** An actuary writes excellent `success_criteria` and terrible button labels; an LLM is good at the latter and bad at the former. Splitting the labour by competence improves the surface that customers see while leaving canonical fields untouched. This would be the only LLM touchpoint in the pipeline; deterministic regen is preserved because the LLM run is a separate authoring step, not a generation step.

**Properties served.** Beautiful. Touches: new `flowforge polish-copy` CLI + bundle-overrides field schema.

---

## Cross-cutting observations

A few patterns emerge across the list.

**Generation-time vs runtime weight.** The list weights toward generation-time artifacts rather than runtime features because that's where the determinism guarantee compounds. Anything generated can be regenerated; anything hand-written is a maintenance liability. The single biggest gap in the current pipeline is that the generator produces *runnable* code but not *operable* code. Items 15 (admin console), 12 (OTel), 1 (migration safety), and 7 (restore runbook) close that gap. Two items (12 OTel, 16 analytics) also introduce new runtime ports (`MetricsPort` extension and `AnalyticsPort` respectively); they are still generation-driven but expand the runtime port surface.

**Specs as interoperability primitives.** Several ideas (8 OpenAPI, 16 analytics, 11 lineage) share a pattern: emit a static, bundle-derived spec alongside the runtime code, so downstream tools can consume the spec without booting the app. Specs are the cheapest interoperability primitive; any time you can replace runtime introspection with a generated spec, you remove a dependency on the running system.

**Beauty as a generation-time property.** Items 18-21 argue that "beautiful" is not a UI-time decision but a generation-time property. If every JTBD emits a diagram, a screenshot baseline, a manual, and a themed render from the same source bundle, the visual surface coheres without anyone enforcing style guides at code-review time.

**Single LLM touchpoint.** Item 22 is the only LLM touchpoint and is deliberately scoped to *labels and copy*, not to canonical fields. This preserves the current "no LLM in the deterministic pipeline" property while still capturing the productivity win where LLMs are competent. Authors who don't want any LLM in their workflow simply don't run the command.

**Sequencing.** If picking a starting subset:

- **Highest leverage on existing stack:** items 2 (compensation synthesis), 13 (real form), 19 (diagram), 15 (admin console). Each closes a documented gap with mostly-existing primitives.
- **Highest reliability return:** items 1 (migration safety), 3 (property tests), 4 (reachability), 6 (idempotency keys), 7 (restore runbook). Each catches a class of bug or operational failure at generation time.
- **Highest interoperability return:** items 8 (OpenAPI), 11 (lineage), 16 (analytics taxonomy). Each adds a static spec downstream tools can consume.
- **Visible UX wins:** items 13 (real form), 18 (design tokens), 21 (visual regression), 20 (operator manual). Each makes the generated app obviously better to look at and use.

A reasonable first wave would be 2 + 13 + 19 + 1 + 8: closes a long-standing synthesiser gap, replaces a stub with real functionality, adds two new spec / artifact emitters, and lands a reliability gate. The pairs are mostly independent, with two front-end-touching dependencies to call out: 13 (real form) and 19 (diagram) both modify the generated frontend output, so 13 should land first; subsequently, items 18 (design tokens), 21 (visual regression baselines), and 16 (analytics) all touch `Step.tsx.j2` and should be sequenced 18 → 21 (so baselines reflect the themed render) and 13 → 16 (so analytics hooks attach to a real form). Items 1, 2, and 8 are independent of the frontend chain.
