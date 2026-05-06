# Workflow Designer — Capability Spec

## 1. Definition Model (what you build)

### Steps / States
- Named state with label, kind (entry, normal, branch, parallel-fork, parallel-join, terminal-success, terminal-fail, manual-review, automated-task, signal-wait, timer-wait)
- Optional UI hints: color, icon, swimlane (role/department), grid position
- State-level metadata: description, help text, owner-role, tags
- Preconditions: data invariants that must hold to enter (`expr` against instance.context)
- Postconditions: what is guaranteed when state is left
- Idle timeout: auto-transition after X if no event
- Retry policy: on transient failure, max-attempts + backoff
- Sub-workflow embedding (call another workflow def, await completion, map outputs)

### Transitions / Edges
- From-state → To-state with named event (e.g., `submit`, `approve`)
- Trigger kinds: user-action, system-event (cron/webhook/queue), timer (sla-elapsed), signal (external), guard-passed, gate-cleared
- Guards: predicate expressions over instance.context, parties, role, time, custom Python/JS hook
- Effects: assign vars, call action, mutate context, fire notification, write document, emit event
- Priority + ordering when multiple transitions match
- Conditional branching with else fallback

### Gates (governance checkpoints)
- Authority gate: caller must have authority_tier ≥ X
- Permission gate: caller has admin permission Y
- Approval gate: N-of-M approvers from role Z, with reason required
- Co-signature gate: serial vs parallel, with timeout
- Compliance gate: external check (sanctions, KYC, OFAC) returns OK
- Document-complete gate: all required docs present + classified
- Checklist-complete gate: all items checked
- Custom gate: webhook or registered evaluator
- Gate composition: AND, OR, sequence, retry-with-backoff
- Override path: who can break-glass, what evidence required, audit consequence

### Escalations
- Trigger: SLA breach, idle timeout, manual flag, gate-failure threshold
- Action: reassign, notify supervisor chain (1..N levels), priority bump, page on-call, fork to parallel investigation, auto-deny
- Recipients: by role, by org-chart climb, by named user, by tenant operator
- Cool-down: don't re-escalate within X minutes
- Multi-step: tier 1 → tier 2 → tier 3 with separate SLAs each
- Suppress conditions: vacation, business-hours-only, throttle limits

### Document Requirements
- Required document kinds per state (or per transition)
- Cardinality: exactly-N, at-least-N, optional
- Classification rules: required tags/types, freshness (≤ N days old), signed-by
- Acceptance criteria: AV-clean, OCR-confidence ≥ X, schema-validated
- Substitutability: doc A satisfies requirement R unless rejected
- Auto-fetch: pull from external system (Keycloak attestation, prior workflow output)
- Bind to workflow context: doc fields populate instance.context

### Checklists
- Per-state or per-transition
- Item: text, kind (boolean, value-entry, file-upload, signature, evidence-link)
- Required vs advisory
- Conditional visibility (show only if context.X)
- Owner: caller, role, named user
- Evidence capture: comment, photo, link, attachment
- Validation rules
- Bulk-completion via template

### Delegations
- Definition-level: roles allowed to delegate
- Instance-level: temporary reassignment (vacation, load-balance)
- Authority: which permissions/scopes flow to delegate, which stay with principal
- Window: start/end timestamps; auto-expire
- Acknowledgement: delegate must accept (vs implicit)
- Chain-of-custody audit
- Override by ops/operator
- Conflict-of-interest filters (delegate cannot be related party)

### Forms / Data Capture
- Form schema bound to state or transition (JSON-schema or form-builder)
- Fields: scalar, enum, party-picker, document-picker, date, money, repeater
- Conditional fields, computed fields
- Pre-populate from context, prior step, party record
- Validation: client + server, cross-field, async (uniqueness check)
- Persistence: into instance.context with namespace
- Versioned with the workflow def

### Notifications
- Channel: in-app, email, SMS, push, webhook, slack
- Trigger: state-enter, state-exit, transition-fired, sla-warning, gate-rejected, escalation
- Recipients: by role, named, party-on-instance, watcher list
- Template: subject + body with context interpolation
- Deduplication, throttling, quiet-hours, locale, timezone
- Acknowledgement requirements (signed-read receipt for compliance)

### Timers / SLAs
- SLA per state (warning at X%, breach at 100%, critical at Y%)
- Business calendar (skip weekends/holidays per tenant)
- Pause/resume with reason (existing pause clock — extend)
- Schedule-relative deadlines (e.g., "due 5 business days from policy effective date")
- Recurring timers (re-evaluate every N hours)

### Variables / Context Schema
- Typed instance context (JSON-schema)
- Computed expressions (read-only derived fields)
- Variable scoping: workflow-global, per-state, per-transition
- Encryption-at-rest tags for PII fields
- Audit-trail: track every write to context

## 2. Editor UX (how you build it)

### Canvas
- React-flow based, drag-drop nodes/edges
- Auto-layout (Dagre / ELK) + manual override
- Snap-to-grid, alignment guides, multi-select, copy/paste, undo/redo (deep)
- Mini-map, zoom, fit-to-screen, fullscreen
- Swimlanes by role / department / team
- Group / sub-flow collapse (visual only)
- Comments / annotations / sticky notes
- Versioned snapshots with named labels

### Property Panel
- Context-sensitive: clicking node/edge shows its properties
- Sectioned: basics, gates, documents, checklists, delegations, notifications, timers, variables
- Inline validation against the schema
- Expression editor with autocomplete on context vars
- Reference picker for roles, permissions, document types, party kinds, settings
- Import/export JSON for a single node

### Validation
- Real-time: unreachable states, missing terminals, dead-end transitions, cyclic gates, undefined variables, missing required fields
- Severity: error blocks publish, warning is informational
- Lint rules: naming conventions, SLA sanity (≥ 1 min, ≤ 90 days), max graph fan-out, unused variables
- Cross-version compatibility check (instances on prior version still completable)

### Simulation / Test Harness
- Walk-through: pick a path, see context mutations, gate evaluations, generated notifications
- Test cases: stored input contexts + expected end state, replay on every change
- Fault injection: simulate gate-fail, doc-missing, sla-breach, delegation-expired
- Time-travel: advance simulated clock to test timers/SLAs
- Diff against current production version
- Export simulation as Playwright fixture

### Versioning UI
- Branch from published version → draft
- Side-by-side visual diff (added/removed/changed nodes + edges, highlighted)
- Promote draft → review → published (with approval gate on publish itself)
- Tag releases (semver or date)
- Pin instance migrations: which old instances auto-upgrade vs stay on old version

### No-Code Form Builder
- Visual drag-drop palette of field widgets onto a form canvas
- Field widgets: text, textarea, number, money, date, datetime, time, boolean (toggle/checkbox), enum (radio/select/segmented), multi-select (chip/checkbox group), file-upload, signature, rich-text, party-picker, document-picker, address, phone, email, URL, color, percentage, JSON, hidden
- Layout primitives: section, fieldset, tab, accordion, two-column, repeater (array of sub-form), conditional group, divider, heading, help-text card
- Per-field properties panel: label, key, placeholder, default value, required flag, read-only flag, hidden flag, help text, validation rules, format mask, prefix/suffix, min/max/step, regex, custom error messages, locale formatting
- Conditional logic: show/hide field, require field, set value, disable field — based on boolean expression over other fields' values, instance.context, role, party kind
- Computed fields: read-only, formula evaluated client-side and re-validated server-side (e.g., `total = price * qty * (1 + tax_rate)`)
- Lookup fields: query an external source (parties, prior workflow output, FX rate, REST endpoint) — debounced, cacheable, with loading + empty + error states
- Cross-field validation: declarative rules at form level (e.g., `end_date > start_date`, `at_least_one_of(phone, email)`)
- Async validation: server-call debounced (uniqueness check, fraud-score, sanctions match)
- Pre-population: from instance.context, prior step output, party record, query string
- Localisation: per-field translations, RTL support, locale-aware number/date formatting
- Accessibility: WCAG 2.2 AA — label associations, ARIA, keyboard nav, focus management, screen-reader announcements
- Form preview: live render alongside the editor with mock context
- Theming: tenant brand tokens applied (colors, fonts, spacing) — read-only at form level
- Versioning: form definitions versioned with the workflow def (no separate lifecycle)
- Output binding: namespaced into `instance.context` (e.g., form `intake_v1` writes to `context.intake_v1.*`)
- Schema export: emit JSON-schema for backend validation; emit TypeScript types for codegen
- Field library: tenant-private + operator-shared reusable field configs (parameterised)
- Storage: persisted as JSON `form_spec` blob; rendered by a single `FormRenderer` component on the frontend (read by the public portal too)
- Testing: form renderer has snapshot tests + property-based tests for conditional/computed paths

### Templates / Reusable Components
- Library of pre-built fragments (4-eyes-approval, KYC-block, document-collection-checklist)
- Parameterised: drop a fragment, fill in slots
- Tenant-private templates + operator-shared templates
- Import community templates with provenance

### Collaboration
- Multi-user editing (CRDT or lock-per-state)
- Presence indicators
- Comments on nodes/edges with @mentions
- Review workflow: editor → reviewer → approver before publish
- Change requests inline

## 3. Lifecycle (definition states)

### States
- `draft` — editable, never executed
- `in_review` — frozen for editing, awaiting approval
- `published` — immutable, instantiable, default for new instances
- `deprecated` — instances continue but no new starts allowed
- `archived` — read-only, hidden from list, retained for audit
- `superseded` — replaced by a newer version

### Transitions
- create → draft
- draft → in_review (submit for review)
- in_review → draft (request changes)
- in_review → published (approve)
- published → deprecated (start sunset)
- deprecated → archived (after no active instances)
- any → archived (by operator with reason)

### Versioning
- Copy-on-publish: published versions are immutable
- Semantic version: major (breaking), minor (additive), patch (fix-only)
- Version diff API + UI
- Compatibility rules per change kind (e.g., adding states is minor, removing is major)
- Migration scripts for in-flight instances on minor bumps

## 4. Runtime / Execution

### Engine
- Existing engine is the foundation; needs: event-driven loop, signal handling, parallel-state coordination, sub-workflow invocation
- Idempotent transition events (deduplicate by event_id)
- At-least-once delivery of side effects with outbox (already built — reuse)
- Compensation actions (saga pattern) on rollback
- Snapshotting for long-running instances

### APIs
- REST + WebSocket
- Start instance (POST /workflows/{key}/instances) with initial context
- Send event (POST /instances/{id}/events) — fires a transition
- Query state (GET /instances/{id}) with full audit trail
- Subscribe to events (WS /instances/{id}/stream)
- Bulk operations: bulk-reassign, bulk-pause, bulk-cancel
- Search by state/owner/SLA-status with cursor pagination

### Permissions
- Tie into P1-RBAC: each transition's permission requirement evaluated against caller
- Tenant RLS: instances scoped, no cross-tenant reads
- Operator override path with audit

## 5. Monitoring / Reporting

### Per-Instance
- Visual current-state highlight on the def graph
- Timeline of events with actor, timestamp, payload
- Document gallery for the instance
- Checklist completion status
- SLA gauges (current, breached, paused)
- Predicted completion time (based on historical avg)
- "Why am I stuck?" diagnosis (which gate, which doc, which approval)

### Aggregate Dashboards
- Funnel: instances entering vs completing per state
- Bottleneck heatmap (avg dwell time per state)
- SLA breach rate over time
- Top assignees by load
- Reassignment rate, escalation rate, override rate
- Per-tenant + per-product-line slicing
- Custom saved views

### Reports
- Volume reports (started, completed, in-flight) by period
- Throughput, cycle time, lead time per definition
- Compliance reports (override count, missing-doc count, gate-fail count)
- Audit reports (who-did-what windows, exportable)
- Forecasting: predicted volumes, capacity planning

### Alerting
- Threshold alerts on metrics (SLA breach > 5% / hour)
- Anomaly detection (volume drop, latency spike)
- Routing to on-call

## 6. Governance / Audit

### Audit Trail
- Every definition edit: who, when, what changed (diff)
- Every instance event: who fired, what context was at that time
- Tamper-evident hash chain (already built in audit table)
- Immutable post-completion
- Retention policy per tenant
- Export pack (PDF + JSON) for regulators

### Compliance
- 4-eyes on definition publish
- Segregation of duties (designer ≠ approver ≠ executor)
- Per-state PII redaction in displayed context
- Data-residency tagging
- Right-to-erasure compatible (link instance to data subject)

### Access Control
- Role-based: who can view, edit, publish, archive, instantiate, override
- Per-definition ACL on top of role
- Operator unlock for emergencies (with required reason)

## 7. Integration

### Inbound
- Webhook to start/advance instances (signed, idempotent)
- Email-to-instance (CC a workflow address to attach correspondence)
- Schedule-based start (cron)
- API tokens scoped to specific definitions

### Outbound
- Webhooks per event kind (configurable subscriptions)
- Outbox-backed (already built) — at-least-once
- Templated payloads with HMAC signing
- Retry + DLQ
- Per-tenant rate limiting

### External Systems
- SpiceDB sync for permission grants (existing)
- Keycloak attribute lookups
- Document-OCR pipeline integration
- Notification fan-out via Mailgun / SES / Twilio
- Calendar integration for delegations / vacations
- BI export (CDC stream, parquet snapshots)

## 8. Performance / Scale

- Lazy load nodes for graphs > 200 states
- Virtualised lists for instances > 10k
- Read-replica routing for monitoring queries
- Materialised views for dashboards
- Per-tenant query budget enforcement
- Index strategy reviewed per release

## 9. Developer Experience

- CLI: import/export def as JSON; round-trip with editor
- Local dev: run def against fixture context, no DB
- TypeScript types generated from def schema
- Storybook for editor components
- Test harness with snapshot comparison

## 10. Migration Path (existing → new)

- All 23 Python defs survive: codify a JSON-schema reflection that emits equivalent JSON
- Parallel runtime: new defs run on JSON engine, old defs run on Python engine, both write same workflow_instances/events tables
- Per-def opt-in flag to flip
- Deprecate Python engine after N tenants × M months on JSON

---

## Out-of-scope (deliberate)

- BPMN compatibility (use a JSON DSL, not BPMN XML)
- Mobile-first canvas (desktop primary, mobile read-only viewer; rendered forms are mobile-responsive)
- Multi-language IDE-style code editor (only expression snippets)
