# Workflow Designer — Architecture

Companion to `docs/workflow-ed.md`. The capability spec describes *what* the
designer can do; this doc describes *how* it is built and how the pieces
communicate.

## 1. Goals & Non-Goals

### Goals
- Tenants edit, version, publish, archive workflow definitions visually.
- Definitions describe states, transitions, gates, escalations, document
  requirements, checklists, delegations, notifications, timers, variables,
  and forms — all in a single JSON DSL.
- Existing 23 Python `WorkflowDefinition` instances continue to execute
  unchanged during migration.
- A single rendered `FormRenderer` is reusable in the admin app, the public
  portal, and Playwright fixtures.
- Tamper-evident audit on every edit + every instance event.
- Outbox-backed at-least-once side-effect dispatch (reuse existing P2 work).
- RBAC integration with the resolver introduced in P1-RBAC.

### Non-Goals
- BPMN XML import/export.
- Multi-runtime engine swap (we keep one engine; we feed it both Python defs
  and DB JSON defs).
- Full programmatic Python escape hatch in the DSL — gates can call named
  registered evaluators, but cannot embed arbitrary Python.

## 2. Top-Level Topology

```mermaid
flowchart TB
  subgraph FE["Frontend (Next.js, frontend/src/app/admin/workflows/)"]
    DC[DesignerCanvas (react-flow)]
    FB[FormBuilder (form-spec editor)]
    Store[WorkflowEditorStore (zustand)<br/>draft + form-spec, validation, undo/redo]
    API[workflows-api.ts (REST + WS)]
    DC --> Store
    FB --> Store
    Store --> API
  end
  API -- "HTTP+WS, CSRF (P15-COOKIE), RBAC (P1)" --> BE
  subgraph BE["Backend (FastAPI, backend/app/workflows_v2/)"]
    DR[designer_router.py]
    RR[runtime_router.py]
    DS["designer_service.py / runtime_service.py<br/>validate · version · publish · diff · simulate · hydrate"]
    EN[engine.py (shared, existing)]
    FV[form_validator.py (jsonschema)]
    DR --> DS
    RR --> DS
    DS --> EN
    DS --> FV
  end
  BE --> DB[(Postgres: workflow_definitions, _versions,<br/>form_specs, instances, events, tokens, saga, audit)]
```

## 3. The DSL (JSON Schema)

A workflow definition is one JSON document. Top-level shape:

```jsonc
{
  "key": "claim.standard",
  "version": "1.4.0",
  "subject_kind": "claim",
  "initial_state": "intake",
  "metadata": {
    "label": "Standard claim",
    "description": "...",
    "owner_role": "claims_manager",
    "tags": ["claims", "p1"]
  },

  "states": [
    {
      "name": "intake",
      "kind": "manual_review",
      "label": "Intake",
      "swimlane": "claims_intake",
      "ui": { "x": 100, "y": 80 },
      "preconditions": [],
      "idle_timeout_seconds": null,
      "documents": [
        { "kind": "claim_form", "min": 1, "max": 1, "freshness_days": 30 }
      ],
      "checklists": [
        { "id": "intake_basics", "items": [
          { "id": "id_verified", "label": "Identity verified", "kind": "boolean", "required": true }
        ]}
      ],
      "form_spec_id": "intake_form_v3",
      "sla": { "warn_pct": 80, "breach_seconds": 14400 }
    }
  ],

  "transitions": [
    {
      "id": "submit",
      "event": "submit",
      "from_state": "intake",
      "to_state": "triage",
      "guards": [
        { "kind": "expr", "expr": "context.intake_form.policy_id != null" }
      ],
      "gates": [
        { "kind": "permission", "permission": "claim.create" },
        { "kind": "documents_complete" },
        { "kind": "checklist_complete", "checklist_id": "intake_basics" }
      ],
      "effects": [
        { "kind": "set_assignee", "role": "triage_officer" },
        { "kind": "notify", "template": "claim.submitted" }
      ]
    }
  ],

  "escalations": [
    {
      "trigger": { "kind": "sla_breach", "state": "triage" },
      "actions": [
        { "kind": "reassign_to_role", "role": "triage_supervisor" },
        { "kind": "notify", "template": "claim.triage.escalated" }
      ],
      "cooldown_seconds": 900
    }
  ],

  "delegations": {
    "allowed_roles": ["claims_handler", "underwriter"],
    "auto_expire_days": 30,
    "requires_acknowledgement": true
  },

  "context_schema": {
    "type": "object",
    "properties": {
      "intake_form": { "$ref": "#/$defs/intake_form" }
    }
  },

  "form_specs": [
    /* see Form DSL below */
  ]
}
```

The schema lives at `backend/app/workflows_v2/schema/workflow_def.schema.json`
and is mirrored to TypeScript via `pnpm gen:workflow-types`.

### Form DSL (subset)

```jsonc
{
  "id": "intake_form_v3",
  "version": "3.0.0",
  "title": "Claim intake",
  "fields": [
    { "id": "policy_id", "kind": "lookup",
      "label": "Policy",
      "source": { "endpoint": "/api/policies/search", "param": "q" },
      "required": true },
    { "id": "incident_date", "kind": "date",
      "label": "Date of incident",
      "validation": { "max": "today" },
      "required": true },
    { "id": "loss_amount", "kind": "money",
      "label": "Estimated loss",
      "validation": { "min": 0 } }
  ],
  "layout": [
    { "kind": "section", "title": "Policy & loss", "field_ids": ["policy_id", "incident_date", "loss_amount"] }
  ],
  "rules": [
    { "kind": "show_if", "field_id": "loss_amount", "expr": "policy_id != null" }
  ],
  "computed": [
    { "id": "is_large_loss", "expr": "loss_amount > 100000" }
  ]
}
```

Forms are addressable by `form_spec_id`. They can be standalone (referenced
from many workflows) or inlined. Reusable forms live in the
`form_specs` table; inlined forms live inside the def JSON.

## 4. Storage

### Tables

```sql
-- Logical definition (one row per (tenant_id, key))
ums.workflow_definitions (
  id              uuid pk,
  tenant_id       uuid not null,
  key             text not null,
  current_version uuid null fk → workflow_definition_versions(id),
  status          text check (status in ('draft','in_review','published','deprecated','archived','superseded')),
  created_at, updated_at, created_by_user_id,
  unique (tenant_id, key)
);

-- Each saved version (immutable once published)
ums.workflow_definition_versions (
  id            uuid pk,
  definition_id uuid not null fk → workflow_definitions(id),
  version       text not null,            -- semver
  status        text not null,            -- draft|in_review|published|deprecated|archived
  spec          jsonb not null,           -- the full DSL document
  spec_hash     text not null,            -- sha256 over canonical JSON
  parent_version_id uuid null,            -- chain for diff/lineage
  created_at, created_by_user_id,
  published_at, published_by_user_id,
  archived_at,  archived_by_user_id, archive_reason text,
  unique (definition_id, version)
);

-- Reusable forms (optional — most live inside the spec)
ums.form_specs (
  id           uuid pk,
  tenant_id    uuid not null,
  key          text not null,
  version      text not null,
  spec         jsonb not null,
  spec_hash    text not null,
  status       text,
  created_at, updated_at,
  unique (tenant_id, key, version)
);

-- Existing tables (extended, not replaced)
ums.workflow_instances ADD COLUMN
  definition_version_id uuid null fk → workflow_definition_versions(id);

ums.workflow_events  -- unchanged; engine writes here

-- Simulation & test fixtures
ums.workflow_simulations (
  id           uuid pk,
  definition_version_id uuid not null,
  name         text not null,
  initial_context jsonb not null,
  expected_path jsonb not null,
  last_run_at  timestamptz,
  last_result  text,                    -- pass|fail
  unique (definition_version_id, name)
);
```

RLS policies follow the rest of the schema: every read scoped by
`tenant_id` GUC; operator may bypass with `app.elevated`.

### Why not single-table?

Splitting `workflow_definitions` (logical) from `workflow_definition_versions`
(physical) gives:

- Cheap "current version" read (one indexed FK).
- Immutable history — `versions` rows never mutate after publish; the
  definition row's `current_version` pointer flips on publish.
- Easy diff: any two version IDs.
- Archival without losing instance pinning.

## 5. Backend Surface

### New package: `backend/app/workflows_v2/`

```
workflows_v2/
├── __init__.py
├── schema/
│   ├── workflow_def.schema.json
│   └── form_spec.schema.json
├── models.py              # SQLAlchemy ORM (the 4 tables above + extension)
├── views.py               # Pydantic request/response shapes
├── designer_router.py     # /admin/workflow-designer/*
├── designer_service.py    # CRUD + validate + publish + archive + diff + simulate
├── runtime_router.py      # /workflows/{key}/instances/*
├── runtime_service.py     # start, event, query, list, bulk
├── compiler.py            # JSON spec → in-memory engine objects
├── validator.py           # static analysis (unreachable, dead-end, schema)
├── form_validator.py      # form spec + form data validation
├── simulator.py           # walk a path; track context mutations
└── audit.py               # adapter on top of app.audit.service
```

### Endpoints (designer)

| Verb | Path | Auth | Purpose |
|------|------|------|---------|
| GET    | `/api/admin/workflow-designer/definitions`               | rbac:wf.view  | List defs |
| POST   | `/api/admin/workflow-designer/definitions`               | rbac:wf.edit  | Create draft |
| GET    | `/api/admin/workflow-designer/definitions/{id}`          | rbac:wf.view  | Read latest |
| GET    | `/api/admin/workflow-designer/definitions/{id}/versions` | rbac:wf.view  | List versions |
| GET    | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}` | rbac:wf.view | Read one |
| PATCH  | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}` | rbac:wf.edit | Update draft |
| POST   | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}/submit-review` | rbac:wf.edit | draft → in_review |
| POST   | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}/approve`       | rbac:wf.publish | in_review → published (4-eyes; approver ≠ author) |
| POST   | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}/reject`        | rbac:wf.publish | in_review → draft + comment |
| POST   | `/api/admin/workflow-designer/definitions/{id}/deprecate`                    | rbac:wf.publish | published → deprecated |
| POST   | `/api/admin/workflow-designer/definitions/{id}/archive`                      | rbac:wf.publish | deprecated → archived |
| POST   | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}/diff/{vid2}`   | rbac:wf.view | Pretty diff |
| POST   | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}/simulate`      | rbac:wf.view | Walk a path |
| POST   | `/api/admin/workflow-designer/definitions/{id}/versions/{vid}/validate`      | rbac:wf.view | Static lint |

### Endpoints (runtime)

Build on existing `/api/admin/workflows/*` and add:

| Verb | Path | Purpose |
|------|------|---------|
| POST | `/api/workflows/{key}/instances`              | Start instance, accepts initial context |
| POST | `/api/workflows/instances/{id}/events`        | Fire event (transition) — idempotent by `event_id` |
| GET  | `/api/workflows/instances/{id}/timeline`      | Events + audit + doc list |
| GET  | `/api/workflows/instances/{id}/why-stuck`     | Diagnose blocker |
| WS   | `/api/workflows/instances/{id}/stream`        | Live updates (state changes, sla warnings) |

CSRF + cookie auth via P15-COOKIE middleware, RBAC via P1-RBAC resolver,
state-changing requests follow the API status-code rule (200 for
state-transition, 201 only for new resources).

### Compiler

`compiler.compile(spec_json) -> CompiledDef` returns an object with:

- `states_by_name`, `transitions_by_event`
- `gate_evaluators` — looked up from a registry keyed by gate-kind
- `effect_runners` — same pattern
- `form_renderers` (server-side; for re-validation only)
- `escalation_handlers`

The compiler runs at definition publish *and* lazily at runtime (cached
per `definition_version_id` in process memory).

### Engine integration

The existing `engine.py` already has the inner `transition()` machinery.
We extend its registry to accept compiled defs at runtime, in addition
to Python-coded ones. Same code path for both — compiled defs simply
present the same shape `engine` expects.

## 6. Frontend Surface

### New routes / pages

```
frontend/src/app/admin/workflow-designer/
├── page.tsx                           # list view
├── new/page.tsx                       # create empty draft
└── [id]/
    ├── page.tsx                       # designer canvas (default tab)
    ├── form-builder/page.tsx          # form-builder canvas
    ├── versions/page.tsx              # version list + diff
    ├── simulate/page.tsx              # simulation panel
    └── audit/page.tsx                 # audit trail
```

### Components

```
frontend/src/components/workflow-designer/
├── DesignerCanvas.tsx                 # react-flow canvas
├── DesignerToolbar.tsx                # save/publish/diff/simulate
├── PropertyPanel/
│   ├── StateProperties.tsx
│   ├── TransitionProperties.tsx
│   ├── GateEditor.tsx
│   ├── EscalationEditor.tsx
│   ├── DocumentRequirementEditor.tsx
│   ├── ChecklistEditor.tsx
│   └── DelegationEditor.tsx
├── FormBuilder/
│   ├── FormCanvas.tsx
│   ├── FieldPalette.tsx
│   ├── FieldProperties.tsx
│   ├── ConditionalRulesEditor.tsx
│   └── PreviewPane.tsx
├── FormRenderer/                      # used by editor preview AND runtime
│   ├── FormRenderer.tsx
│   ├── fields/                        # one component per field kind
│   └── validators.ts
├── ValidationPanel.tsx
├── DiffViewer.tsx
└── SimulationPanel.tsx
```

`FormRenderer` is the single React component that any caller (admin,
portal, claim form, application intake) uses. It accepts a `form_spec`,
an `initialContext`, and an `onSubmit` callback.

### State management

`zustand` store per editor session (already used elsewhere in admin):
- `editor.spec` — current draft JSON
- `editor.dirty`, `editor.history` (undo/redo via `temporal`)
- `editor.validation` — output of validator
- `editor.simulation` — last sim result

Persistence: debounced PATCH to backend, optimistic UI, conflict handled
via version-cursor (server returns 409 if `parent_version_hash` mismatches).

### Library choices

- `reactflow` (already used) — canvas
- `@hookform/resolvers` + `react-hook-form` — form runtime
- `ajv` — client-side JSON-schema validation (matches backend)
- `dagre` — auto-layout
- `monaco-editor` (lazy) — expression editor

## 7. Audit & Compliance

Every designer-router mutation calls `app.audit.service.record` with:

- `subject_kind = "workflow_definition_version"`, `subject_id = vid`
- `payload` containing the diff hash and the actor's reason
- The hash chain (existing) makes tampering visible.

On publish, an `audit_event` of action `wf.def.published` is required;
the resolver enforces 4-eyes (creator ≠ approver) at the service layer.

## 8. Migration Path

Capability-unit phases (week numbers removed per M12; sequencing
follows §17.13).

### Phase A — Coexistence
Ship the new schema (§17 tables) + `workflows_v2/` package. Backend
serves both engines: lookup `workflow_definitions`; if published, use
compiled JSON; else fall back to Python registry. Frontend designer
mounts behind `wf.designer.enabled` (default off).

### Phase B — Backfill
Reflect each of the 23 Python defs into JSON via
`scripts/reflect_python_workflows.py`. Insert as `published v1.0.0`
under the operator tenant; tenants fork to override. Per-def parity
fixture compares end states + audit events; CI fails on divergence.

### Phase C — Cutover
Per-tenant opt-in flips `wf.designer.enabled`. New tenants default to
JSON. Python defs marked `deprecated` after 30 days at zero new starts.

### Phase D — Sunset
Drop the Python registry path. Delete `app/workflows/definitions/*.py`
(only after the adapter-retention CI guard §17.8.3 confirms no
non-archived def-version still references those modules). Update
`app/workflows/registry.py` to read from DB only.

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| DSL diverges from Python defs (semantic drift) | M | H | Reflection script + per-def fixture parity test in CI |
| Editor performance on graphs >200 states | L | M | Lazy load + virtualisation; test fixture with 500-state graph |
| Form-builder complexity creeps to "another visual programming language" | M | H | Cap on field kinds, conditional rules expressed as DSL not JS, no nested rules deeper than 3 |
| Versioning bugs strand instances | L | H | Always pin `definition_version_id` on instance; never auto-upgrade without explicit migration script |
| RBAC mismatch between gate-permission and resolver | L | H | DB-backed `permission_catalog` table (§20.8) used by both gates and routes; CI guard fails on drift |
| Concurrent editors clobber each other | M | M | Optimistic locking via `parent_version_hash`; later upgrade to CRDT if needed |
| Form spec validation differs client vs server | M | M | Shared JSON-schema, same `ajv` ruleset on both sides |

## 10. Testing Strategy

| Layer | Tests |
|-------|-------|
| Schema | JSON-schema self-tests (positive + negative fixtures) |
| Compiler | Unit: spec → CompiledDef shape; reject malformed |
| Validator | Lint rules — unreachable state, dead-end transition, undefined var, missing terminal |
| Engine | Reuse existing `tests/test_workflows_*` against compiled defs |
| Designer service | RBAC, lifecycle transitions, diff stability, simulate determinism |
| Runtime service | Idempotent events, parallel forks, sla timers |
| FormRenderer | Snapshot per field-kind + property combination |
| End-to-end | Playwright: create draft → edit → simulate → submit-review → approve → instantiate → fire events → archive |
| Performance | 500-state def render <400ms p95 cold/<100ms warm; 100-event timeline <100ms p95; 10k instance list <300ms p95; validator lint <200ms (see §20.4 for full budget table and CI fixture) |
| Migration | Per-Python-def parity fixture |

## 11. Phased Plan (deliverables per phase)

| Phase | Deliverables | Tests |
|---|---|---|
| **P-WD-1** Foundation | Alembic for §17 tables (`tokens`, `saga_steps`, `elevation_log`, `migrations`, `quarantine`, `business_calendars`, `pending_signals`) + `workflow_events.external_event_id` + rename `instances.status`→`aggregate_status`. `workflows_v2/` skeleton (schema + models + views). JSON-schema fixtures + TS types. Empty routers registered. RBAC catalog extended. | schema fixtures, RBAC contract |
| **P-WD-2** Designer CRUD + lifecycle | `designer_service` create/update/list/get/diff. Lifecycle (draft→in_review→published) with audit. Validator (static lint, duplicate-priority check, lookup-permission publish-time check, elevation justification check). Frontend: list page + create draft + read-only canvas. Two-phase fire() commit path. Elevation log writes. | lifecycle FSM, validator coverage, RBAC, two-phase fire |
| **P-WD-3** Editor canvas (R/W) | DesignerCanvas + PropertyPanel (state/transition/gate/escalation/delegation). Optimistic-locking PATCH. Undo/redo. Autosave. | editor store, conflict handling |
| **P-WD-4** Form builder | FormBuilder + FormRenderer + form_validator. form_specs CRUD + version drift policy. | snapshot + property tests |
| **P-WD-5** Runtime integration | compiler.py + engine accepts compiled defs. runtime_router (start/event/query/why-stuck). WebSocket stream. Saga DLQ→compensation handoff (`wf.saga.compensate` outbox handler). Calendar snapshotting. Signal correlator job. Sub-workflow start/return. Reflect 23 Python defs; parity fixture. | parity, idempotent events, saga, calendar, signals, sub-workflows |
| **P-WD-6** Sim + diff + monitoring | simulator.py + SimulationPanel. DiffViewer. Timeline + why-stuck. Aggregate dashboards. | replay determinism, diff stability |
| **P-WD-7** Cutover & sunset | Per-tenant opt-in flag. Python registry deprecation. Delete Python def files (only after adapter-retention CI guard §17.8.3 green). Final pyright + pytest sweep. | retention CI, end-to-end Playwright |

## 12. Platform Integration

This section enumerates every existing platform subsystem the designer
must integrate with. Each item lists *what we touch*, *how*, and *which
phase* the work lands in.

### 12.1 RBAC (P1-RBAC)

- Seed new workflow permissions into `ums.permission_catalog` (§20.8)
  via `backend/app/workflows_v2/permissions_seed.py` (idempotent upsert
  at startup): `workflow_designer.view`, `workflow_designer.edit`,
  `workflow_designer.publish`, `workflow_designer.archive`,
  `workflow.runtime.start`, `workflow.runtime.event`,
  `workflow.runtime.override`. The `AdminPermission` enum is superseded
  by the DB-backed catalog; existing enum values become seed rows.
- Designer + runtime routers use `Depends(require_admin_permission(...))`
  decorators (the resolver landed in P1).
- Gate kind `permission` evaluates the same `simulate_effective_access`
  helper used by the request-time resolver — single source of truth.
- 4-eyes on publish enforced in `designer_service.publish` by checking
  `version.created_by_user_id != caller.user.id`.
- Strict `tests/admin/test_rbac_contract.py` baseline test must remain
  green after wiring (every new `/admin/workflow-designer/**` route has
  a permission dep).

Phase: **P-WD-1** (catalog + routes), **P-WD-2** (publish 4-eyes).

### 12.2 Cookie auth + CSRF (P15-COOKIE)

- All designer + runtime POST/PATCH/DELETE go through the existing
  `CsrfDoubleSubmitMiddleware`.
- WebSocket runtime stream uses cookie auth (existing path), no Bearer
  fallback for browsers under `COOKIE_ONLY_BROWSER`.
- Frontend `workflows-api.ts` reuses `frontend/src/lib/http.ts` so
  `credentials: "include"` + `X-CSRF-Token` echo are automatic.

Phase: **P-WD-1**.

### 12.3 Outbox + cross-cut (P2-OUTBOX)

- Side effects (notifications, SpiceDB grants, webhook fire-out, audit
  fan-out) enqueue via `app.core.cross_cut.dispatch(BEST_EFFORT_OUTBOX)`.
- Register new outbox handlers under
  `app.workers.outbox_worker.HANDLERS`:
  - `wf.notify` — render template + send via notification dispatcher.
  - `wf.spicedb_grant` — call existing `_direct_write_relationships`.
  - `wf.webhook` — HMAC-sign + POST to subscriber, retry per existing
    DLQ rules.
- Definition publish + archive themselves dispatch `wf.audit.published`
  through the outbox so downstream BI consumers see them.

Phase: **P-WD-5** (handlers land with runtime).

### 12.4 Platform packages (P35-PLATFORMSPLIT)

- Settings: register namespaced entries via
  `app.platform.settings.registry`:
  - `workflow.designer.enabled` (bool, per-tenant gate for the editor)
  - `workflow.designer.simulation_max_steps` (int)
  - `workflow.designer.publish_requires_signature` (bool)
  - `workflow.runtime.default_sla_seconds` (int)
  - `workflow.runtime.escalation_cooldown_seconds` (int)
  - `workflow.runtime.business_calendar_id` (text)
- Flags: `workflow.designer.enabled` is a feature flag (read via
  `app.platform.flags`) — controls UI mount + designer-router enable.
- Signing: when `publish_requires_signature=true`, the publish endpoint
  takes a signed-request via `app.platform.signing.require_signature`
  (already in use on flag/setting writes per P1).
- FX: not directly used; mention only because money fields in forms can
  reference `app.platform.fx` for currency conversion.

Phase: **P-WD-1** (registry seeds), **P-WD-2** (signing wired).

### 12.5 Document subsystem (`app/documents`)

- Document-requirement gates query the existing documents tables.
  Define an evaluator at
  `app.workflows_v2.gate_evaluators.documents.documents_complete(spec, instance, session)`
  that:
  - Resolves required kinds from the state's `documents` array.
  - Calls `app.documents.service.list_for_subject(...)` to fetch attached
    docs.
  - Applies cardinality + freshness + classification rules.
- Auto-fetch effects:
  `app.workflows_v2.effect_runners.attach_document` invokes the
  documents service to create a link from a referenced document into the
  instance.
- Document-required form fields use the existing
  `frontend/src/components/documents/document-table.tsx` for picking.

Phase: **P-WD-5**.

### 12.6 Notifications

- Reuse existing `app.notifications.render` + dispatcher.
- Add notification kinds:
  `workflow.state_entered`, `workflow.transition_fired`,
  `workflow.sla_warning`, `workflow.sla_breached`,
  `workflow.gate_rejected`, `workflow.escalation_triggered`,
  `workflow.delegation_invited`, `workflow.delegation_acknowledged`.
- Templates live under `app/notifications/templates/workflow/*.tmpl`
  with locale variants.
- Subscribers (channel preference: in-app, email, slack, webhook)
  follow existing `notification_preferences` rows.

Phase: **P-WD-5**.

### 12.7 SpiceDB grants for delegations

- When a delegation is acknowledged, enqueue a `wf.spicedb_grant`
  outbox row that:
  - Adds `delegate@user → can_act_as → principal@user` for the
    delegation window.
  - Reverses the grant on auto-expire or revoke.
- Reuse `app/auth/spicedb.py:write_resource_grants` exactly as the P2
  outbox path expects (no special case).

Phase: **P-WD-5**.

### 12.8 Frontend conventions

- Every fetch in the designer goes through
  `frontend/src/lib/admin-api.ts` (`adminQuery`/`adminMutate`); no raw
  `fetch(` outside the helpers (P3 ESLint rule already enforces this).
- All React Query keys use `useTenantQueryKey` so tenant-scope
  invalidation works on tenant switch.
- `useCurrentTenantScope` informs read-only mode for cedant tenants
  viewing operator-shared definitions.
- The whole designer mounts inside `AdminPageLayout` so it inherits the
  scoped admin `QueryClient` (P4: `staleTime ≥60s`, `gcTime ≥10min`).
- The existing `frontend/src/components/workflows/WorkflowGraphViewer.tsx`
  is *retained* as a read-only renderer (used in instance detail pages);
  the new `DesignerCanvas` is editor-only.

Phase: **P-WD-2 / P-WD-3 / P-WD-4**.

### 12.9 ReadSession (P4)

- Designer GETs (list/read/diff) and runtime read endpoints (timeline,
  why-stuck, list instances) declare `ReadSession` (per P4 default for
  GETs).
- The CI scan `tests/ci/test_read_session_on_gets.py` is extended to
  include the two new routers.

Phase: **P-WD-1** (router skeletons), **P-WD-6** (final scan
extension).

### 12.10 CI guards

- `backend/scripts/check_no_new_admin_service_mocks.sh`: extend the
  blocklist to include `app.workflows_v2.designer_service` and
  `app.workflows_v2.runtime_service` once those exist (any new
  `unittest.mock.patch` of those symbols fails CI).
- `backend/scripts/check_no_admin_flag_imports.sh`: no change needed —
  workflow_v2 imports nothing from `app.admin.flags`.
- New CI guard `check_workflow_def_drift.sh`: per-PR, run the
  Python-vs-JSON parity fixture for any def whose Python file or JSON
  reflection changed.

Phase: **P-WD-2** (mock guard), **P-WD-5** (drift guard).

### 12.11 Operational tasks integration

- Existing `app/tasks/service.py` provides operational-task tracking.
- Stuck-instance signal: when an SLA breach lands, the runtime emits a
  `workflow.sla_breached` event; an outbox handler creates an
  operational-task row of kind `workflow_stuck` with the instance
  link, so the existing tasks dashboard surfaces it.
- The "Why am I stuck?" diagnosis writes its summary into the
  operational task's `note` field for one-click context.

Phase: **P-WD-6**.

### 12.12 Threshold alerts pipeline

- SLA breach rate, escalation rate, override rate are exposed as
  metric kinds the existing `app/threshold_alerts/evaluator.py` already
  understands (it gained per-tenant batching in P3).
- Define new threshold-alert metric kinds:
  `workflow.sla_breach_rate`, `workflow.gate_failure_rate`,
  `workflow.override_rate`. Operators configure thresholds in the
  existing admin UI.

Phase: **P-WD-6**.

### 12.13 Audit (existing hash-chain table)

- Every designer mutation calls `app.audit.service.record` with
  `subject_kind="workflow_definition_version"`, `payload` containing
  the diff hash + reason.
- Every runtime event (transition fired, gate rejected, override
  applied, delegation acknowledged) calls
  `app.audit.service.record` — the existing tamper-evident hash chain
  carries through.
- The audit-resolved.md mapping for finding C3 (no `alg:none`) is
  unaffected — designer never mints tokens.

Phase: **P-WD-2** (designer audit), **P-WD-5** (runtime audit).

### 12.14 RLS

- Both new tables (`workflow_definitions`, `workflow_definition_versions`,
  `form_specs`, `workflow_simulations`) carry `tenant_id` and have RLS
  policies installed in the alembic migration with the same shape as
  the existing `tenant_settings` policy (uses `app.tenant_id` GUC, with
  `app.elevated` bypass for operator).
- All admin sessions go through `tenant_session` so the GUC is set;
  bootstrap seed runs under elevated session.

Phase: **P-WD-1**.

### 12.15 Migration workbench (existing)

- `migration_workbench` tables (from migration 0053) already model
  generic data-migration runs. Reuse them for the
  Python-→-JSON reflection step:
  - Each Python def reflected becomes a `migration_workbench_run` row.
  - Parity fixture pass/fail recorded per-row.
  - Operator can view results in the existing workbench UI.

Phase: **P-WD-5** (during the cutover).

### 12.16 Deploy runbook

- Append a "Workflow Designer rollout" section to
  `docs/runbooks/audit-remediation-deploy.md` (or split into
  `docs/runbooks/workflow-designer-rollout.md`) with:
  - Per-tenant flip checklist.
  - Pre-flight: parity fixture green for all 23 Python defs.
  - Post-deploy: 5xx rate, queue depth, instance start latency, gate
    eval p95.
  - Rollback: flip flag off → instances continue on JSON engine but
    no new designer edits.

Phase: **P-WD-7**.

### 12.17 Existing /admin/workflows page

- Keep the existing page mounted at `/admin/workflows` (instance ops:
  list, pause, resume, reassign — landed via P0/P1 work).
- New designer mounts at `/admin/workflow-designer` so the two surfaces
  do not collide.
- Add an in-page link from each definition row in `/admin/workflows`
  to its designer page.

Phase: **P-WD-2**.

## 13. Embedding existing screens as workflow steps

Every domain UI (claims, policies, applications, parties, documents,
payments, recovery, reserving, ai-assist, tenants, users) must be
embeddable as a workflow step without forking its codebase.

### 13.1 The WorkflowStep contract

Every embeddable screen exports a wrapper component with this prop
shape:

```ts
type WorkflowStepProps = {
  instance: WorkflowInstance;        // id, def_version, current_state, context, sla
  formSpec?: FormSpec;               // when the state binds a form
  readOnly?: boolean;                // monitoring + audit replay
  onSubmitEvent: (event: string, payload: unknown) => Promise<void>;
  onSaveContext: (patch: Record<string, unknown>) => Promise<void>;
  onCancel?: () => void;
};
```

The wrapper:

1. Fetches the domain object via the existing API helpers.
2. Hides its top-level chrome (header, save toolbar) — those become the
   workflow shell's responsibility.
3. Routes mutations through `onSubmitEvent` (so the engine logs them as
   transition payloads with full audit).
4. Renders read-only when `readOnly=true` (used for audit replay).

### 13.2 Step registry

```ts
// frontend/src/components/workflow-designer/step-registry.ts
export const STEP_REGISTRY = {
  "claim.detail":       () => import("@/components/claims/claim-step"),
  "policy.endorsement": () => import("@/components/policies/endorsement-step"),
  "application.intake": () => import("@/components/applications/intake-step"),
  "document.review":    () => import("@/components/documents/review-step"),
  "party.kyc":          () => import("@/components/parties/kyc-step"),
  "payment.refund":     () => import("@/components/payments/refund-step"),
  "ai.review":          () => import("@/components/ai-assist/review-step"),
  /* one entry per embeddable domain screen */
};
```

A state references a step by registry key:

```jsonc
"states": [{
  "name": "intake_review",
  "kind": "manual_review",
  "embedded_step": { "kind": "application.intake", "props": { "show_history": true } }
}]
```

The runtime renderer at `/workflows/instance/[id]` dynamically imports
the registered component and supplies the standard props.

### 13.3 Per-domain adjustments

| Domain | Adjustment |
|---|---|
| Claims          | Extract `ClaimDetailContent`; export `ClaimStep` wrapper that hides save buttons, routes mutations via `onSubmitEvent`. |
| Policies        | Endorsement form already stateful — wrap as `PolicyEndorsementStep`. |
| Applications    | Intake becomes a form_spec; review becomes `ApplicationReviewStep`. |
| Documents       | Doc-table + classification editor become `DocumentReviewStep` (already partly modular). |
| Parties         | KYC + sanctions screen → `PartyKYCStep`. |
| Recovery / Reserving | Read-only analyst-review step. |
| AI-assist       | Suggestion-acceptance UI → `AIReviewStep`. |
| Tenants / Users / Roles | Admin steps for onboarding workflows. |

### 13.4 Generic capabilities the wrappers need

- **Action interception**: every button calls `onSubmitEvent` instead of
  its private API.
- **Context binding**: each screen reads/writes
  `instance.context.<namespace>` instead of its own local state.
- **Validation passthrough**: domain-level validators expose a pure
  `validate(context)` so the engine can re-validate before firing a
  transition.
- **Audit hooks**: every interaction emits a `workflow_event` with
  actor + payload.
- **Read-only mode**: same component renders historical state for
  replay.
- **Permission lift**: the wrapper queries `simulate_effective_access`
  to decide which buttons are visible (gate hints up front).

### 13.5 Backend adapter pattern

Each domain ships a small `workflow_adapter` module:

```python
# e.g. app/claims/workflow_adapter.py
async def render_context(session, claim_id) -> dict
async def apply_transition(session, claim_id, event, payload) -> Result
async def validate(session, context) -> list[ValidationError]
```

This keeps domain logic owned by the domain while the engine drives
orchestration. The runtime calls these adapters when the spec sets
`embedded_step.kind`.

### 13.6 Phasing

- **P-WD-3**: registry + 2 reference adapters (claims, applications).
- **P-WD-4**: form-builder coexists with embedded steps (a state has
  either a form_spec OR an embedded_step).
- **P-WD-5**: backfill 8 domain adapters as Python defs are reflected.

## 14. Expressions, calculations, transformations on transitions

A single restricted JSON-Logic-style language covers all three
expression slots in the DSL.

### 14.1 The three slots

| Slot | Purpose | Return type |
|---|---|---|
| **Guards** | predicate that allows/blocks a transition | boolean |
| **Effects** | mutate `instance.context`, set assignee, fire notification, schedule timer, call adapter | side-effecting action descriptors |
| **Computed** | read-only derived values exposed to UI + downstream guards | scalar/object |

### 14.2 DSL examples

```jsonc
// Guard
{ "kind": "expr",
  "expr": { "and": [
    { ">": [{ "var": "context.intake.loss_amount" }, 0] },
    { "not_null": { "var": "context.intake.policy_id" } },
    { "in": [{ "var": "caller.role" }, ["claims_handler", "underwriter"]] }
  ]}
}

// Effect: set value with computation
{ "kind": "set",
  "target": "context.triage.priority",
  "expr": { "if": [
    { ">": [{ "var": "context.intake.loss_amount" }, 100000] }, "high",
    { ">": [{ "var": "context.intake.loss_amount" }, 10000] },  "normal",
    "low"
  ]}
}

// Effect: transform (map a list)
{ "kind": "set",
  "target": "context.policy_summary",
  "expr": { "map": [
    { "var": "context.policies" },
    { "object": { "id": { "var": "$.id" }, "premium": { "var": "$.premium_amount" } }}
  ]}
}

// Computed (read-only)
{ "id": "is_large_loss",
  "expr": { ">": [{ "var": "context.intake.loss_amount" }, 100000] }
}
```

### 14.3 Whitelisted operators

- **Logic**: `and`, `or`, `not`, `if/elif/else`, `==`, `!=`, `<`, `<=`,
  `>`, `>=`
- **Arithmetic**: `+`, `-`, `*`, `/`, `%`, `pow`, `round`, `floor`,
  `ceil`, `abs`, `min`, `max`, `sum`
- **String**: `concat`, `lower`, `upper`, `trim`, `substring`,
  `regex_match`, `format`
- **Date/time**: `now`, `parse_date`, `add_days`, `add_business_days`,
  `diff_seconds`, `is_before`, `is_after`, `is_business_day`,
  `truncate_day`
- **Money/FX**: `convert_currency` (calls `app.platform.fx`),
  `add_money`, `multiply_money`, `format_money`
- **List/object**: `map`, `filter`, `reduce`, `length`, `any`, `all`,
  `keys`, `values`, `pick`, `omit`, `merge`, `in`, `index`
- **Null safety**: `coalesce`, `not_null`, `default`
- **Identity**: `caller.user_id`, `caller.role`, `caller.tenant_id`,
  `caller.authority_tier`
- **Lookups (async, whitelisted)**: `lookup_party(id)`,
  `lookup_policy(id)`, `lookup_claim(id)`, `lookup_setting(key)`,
  `lookup_workflow_output(workflow_key, instance_id, field)` — results
  cached per evaluation.

### 14.4 Sandbox guarantees

- **No I/O** outside the named `lookup_*` whitelist.
- **No `while`/recursion-as-loop**; AST recursion depth capped
  (configurable, default 8).
- **Bounded execution**: max 1000 ops per evaluation, max 200 ms wall
  time, hard fail on exceed.
- **Deterministic**: same `(spec, context, caller, now_seed)` ⇒ same
  result. `now()` reads from `evaluation_context.now`, which the engine
  pins at the start of a transition for replay.
- **No mutable globals** — every operator is pure.

### 14.5 Design-time validation

- AST parser rejects unknown operators and malformed shapes.
- Type inference walks the expression against `context_schema` and
  the operator signature table; emits *"field X is referenced but not
  declared"* and *"type mismatch: comparing string to number"* errors
  in the editor.
- Lint warnings: unused computed fields, deeply nested conditionals
  (>4), suspect numeric overflow.

### 14.6 Editor UX

- **Expression editor**: monaco with custom language mode, autocomplete
  on `var`-paths drawn from the context schema, hover documentation on
  each operator.
- **Test panel**: paste a sample context; see the expression result
  instantly; failing assertions highlight the offending sub-expression.
- **Visual builder for common shapes**: dropdowns for `field op value`,
  switch ladder for `if/elif/else`, drag-to-reorder for
  `map/filter/reduce` chains. Power users drop into raw JSON.

### 14.7 Server-side execution

- Engine has `app/workflows_v2/expr/evaluator.py` — pure-Python
  implementation of the operators. No `eval`, no `exec`, no AST execution
  outside the whitelist.
- Lookups are async; the evaluator awaits them. Engine batches lookups
  across all expressions in a single transition to amortise round trips.
- Compilation cached per `(definition_version_id, expression_hash)` so
  the AST is parsed once per process.

### 14.8 Audit + replay

- Every transition records
  `evaluated_expressions: [{ path, ast_hash, result, lookup_keys }]`
  into `workflow_events.payload`.
- Replay tool reconstructs decision paths exactly (deterministic
  evaluator + pinned `now`).

### 14.9 Migration of existing Python guards

- Each Python `Transition.guard` callable maps to either:
  - A simple DSL expression (most existing guards are field-comparison
    heavy), OR
  - A registered named evaluator
    `app.workflows_v2.evaluators.<name>` for cases where the logic
    needs to call domain services. The DSL allows
    `{ "kind": "named", "name": "claims.coverage_in_force", "args": {...} }`
    to invoke them.
- Coverage target: ≥90% of guards as pure DSL. The remainder ride
  named evaluators with explicit allow-list and audit.

### 14.10 Phasing

- **P-WD-2**: AST + evaluator + design-time validation + simple
  expression editor.
- **P-WD-3**: monaco-backed editor, visual builders, test panel.
- **P-WD-5**: lookup whitelist + named evaluator registry; map all
  Python guards.

## 15. Schema awareness & safe data writes

### 15.1 Two layers, on purpose

The designer is **schema-aware** but never issues raw SQL.

| Layer | Knows | Writes via |
|---|---|---|
| Editor (design time) | Domain entity catalog, fields, FKs, RLS, validation rules | nothing |
| Runtime engine       | Same catalog, plus current row state                     | domain adapters only |

Direct SQL writes from the workflow are forbidden. Every mutation goes
through a registered domain adapter (claims, policies, parties, etc.)
that already enforces every invariant the domain tables require — RLS,
FK, business rules, hash chains. This is the same boundary that admin
HTTP routers respect.

### 15.2 The Entity Catalog

The editor reads a generated *catalog* describing what is writable from
inside a workflow:

```jsonc
// generated by scripts/build_workflow_catalog.py from SQLAlchemy models
{
  "entities": {
    "claim": {
      "table": "ums.claims",
      "primary_key": "id",
      "tenant_scoped": true,                  // tenant_id auto-injected
      "soft_delete": true,
      "fields": [
        { "name": "policy_id",      "type": "uuid", "required": true,
          "fk": { "entity": "policy", "on_delete": "RESTRICT" } },
        { "name": "incident_date",  "type": "date", "required": true },
        { "name": "loss_amount",    "type": "money", "required": true,
          "validation": { "min": 0 } },
        { "name": "status",         "type": "enum",
          "values": ["draft","submitted","triage","approved","rejected"] }
      ],
      "create_adapter": "app.claims.workflow_adapter.create_claim",
      "update_adapter": "app.claims.workflow_adapter.update_claim",
      "delete_adapter": null,                  // not allowed from workflows
      "lookup_adapter": "app.claims.workflow_adapter.lookup_claim",
      "permissions": {
        "create": "claim.create",
        "update": "claim.update"
      }
    },
    "policy": { /* ... */ },
    "party":  { /* ... */ },
    "document": { /* ... */ }
  }
}
```

The catalog is a *narrowed* projection of the SQLAlchemy schema. Tables
without a `workflow_adapter` (audit_events, alembic_version, internal
queue tables, secrets, RBAC grants) **are not in the catalog and cannot
be written from a workflow** — period.

The catalog is regenerated at build time via
`scripts/build_workflow_catalog.py`, committed under
`backend/app/workflows_v2/catalog/entities.json`, and shipped to the
frontend as a TypeScript module. CI fails if the committed catalog
drifts from what the script would emit.

### 15.3 What the editor sees

When designing a state or transition, the editor lets the designer:

- **Bind a form field to a catalog field**: e.g., the form's
  `policy_id` field can reference `entity:policy.id` and renders a
  `lookup_adapter`-backed picker that respects tenant RLS.
- **Add a "create entity" effect**: `{ "kind": "create_entity",
  "entity": "claim", "values": { "policy_id": { "var":
  "context.intake.policy_id" }, "incident_date": ... } }` — the editor
  shows required-field validation and FK-target hints inline.
- **Add an "update entity" effect** with the same shape; primary key is
  required.
- **Reject impossible bindings at edit time**:
  - Field marked `required: true` not provided → error.
  - Type mismatch (e.g., expression returns string, field expects
    decimal) → error.
  - FK target entity not in the catalog → error.
  - Adapter-less entity targeted → error.
- **Show RLS hints**: "this entity is tenant-scoped — `tenant_id` is
  auto-injected from the caller's session, do not set manually".

### 15.4 Referential integrity guarantees

#### Design time
- The catalog declares FKs, NOT NULL, enums, and check constraints.
- The editor's static validator rejects:
  - References to missing entities.
  - Required-field omissions.
  - Enum-value mismatches.
  - Cyclic create-order in a single transition (entity A needs B's id;
    B needs A's id).

#### Runtime
- Mutations go through `app.<domain>.workflow_adapter.<verb>`.
- Each adapter:
  - Opens the existing tenant-bound `AsyncSession` (RLS GUC already
    set).
  - Validates inputs against Pydantic models (the same models the
    domain HTTP router uses).
  - Executes the same service-layer call (e.g.,
    `claims_service.create`) so all invariants — FKs, business rules,
    audit-chain inserts, outbox enqueues — fire identically to a
    user-driven HTTP request.
- All effects in one transition execute inside one DB transaction.
  - Adapter raises domain-typed exceptions
    (`NotFoundError`, `ValidationError`, `IntegrityError`) and the
    engine maps them to a transition failure → audit event recording
    the rejection reason → instance stays in the previous state.
  - On `IntegrityError` (e.g., FK target deleted between guard
    evaluation and effect), the transaction rolls back; the
    cross-cut policy decides whether to retry, escalate, or mark the
    instance failed.
- Side effects that cross system boundaries (SpiceDB, notifications,
  webhooks) ride the outbox (P2). They commit as outbox rows in the
  same transaction; if the transaction rolls back, the rows never
  appear.

### 15.5 Tenant scoping

- Every catalog entity flagged `tenant_scoped` has `tenant_id`
  auto-injected from the active session's GUC. The DSL has no way to
  override it — the field is hidden from the editor's value form for
  tenant-scoped entities and the runtime adapter ignores any value
  supplied for it.
- Cross-tenant reads in lookups are blocked by RLS. The editor's
  `lookup_*` operators only see rows the caller's tenant can see.
- Operator workflows that legitimately need cross-tenant visibility set
  `evaluation_context.elevated=true` and the engine sets
  `app.elevated=true` for the duration of the transition. This is a
  per-definition flag, audited on every fire.

### 15.6 Soft-delete + retention

- Adapters honour `soft_delete=true` (status flip, `deleted_at`
  timestamp) — workflows never DELETE rows directly.
- Audit-table rows (P3 hash chain) and `workflow_events` rows are
  immutable; no adapter exposes a write to them other than `record`.

### 15.7 Compensation / sagas

- For multi-step writes that span systems (e.g., create claim →
  generate document → notify reinsurer), each effect is paired with a
  named *compensation* in the catalog (`reverse_create_claim`,
  `delete_generated_document`, etc.).
- If a downstream effect fails after upstream effects committed (the
  outbox case where SpiceDB fails after the DB write), the engine
  schedules the compensation through the outbox. This is the saga
  pattern, but driven by the catalog rather than ad-hoc code per
  workflow.

### 15.8 Migration story

- Existing 23 Python defs that already mutate domain rows do so via
  service calls. The reflection script generates equivalent
  `create_entity`/`update_entity` effects in the JSON DSL pointing at
  the same adapter — no behavioural change.
- Tables without an adapter today (e.g., a long tail of admin-only
  tables) get adapters added on demand as workflows need to write to
  them; each adapter PR follows the standard "service + view + RBAC"
  pattern from prior phases.

### 15.9 Phasing

- **P-WD-1**: catalog generator + 4 entities (`claim`, `policy`,
  `party`, `document`). CI drift check.
- **P-WD-3**: editor shows catalog hints + binds form fields to
  catalog fields.
- **P-WD-5**: `create_entity` / `update_entity` effects, adapter
  registry, transaction + saga semantics, compensation map.
- **P-WD-6**: catalog coverage expanded to all writable domains.

## 17. Runtime Correctness Addendum (review iteration 1)

This section is normative. It supersedes any softer language earlier in the
doc and addresses critic findings C1–C8 and M1, M3 with concrete schema,
algorithms, audit hooks, and test obligations. Existing platform paths
cited as absolute repo paths.

### 17.1 Tokens, parallel regions, fork/join (closes C1)

#### 17.1.1 Schema

```sql
ums.workflow_instance_tokens (
  id                 uuid pk,
  instance_id        uuid not null fk → workflow_instances(id) on delete cascade,
  region_id          text not null,            -- DSL region identifier ("root" for the default trunk)
  current_state      text not null,
  status             text not null check (status in
                       ('active','paused','awaiting_signal','awaiting_compensation',
                        'completed','cancelled','failed')),
  parent_token_id    uuid null fk → workflow_instance_tokens(id),
  fork_event_id      uuid null fk → workflow_events(id),
  join_group_id      uuid null,                -- groups sibling tokens for join evaluation
  status_changed_at  timestamptz not null default now(),
  paused_at          timestamptz null,
  pause_reason       text null,
  version_cursor     bigint not null default 0,-- monotone, bumped on every state mutation
  created_at         timestamptz not null default now(),
  unique (instance_id, region_id, parent_token_id) -- one active token per (instance, region, parent) triple
);
create index on ums.workflow_instance_tokens (instance_id, status);
create index on ums.workflow_instance_tokens (join_group_id) where join_group_id is not null;
```

`workflow_instances.status` is generalised to an enumerated *aggregate*
status — `active | paused | completed | cancelled | failed |
compensating` — derived from token statuses on every commit (rule:
`compensating > failed > cancelled > paused > active > completed`).
The legacy single-state `workflow_instances.status` column at
`backend/app/workflows/models.py:33` is renamed to `aggregate_status` in
P-WD-1 with a backfill that creates one root token per existing
instance carrying its current Python-state name.

#### 17.1.2 DSL additions

```jsonc
"states": [
  { "name": "kyc_branch", "kind": "parallel_fork",
    "regions": [
      { "id": "kyc.party",     "initial_state": "verify_party"  },
      { "id": "kyc.documents", "initial_state": "collect_docs"  },
      { "id": "kyc.sanctions", "initial_state": "screen"        }
    ],
    "join": {
      "policy": "all",                 // all | n_of_m | first_success | first_terminal
      "n": null,                        // required when policy=n_of_m
      "to_state": "kyc_complete",
      "on_partial_failure": "compensate" // compensate | continue | fail
    }
  }
]
```

DSL also exposes `parallel_join` as a synthetic state (the engine creates
it implicitly from `join.to_state`); the validator rejects defs whose
`regions[].id` are not unique within a fork, or whose region states
appear in another region. `parallel_fork` may not be a `terminal` state.

#### 17.1.3 Concurrency policy

- One row in `workflow_instance_tokens` is the lock granule. Per-token
  optimistic concurrency: a transition reads the token with
  `SELECT ... FOR UPDATE` keyed by `id`, asserts `version_cursor` matches
  the cursor it planned against (see §17.2), and bumps it on commit.
- Sibling tokens in disjoint regions never contend for the same row.
- `join_group_id` is set by the fork at creation time; the join handler
  scans the group at every sibling commit and fires the join transition
  when its policy is satisfied. The scan runs in the *committing*
  transaction so a join either fires or does not — never half.
- `awaiting_compensation` blocks new transitions on that token only;
  sibling tokens may still progress unless `on_partial_failure="fail"`.

#### 17.1.4 Tests

- `tests/ci/test_wf_parallel_tokens.py::test_fork_creates_one_token_per_region`
- `tests/ci/test_wf_parallel_tokens.py::test_join_all_waits_for_all_siblings`
- `tests/ci/test_wf_parallel_tokens.py::test_join_n_of_m_completes_partial`
- `tests/ci/test_wf_parallel_tokens.py::test_partial_failure_compensates_only_failed_branch`
- `tests/ci/test_wf_parallel_tokens.py::test_aggregate_status_derives_from_tokens`

### 17.2 Two-phase fire(): plan → commit (closes C2)

The current single-shot `engine.transition()` at
`backend/app/workflows/engine.py:351-489` evaluates guards under a row
lock that is held across async lookups. The compiled-def runtime
replaces this with two phases:

#### 17.2.1 Plan phase (no row lock)

1. Snapshot the token: `SELECT id, current_state, version_cursor, ...`
   without `FOR UPDATE`. Capture `version_cursor` as `planned_cursor`.
2. Resolve the matching transition by `(state, event)` priority order.
3. Evaluate guards and `lookup_*` operators with no SQL row locks held.
   Each evaluation produces a deterministic record:
   ```jsonc
   {
     "expr_id": "guard:submit#0",
     "ast_hash": "sha256:…",
     "result": true,
     "evaluated_lookups": [
       { "kind": "lookup_party", "args": { "id": "…" },
         "result_hash": "sha256:…", "result_snapshot": { /* canonical projection */ },
         "permission_checked": "party.read", "principal": "user:abc",
         "evaluated_at": "2026-05-05T08:30:01Z" }
     ]
   }
   ```
4. Build a `TransitionPlan` carrying: target state, effects, lookups
   evaluated, planned_cursor, idempotency key, saga step list.

#### 17.2.2 Commit phase (under row lock)

1. `BEGIN; SELECT ... FROM workflow_instance_tokens WHERE id = :id FOR UPDATE`.
2. **Re-validate under lock**: assert `version_cursor == planned_cursor`.
   If not, abort with `STALE_PLAN`; caller retries with backoff (max 3 in
   the runtime path; orchestration tasks fall through to outbox retry).
3. Re-evaluate **only** the guards whose AST is flagged
   `requires_relock = true` (default false). The validator sets this
   flag during publish when the guard AST satisfies **either** of:
   (a) any `{ "var": "..." }` path that appears as a write-target in
   a sibling effect within the same transition (read-after-write
   hazard), or (b) any `lookup_workflow_output` call whose
   `workflow_key` equals the current def's key (self-read on live
   state). All other guards are trusted from the plan.
4. Execute effects inside the same transaction. Adapters
   (`app.<domain>.workflow_adapter.<verb>`) run here.
5. Bump `version_cursor`, write the `workflow_event` row with the full
   `evaluated_lookups[]` payload (see §17.3), enqueue outbox rows in
   the same TX.
6. `COMMIT`.

A guard that fails under lock is recorded as a rejected transition, the
token stays in its previous state, and an audit row is emitted.

Conflict ordering: a published def must not have two transitions with
the same `(from_state, event, priority)` tuple — enforced by
`validator.py` and tested by
`tests/ci/test_wf_validator.py::test_duplicate_priority_rejected`.

#### 17.2.3 Tests

- `tests/ci/test_wf_two_phase_fire.py::test_lookup_runs_without_row_lock`
- `tests/ci/test_wf_two_phase_fire.py::test_stale_plan_aborts_under_lock`
- `tests/ci/test_wf_two_phase_fire.py::test_relock_guard_reevaluated`
- `tests/ci/test_wf_two_phase_fire.py::test_concurrent_branches_do_not_serialize`

### 17.3 Replay determinism via persisted lookup snapshots (closes C3)

`workflow_events.payload` is extended:

```jsonc
{
  "evaluated_expressions": [
    { "expr_id": "guard:submit#0", "ast_hash": "…", "result": true,
      "evaluated_lookups": [ /* see 17.2 */ ] }
  ],
  "now_seed": "2026-05-05T08:30:01Z",
  "calendar_snapshot_id": "uuid",      // see 17.10
  "definition_version_id": "uuid",
  "external_event_id": "…"
}
```

`scripts/replay_workflow_event.py <event_id>` MUST:

1. Load the event row.
2. Construct an `EvaluationContext` whose lookup table is pre-seeded
   from `evaluated_lookups[]` — all `lookup_*` operators consult that
   table and never hit the DB.
3. Re-evaluate the AST and assert the result equals
   `evaluated_expressions[i].result`.
4. Exit non-zero on any divergence.

CI test
`tests/ci/test_wf_replay.py::test_replay_matches_recorded_outcome` runs
this for every `workflow_events` row produced by the parity fixture in
P-WD-5. Replay is documented as **decision-replay**, not
**world-replay**: domain rows may have changed since.

`evaluated_lookups[].result_snapshot` is the *canonical projection*
declared per-lookup in the catalog as `result_projection` (§17.6.1)
— the same field, same authority — not the raw row, so:
- PII fields not in the projection never enter the audit row;
- soft-deleted rows still replay because the snapshot was captured
  while the row was live.

### 17.4 Saga ledger and DLQ→compensation handoff (closes C4)

#### 17.4.1 Schema

```sql
ums.workflow_saga_steps (
  id                  uuid pk,
  instance_id         uuid not null fk → workflow_instances(id),
  token_id            uuid not null fk → workflow_instance_tokens(id),
  transition_event_id uuid not null fk → workflow_events(id),
  step_idx            int  not null,             -- order within the transition
  step_kind           text not null,             -- effect kind (create_entity, notify, …)
  status              text not null check (status in
                        ('pending','done','compensating','compensated','failed')),
  attempt             int  not null default 0,
  compensation_kind   text null,                 -- catalog-named compensation
  compensation_payload jsonb not null default '{}'::jsonb,
  compensation_order  text not null default 'strict_descending'
                        check (compensation_order in
                          ('strict_descending','strict_ascending','parallel')),
  outbox_row_id       uuid null,                 -- link to outbox row when dispatched
  last_error          text null,
  last_error_at       timestamptz null,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (transition_event_id, step_idx)
);
create index on ums.workflow_saga_steps (instance_id, status);
create index on ums.workflow_saga_steps (token_id, status);
```

#### 17.4.2 Lifecycle

| Event | Effect on ledger |
|---|---|
| Transition commits | One row per effect, status=`pending` for outbox effects, `done` for in-TX effects. |
| Outbox dispatch ok | Worker flips matching row to `done`. |
| Outbox row → `dead` (DLQ; existing path `backend/app/workers/outbox_worker.py:243`) | Worker flips row to `failed`, walks all earlier `done` rows in `transition_event_id` (descending `step_idx`), enqueues their `compensation_kind` to outbox marked `compensation=true`, and flips them to `compensating`. The token's status flips to `awaiting_compensation`. |
| Compensation outbox row ok | Row → `compensated`. When all sibling rows are `compensated|done|failed`, token returns to `current_state` *prior* to the failed transition (recorded on the saga row) and aggregate status is recomputed. |
| Compensation outbox row → `dead` | Row → `failed`. Token stays `awaiting_compensation`. Threshold alert `workflow.compensation_dlq` fires. Manual operator action required. |

#### 17.4.3 Block rule

Engine refuses to fire any transition on a token whose
`workflow_saga_steps` shows any row in
`('pending','compensating','failed')` whose `transition_event_id` ≠ the
incoming event. Implementation: `runtime_service.fire()` issues a
single guarded SELECT and aborts with `SAGA_PENDING`.

#### 17.4.4 Outbox handler interaction

- Existing `app.workers.outbox_worker.HANDLERS` adds `wf.saga.compensate`
  whose payload is `{ saga_step_id, compensation_kind, payload }`.
- Compensation handlers run **un-elevated** by default; see §17.7.
- `app.workers.compensation` (path
  `backend/app/workers/compensation.py`) gains a `wf.saga` adapter that
  reads the ledger and resolves the catalog's
  `entities.<name>.compensations.<kind>` to a Python callable.

#### 17.4.5 Tests

- `tests/ci/test_wf_saga.py::test_in_tx_effect_marks_done_on_commit`
- `tests/ci/test_wf_saga.py::test_outbox_dlq_walks_done_rows_descending`
- `tests/ci/test_wf_saga.py::test_pending_saga_blocks_new_transitions`
- `tests/ci/test_wf_saga.py::test_compensation_failure_holds_token`
- `tests/ci/test_wf_saga.py::test_aggregate_status_compensating_visible_in_api`

### 17.5 Idempotency keys and late-arriving events (closes C5)

#### 17.5.1 Schema

```sql
alter table ums.workflow_events
  add column external_event_id text not null;

create unique index workflow_events_extkey_uq
  on ums.workflow_events (instance_id, external_event_id);

create index workflow_events_extkey_tenant
  on ums.workflow_events (tenant_id, external_event_id);
```

The `external_event_id` is supplied by the caller as
`Idempotency-Key` HTTP header (or `event_id` for outbox-driven ingress).
Server-issued events (timers, sla, escalations) generate
`external_event_id = "engine:" || transition_id || ":" || token_id || ":" || version_cursor`.

#### 17.5.2 Server semantics

```
fire(instance_id, token_id, event, external_event_id, payload):
  attempt insert workflow_events(... external_event_id ...) within the
    commit phase TX (§17.2.2 step 5)
  if unique-violation:
    SELECT the existing row; return its outcome (200 + cached body)
  else proceed
```

Replay-on-same-key returns the original outcome verbatim (status code,
headers carrying audit hash, body). The endpoint is an idempotent
upsert by definition.

#### 17.5.3 Late-arrival policy

Three explicit cases, each with a reason code:

| Case | Detection | Policy | Audit reason |
|---|---|---|---|
| Token is in a terminal state | Plan phase reads `status in ('completed','cancelled','failed')` | Reject with HTTP 409, body `{ "code": "EVENT_ON_TERMINAL_TOKEN" }` | `wf.event.rejected.terminal` |
| Token is `awaiting_compensation` | Saga ledger guard | Reject 409 `{ "code": "EVENT_AWAITING_COMPENSATION" }` | `wf.event.rejected.compensating` |
| Out-of-order from a sequenced source (e.g. webhook with `source_seq`) | Compare to `pending_signals` last_seq | Stash in `pending_signals` until the predecessor arrives, `ttl=24h`, then drop with audit | `wf.event.deferred.out_of_order` / `wf.event.dropped.expired` |

`pending_signals` is the same table introduced in §17.10.

#### 17.5.4 Tests

- `tests/ci/test_wf_idempotency.py::test_duplicate_external_event_id_returns_cached`
- `tests/ci/test_wf_idempotency.py::test_unique_index_blocks_double_insert`
- `tests/ci/test_wf_idempotency.py::test_event_on_terminal_token_rejects`
- `tests/ci/test_wf_idempotency.py::test_out_of_order_stashed_then_drained`

### 17.6 Lookup-as-oracle defense (closes C6)

#### 17.6.1 Catalog declarations

Each `lookup_*` entry in `entities.json` (§15.2) gains:

```jsonc
"lookups": {
  "lookup_party": {
    "read_permission": "party.read",
    "result_projection": ["id","kyc_status","sanctions_flag","tenant_id"],
    "constant_time_miss_ms": 25,
    "rate_limit_per_tenant_per_minute": 600
  }
}
```

#### 17.6.2 Three-stage authorisation

1. **Publish-time**: validator walks the AST, collects every `lookup_*`
   call. Each must reference a catalog lookup whose `read_permission` is
   held by the *def author* (the user submitting publish), evaluated by
   `simulate_effective_access` for the tenant the def will be published
   into. Operator-shared defs are evaluated against the operator-tenant.
   When a tenant forks an operator-shared def (§19.2), the publish-time
   check re-runs against the *forking tenant's* principal grants before
   the fork is accepted. Failure rejects publish with `LOOKUP_PERMISSION_MISSING`.
2. **Plan-time** (per-fire): evaluator re-checks `read_permission`
   against the *runtime caller* before issuing the lookup. Failure
   surfaces as a guard-evaluation failure, never as a silent drop.
3. **Result-time**: evaluator clamps the row to `result_projection`
   before exposing it to the AST.

Two principals — *def author* and *runtime caller* — are recorded
per-lookup in `evaluated_lookups[].principal_design` and
`.principal_runtime`.

#### 17.6.3 Rate limiting + constant-time miss

- A per-tenant token-bucket sits in front of every `lookup_*` call
  (`rate_limit_per_tenant_per_minute`). Bucket key:
  `(tenant_id, lookup_kind)`. Implemented in
  `app.workflows_v2.expr.lookup_runtime.LookupGate` using existing
  Redis bucket helpers.
- Miss path waits until `constant_time_miss_ms` elapsed since the
  request started (default 25ms) before returning, defeating timing
  side channels. Hits return on natural latency; an additive jitter
  (uniform 0–10ms) is applied so hit/miss distributions overlap.
- `lookup_setting` is restricted to a static allowlist
  (`workflow.allowed_setting_keys` setting, default empty) — keys not
  on the list reject with `LOOKUP_SETTING_FORBIDDEN`.
- `lookup_workflow_output` requires the *target* workflow's
  `read_permission` held by both author and caller.
- Hard cap: 16 lookups per evaluation, 1 lookup-result per AST node
  (memoised). Exceeded → `LOOKUP_BUDGET_EXCEEDED`.

#### 17.6.4 Audit

Every lookup writes a row to `audit_events` with
`subject_kind="workflow_lookup"`, `payload={lookup_kind,args_hash,
result_hash,principal_design,principal_runtime,permission}`. This is
in addition to the inline `evaluated_lookups[]` payload — the audit
row is hash-chained.

#### 17.6.5 Tests

- `tests/ci/test_wf_lookup_oracle.py::test_publish_blocks_unauthorised_lookup`
- `tests/ci/test_wf_lookup_oracle.py::test_runtime_blocks_caller_without_permission`
- `tests/ci/test_wf_lookup_oracle.py::test_constant_time_miss_within_jitter`
- `tests/ci/test_wf_lookup_oracle.py::test_rate_limit_per_tenant`
- `tests/ci/test_wf_lookup_oracle.py::test_setting_lookup_allowlist_enforced`
- `tests/ci/test_wf_lookup_oracle.py::test_audit_row_emitted_per_lookup`

### 17.7 Elevation audit & tamper resistance (closes C7)

#### 17.7.1 Hard rules

1. **Compensation runs un-elevated.** The saga worker explicitly clears
   `app.elevated` before invoking any compensation step. An elevated
   compensation requires a fresh, per-step `elevation_justification`
   recorded in the elevation log (below) and approved by a separate
   principal (4-eyes). Implementation lives in
   `backend/app/workers/compensation.py`.
2. **Audit-row writes are forbidden inside an elevated transition.**
   The `app.audit.service.record` entry-point (path
   `backend/app/audit/service.py`) gains a precondition: when the
   active session has `app.elevated=true`, `record()` raises
   `AuditElevationDenied` unless the `subject_kind` is on a static
   allowlist (`workflow_elevation_log`, `secret_access`). The change
   is exercised by `tests/ci/test_audit_elevation_block.py`.
3. **Operator-shared def changes** are recorded under
   `subject_kind="workflow_definition_shared"`, distinct from per-tenant
   def changes.

#### 17.7.2 Schema — HSM-signed elevation log

```sql
ums.workflow_elevation_log (
  id                    uuid pk,
  instance_id           uuid not null,
  token_id              uuid null,
  transition_event_id   uuid null,
  elevation_reason      text not null,           -- enum: cross_tenant_lookup, operator_compensation, …
  justification         text not null,
  actor_user_id         uuid not null,           -- runtime caller
  approver_user_id      uuid null,               -- 4-eyes for compensation case
  approved_at           timestamptz null,
  signature             bytea not null,          -- HSM signature over canonical row
  signature_key_id      text not null,           -- KMS / HSM key reference
  prev_signature        bytea null,              -- chain
  created_at            timestamptz not null default now()
);
create index on ums.workflow_elevation_log (instance_id);
```

The signature covers `(id, instance_id, token_id, transition_event_id,
elevation_reason, justification, actor_user_id, approver_user_id,
approved_at, prev_signature, created_at)` canonical-JSON. The signing
call is `app.platform.signing.sign_payload(payload: bytes) -> bytes`
(path `backend/app/platform/signing.py`). That function already accepts
arbitrary `bytes` (it wraps KMS `sign`); the flag/settings callers pass
JSON-serialised dicts — the elevation log does the same. Rotation
follows the existing HMAC rotation runbook. P-WD-1 must add an
integration test confirming `sign_payload` round-trips a
`workflow_elevation_log`-shaped canonical-JSON payload.

#### 17.7.3 Per-elevation justification

Engine refuses to set `app.elevated=true` for a transition that does
not declare:

```jsonc
"effects": [{
  "kind": "elevate",
  "reason": "cross_tenant_lookup",
  "justification_expr": { "var": "context.elevation_reason" }
}]
```

The justification expression must resolve to a non-empty string of
≥10 chars at fire-time. Empty / static / literal "elevation" strings
are rejected by the validator.

#### 17.7.4 Tests

- `tests/ci/test_wf_elevation.py::test_audit_record_blocked_when_elevated`
- `tests/ci/test_wf_elevation.py::test_compensation_runs_unelevated`
- `tests/ci/test_wf_elevation.py::test_elevation_signature_verifies`
- `tests/ci/test_wf_elevation.py::test_missing_justification_rejects`

### 17.8 In-flight migration (closes C8)

#### 17.8.1 Migration DSL

```jsonc
{
  "migration_id": "claim.standard:1.4.0->1.5.0",
  "from_version_id": "uuid",
  "to_version_id": "uuid",
  "ops": [
    { "op": "rename_state", "from": "triage", "to": "triage_v2" },
    { "op": "add_field", "path": "context.triage.priority", "default": "normal" },
    // NOTE: "default" in add_field MUST be a JSON literal (string, number, bool, null,
    // or a constant array/object). Expressions are forbidden — use set_default for those.
    { "op": "drop_state", "name": "manual_review_legacy",
      "remap_active_tokens_to": "triage_v2" },
    { "op": "remap_assignee", "from_role": "claims_handler", "to_role": "claims_specialist" },
    { "op": "set_default", "path": "context.flags.kyc_v2_enabled", "value": true },
    { "op": "drop_field", "path": "context.legacy.misc",
      "audit_kind": "wf.migration.field_dropped" }
  ]
}
```

The migration document is itself a versioned, audited artefact stored
in `workflow_definition_migrations`:

```sql
ums.workflow_definition_migrations (
  id                uuid pk,
  from_version_id   uuid not null fk → workflow_definition_versions(id),
  to_version_id     uuid not null fk → workflow_definition_versions(id),
  ops               jsonb not null,
  spec_hash         text not null,
  created_at        timestamptz not null default now(),
  created_by_user_id uuid not null,
  approved_at       timestamptz null,
  approved_by_user_id uuid null,
  unique (from_version_id, to_version_id)
);
```

#### 17.8.2 Per-instance runner

```sql
ums.workflow_instance_quarantine (
  id              uuid pk,
  instance_id     uuid not null fk → workflow_instances(id),
  token_id        uuid null fk → workflow_instance_tokens(id),
  migration_id    uuid not null fk → workflow_definition_migrations(id),
  status          text not null check (status in
                    ('queued','running','succeeded','failed','manual_fix')),
  attempt         int  not null default 0,
  last_error      text null,
  last_error_at   timestamptz null,
  context_before  jsonb null,
  context_after   jsonb null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (instance_id, migration_id)
);
```

Runtime semantics:

- Migrations run **lazily on next event** by default. The plan phase
  detects `instance.definition_version_id != latest_target` and the
  migration runner executes inside the same TX as the commit phase,
  *before* the transition.
- A batch runner (`scripts/run_workflow_migration.py --migration-id <id>
  --batch-size 200`) exists for operator-driven full-fleet migrations.
- Failure modes:
  - `op` raises → quarantine row `status=failed`, instance pinned to
    old version, alert fires.
  - 3 retries exhaust → `manual_fix`, runbook page in
    `docs/runbooks/workflow-migration.md`.
- Tokens are migrated atomically: per-instance lock is taken,
  every token rewritten, then `definition_version_id` flipped on the
  instance row.

#### 17.8.3 Adapter retention rule

CI guard `backend/scripts/check_workflow_adapter_retention.sh` walks
every non-archived `workflow_definition_versions` row and asserts every
catalog adapter referenced by the def's effects exists in the current
codebase. Removing an adapter referenced by a non-archived def-version
fails CI.

#### 17.8.4 Tests

- `tests/ci/test_wf_migration.py::test_lazy_migration_on_next_event`
- `tests/ci/test_wf_migration.py::test_batch_runner_progresses_in_chunks`
- `tests/ci/test_wf_migration.py::test_failed_op_quarantines_instance`
- `tests/ci/test_wf_migration.py::test_manual_fix_runbook_link_present`
- `tests/ci/test_wf_adapter_retention.py::test_referenced_adapters_present`

### 17.9 Business calendars and DST (closes M1)

#### 17.9.1 Schema

```sql
ums.business_calendars (
  id            uuid pk,
  tenant_id     uuid not null,                 -- nullable would allow operator-shared; we fork instead
  region_code   text not null,                 -- "GLOBAL", "KE", "KE-NBO", …
  tz            text not null,                 -- IANA tz, e.g., "Africa/Nairobi"
  holidays      jsonb not null default '[]'::jsonb,  -- [{date, label, kind}]
  work_hours    jsonb not null default '{}'::jsonb,  -- per weekday {start,end} in tz local time
  effective_from date not null,
  effective_to   date null,
  spec_hash     text not null,
  version_cursor bigint not null default 0,     -- bumped on every update; used as snapshot key
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, region_code, effective_from)
);
create index on ums.business_calendars (tenant_id, region_code);
```

#### 17.9.2 Resolution rule per def

```jsonc
"calendar_resolution": {
  "rule": "instance.context.region",      // tenant | tenant+region | instance.context.region
  "context_path": "context.party.region", // when rule=instance.context.region
  "fallback_region": "GLOBAL"
}
```

The compiler resolves a `calendar_id` per transition and pins it as
`workflow_events.payload.calendar_snapshot_id`; the snapshot is the
`(calendar_id, version_cursor)` pair, ensuring date math reproduces on
replay even if the operator edits the calendar later.

`add_business_days`, `is_business_day`, `add_money` etc. all take an
implicit `calendar` handle. Wall-clock deadlines (`legal filing`) opt
out by setting `pause_aware: false` and `calendar: "wall_clock"`.

DST: every deadline stores `(due_at_utc, source_tz, source_local_at)`.
Pause/resume math operates on `due_at_utc - paused_seconds`; the
displayed deadline re-formats `source_local_at` through the
`source_tz` zoneinfo so DST shifts are honoured.

#### 17.9.3 Tests

- `tests/ci/test_wf_calendar.py::test_business_day_skips_holiday`
- `tests/ci/test_wf_calendar.py::test_deadline_dst_spring_forward`
- `tests/ci/test_wf_calendar.py::test_calendar_snapshot_pinned_on_event`
- `tests/ci/test_wf_calendar.py::test_per_tenant_per_region_override_resolves`

### 17.10 Signal correlation and pending signals (closes M3)

#### 17.10.1 Schema

```sql
ums.pending_signals (
  id             uuid pk,
  tenant_id      uuid not null,
  instance_id    uuid not null fk → workflow_instances(id),
  token_id       uuid null fk → workflow_instance_tokens(id),
  signal_kind    text not null,                 -- "kyc.completed", "ext.ack", …
  dedup_key      text not null,                 -- caller-supplied or derived
  correlation_key text null,                    -- e.g. context.party_id
  source_seq     bigint null,                   -- for out-of-order detection
  payload        jsonb not null default '{}'::jsonb,
  expires_at     timestamptz not null,
  created_at     timestamptz not null default now(),
  unique (instance_id, dedup_key)
);
create index on ums.pending_signals (signal_kind, correlation_key);
create index on ums.pending_signals (expires_at);
```

#### 17.10.2 DSL

```jsonc
{ "name": "await_kyc",
  "kind": "signal_wait",
  "signal": "kyc.completed",
  "correlation": { "expr": { "var": "context.party_id" } },
  "expected_count": 1,
  "timeout_seconds": 86400,
  "on_timeout_event": "kyc.timed_out"
}
```

#### 17.10.3 Runtime

- Inbound signal endpoint: `POST /api/workflows/signals` carrying
  `{ signal_kind, dedup_key, correlation_key, source_seq?, payload }`.
- Insert into `pending_signals`. Unique-violation on `(instance_id,
  dedup_key)` is the idempotency guarantee.
- A correlator job (existing scheduler tick) finds tokens in
  `signal_wait` whose `correlation_key` and `signal` match and whose
  `received_count >= expected_count`, then fires the signal as a
  transition event. Out-of-order signals stay in the table until the
  correlator promotes them in `source_seq` order.
- Timeout: a scheduled job fires `on_timeout_event` for tokens whose
  `signal_wait.deadline` passed.

#### 17.10.4 Tests

- `tests/ci/test_wf_signals.py::test_signal_dedup_unique_index`
- `tests/ci/test_wf_signals.py::test_correlator_promotes_when_count_met`
- `tests/ci/test_wf_signals.py::test_out_of_order_signals_buffered`
- `tests/ci/test_wf_signals.py::test_timeout_fires_on_timeout_event`

### 17.11 Sub-workflows (closes M4)

#### 17.11.1 Schema additions

```sql
alter table ums.workflow_instances
  add column parent_instance_id uuid null fk → workflow_instances(id),
  add column parent_token_id    uuid null fk → workflow_instance_tokens(id),
  add column correlation_id     text null,           -- opaque key parent uses to map returns
  add column nesting_depth      int  not null default 0;

create index on ums.workflow_instances (parent_instance_id);
```

`nesting_depth` is enforced ≤ 5 (configurable
`workflow.runtime.max_nesting_depth`). Exceeded → start fails with
`SUBWORKFLOW_DEPTH_EXCEEDED`.

#### 17.11.2 Start / return semantics

- Effect kind `start_subworkflow` on a transition:
  ```jsonc
  { "kind": "start_subworkflow",
    "def_key": "kyc.standard",
    "input_map": { "party_id": { "var": "context.party_id" } },
    "correlation_id": "kyc.party",
    "on_complete_event": "kyc.done",
    "on_failure_event":  "kyc.failed",
    "wait": true }                          // true = parent token blocks until child terminal
  ```
- When `wait=true`, the parent token enters an implicit `signal_wait`
  on `signal_kind="subworkflow.return"`,
  `correlation_key=correlation_id`, `expected_count=1`. Child terminal
  publishes the corresponding signal carrying its `output_map` payload.
- Multi-instance pattern: emit N children at once with distinct
  `correlation_id`s; parent declares
  `expected_count=N, signal_kind="subworkflow.return"` and a join
  policy (all / n_of_m).

#### 17.11.3 Static cycle detection

The validator builds a directed graph over `def_key` references from
every `start_subworkflow` effect across all published defs visible to
the tenant. A cycle A → B → A causes publish to fail with
`SUBWORKFLOW_CYCLE_DETECTED` listing the cycle path. Detection uses
DFS with a visited-set; runtime `nesting_depth ≤ 5` is the defence of
last resort for cycles that evade the static check (e.g., dynamically
resolved `def_key` expressions — these are disallowed: `def_key` must
be a string literal, enforced by the validator). Tests:

- `tests/ci/test_wf_validator.py::test_subworkflow_cycle_rejected`
- `tests/ci/test_wf_validator.py::test_dynamic_def_key_rejected`

#### 17.11.4 Tests

- `tests/ci/test_wf_subworkflow.py::test_parent_blocks_until_child_returns`
- `tests/ci/test_wf_subworkflow.py::test_max_nesting_enforced`
- `tests/ci/test_wf_subworkflow.py::test_multi_instance_join_all`

### 17.12 Findings traceability matrix

| Finding | Section | Tables added | Tests added |
|---|---|---|---|
| C1 parallel regions | 17.1 | `workflow_instance_tokens` | test_wf_parallel_tokens |
| C2 lock-vs-lookup | 17.2 | (none — algorithm) | test_wf_two_phase_fire |
| C3 replay determinism | 17.3 | (event payload) | test_wf_replay |
| C4 saga ledger | 17.4 | `workflow_saga_steps` | test_wf_saga |
| C5 idempotency | 17.5 | `workflow_events.external_event_id` | test_wf_idempotency |
| C6 lookup oracle | 17.6 | (catalog ext) | test_wf_lookup_oracle |
| C7 elevation audit | 17.7 | `workflow_elevation_log` | test_wf_elevation, test_audit_elevation_block |
| C8 in-flight migration | 17.8 | `workflow_definition_migrations`, `workflow_instance_quarantine` | test_wf_migration, test_wf_adapter_retention |
| M1 calendars | 17.9 | `business_calendars` | test_wf_calendar |
| M3 signal correlation | 17.10 | `pending_signals` | test_wf_signals |
| M4 sub-workflows | 17.11 | (instance ext) | test_wf_subworkflow |

### 17.13 Phasing impact

P-WD-1 absorbs the new tables (`workflow_instance_tokens`,
`workflow_saga_steps`, `workflow_elevation_log`,
`workflow_definition_migrations`, `workflow_instance_quarantine`,
`business_calendars`, `pending_signals`) and the
`workflow_events.external_event_id` column with its unique index. The
`alembic` migration also renames `workflow_instances.status` →
`aggregate_status` and backfills root tokens.

P-WD-2 lands the two-phase fire path, lookup catalog extensions, and
elevation log writes.

P-WD-3 introduces the validator gates that reject duplicate-priority
transitions, missing publish-time lookup permissions, and
unjustified `elevate` effects.

P-WD-5 adds the saga DLQ→compensation handoff, calendar snapshotting,
signal correlator job, and sub-workflow start/return.

## 18. Iteration 1 Changelog

| Iteration | Verdict | Key changes |
|---|---|---|
| 0 (initial) | REJECT | — |
| 1 | ACCEPT-WITH-RESERVATIONS | §17 added: C1–C8, M1/M3/M4 closed with tables + tests. R-1–R-8 deferred. |
| 2 | See `docs/workflow-ed-arch-review.md` | R-1–R-8 resolved inline (§17.2, §17.3, §17.4, §17.6, §17.7, §17.8, §17.9, §17.11). M2/M5–M15 deferred. |

All P0/CRITICAL (C1–C8) and brief-nominated P1/MAJOR (M1, M3, M4)
findings are closed. Remaining MAJORs (M2, M5–M15) are deferred to
phase notepads and later iterations. See §17.12 traceability matrix.

## 20. Deferred MAJOR Findings — Closed (iteration 3)

All M-findings closed below. Format: decision + schema/algorithm + tests.

### 20.1 M2 — Pause-aware timers

Each timer DSL node declares `pause_aware: true` (default) or `false`.
At pause, engine records `token.paused_at`. At resume, adds
`(resume_at − paused_at)` to `due_at_utc` for every `pause_aware=true`
timer on the token. `pause_aware=false` timers (wall-clock legal
cutoffs) are untouched. Validator rejects `{ pause_aware: false,
idle_timeout: ... }` (contradictory). DSL:

```jsonc
"sla": { "breach_seconds": 14400, "warn_pct": 80, "pause_aware": true },
"idle_timeout": { "seconds": 3600, "on_timeout_event": "idle.escalate", "pause_aware": true },
"legal_deadline": { "due_at_expr": { "add_days": [...] }, "pause_aware": false, "on_breach_event": "legal.missed" }
```

Tests: `test_wf_timer::test_sla_clock_freezes_on_pause`,
`test_wf_timer::test_wall_clock_ignores_pause`,
`test_wf_validator::test_non_pause_aware_idle_rejected`.

### 20.2 M5 — Form-spec version drift mid-edit

Policy: **accept submitted version, audit it**. No server rejection on
version drift. `workflow_events` gains `form_spec_version text null`
(null for non-form transitions). Frontend submits include
`form_spec_version`; server validates form data against *that* version's
schema. Per-field `added_in_version` marker in the form-spec schema
lets `FormRenderer` skip unknown fields rather than error on old renders.

```sql
alter table ums.workflow_events add column form_spec_version text null;
```

Tests: `test_wf_form_drift::test_old_version_accepted_and_audited`,
`test_wf_form_drift::test_added_in_version_field_skipped`.

### 20.3 M6 — Editor concurrent-edit (normative)

**Intra-tenant:** optimistic lock via `parent_version_hash`; 409 shows
inline diff with *my/server/merge* choice. No CRDT planned.

**Operator-shared def:** fork-on-edit is **mandatory** (§19.2 answer:
fork, not layer). A tenant PATCH against an operator def auto-forks a
private `workflow_definitions` row; `parent_version_id` preserves
lineage. Tenant cannot un-fork; archives fork to re-inherit.

Tests: `test_wf_editor::test_409_on_hash_mismatch`,
`test_wf_editor::test_operator_patch_forks_copy`,
`test_wf_editor::test_fork_lineage_in_parent_version_id`.

### 20.4 M7 — Editor performance budgets

Enforced by `tests/perf/test_wf_editor_perf.py` (CI: 8-core/16 GB):

| Metric | Budget p95 | Adaptive trigger |
|---|---|---|
| 500-node react-flow cold render | 400 ms | auto-layout off above 300 nodes |
| 500-node react-flow warm render | 100 ms | minimap off above 500 nodes |
| Monaco load (lazy) | 800 ms | first expression-click only |
| 100-event timeline API | 100 ms | read-session |
| 10k instance list page 1 | 300 ms | cursor pagination |
| Validator lint 500-state def | 200 ms | server-side sync |

Monaco locked (already in admin app); codemirror not adopted.

Tests: `test_wf_editor_perf::test_500_state_render_budget`,
`test_wf_editor_perf::test_timeline_budget`.

### 20.5 M8 — Catalog default-deny

`build_workflow_catalog.py` includes a column **only** if its model
declares `WorkflowExposed` and lists it in `workflow_projection`:

```python
# backend/app/workflows_v2/catalog/mixins.py
class WorkflowExposed:
    workflow_exposed: ClassVar[bool] = True
    workflow_projection: ClassVar[list[str]] = []   # explicit allowlist
```

CI guards: `check_catalog_drift.sh` (def references absent column →
fail), `check_no_pii_in_catalog.sh` (PII column in projection without
`pii_allowed=True` annotation in `backend/app/core/pii_registry.py` →
fail).

Tests: `test_wf_catalog::test_unlisted_column_excluded`,
`test_wf_catalog::test_pii_blocked_without_annotation`.

### 20.6 M9 — Webhook signing envelope

Signed envelope for every `wf.webhook` outbox dispatch:
`HMAC-SHA256(subscriber_secret, id + "." + timestamp + "." + body_sha256)`.
Subscribers verify: timestamp within ±5 min, body hash matches, HMAC
valid, `id` not in 10-min replay cache. Key rotation: new secret
generated, old valid 24 h, handler dual-signs during overlap
(two `X-Workflow-Signature` headers).

Tests: `test_wf_webhook::test_hmac_verifies`,
`test_wf_webhook::test_replay_rejected`,
`test_wf_webhook::test_dual_sign_rotation`.

### 20.7 M10 — Why-stuck typed diagnosis

`GET /api/workflows/instances/{id}/why-stuck` →
`diagnosis: [{cause, detail, paging_policy, suggested_action}]`.

Cause enum: `gate_blocked | adapter_down | outbox_depth |
threshold_hold | awaiting_signal | awaiting_compensation`.
Paging policy per cause: `gate_blocked` → `assignee`;
`adapter_down | outbox_depth | threshold_hold` → `on_call`/`ops`;
`awaiting_*` → `none`. Implementation: `backend/app/workflows_v2/diagnosis.py`.
Result written into operational-task `note` (§12.11).

Tests: `test_wf_diagnosis::test_gate_blocked_detail`,
`test_wf_diagnosis::test_awaiting_compensation_cause`.

### 20.8 M11 — Permission catalog as DB table

```sql
ums.permission_catalog (
  name               text pk,
  description        text not null,
  deprecated_aliases jsonb not null default '[]'::jsonb,
  deprecated_at      timestamptz null,
  created_at         timestamptz not null default now()
);
```

Seeded idempotently from `backend/app/workflows_v2/permissions_seed.py`.
Validator rejects gate permissions absent from catalog. Deprecated
aliases resolve transparently (old defs keep working). CI guard
`check_permission_catalog_drift.sh` fails if any route permission or
gate permission in a committed def is absent from the seed.

Tests: `test_wf_permissions::test_unknown_permission_rejected`,
`test_wf_permissions::test_deprecated_alias_resolves`.

### 20.9 M13 — Instance snapshots

```sql
ums.workflow_instance_snapshots (
  id           uuid pk,
  instance_id  uuid not null fk → workflow_instances(id),
  token_id     uuid not null fk → workflow_instance_tokens(id),
  at_event_seq bigint not null,
  context      jsonb not null,
  token_state  jsonb not null,
  created_at   timestamptz not null default now(),
  unique (instance_id, token_id, at_event_seq)
);
create index on ums.workflow_instance_snapshots (instance_id, at_event_seq desc);
```

`workflow_events` gains `seq bigint generated always as identity`.
Snapshot written in commit TX when `event_count % snapshot_interval == 0`
(default 100, configurable `workflow.runtime.snapshot_interval`).
Rebuild = latest snapshot ≤ target seq + tail replay. Worst-case depth:
`snapshot_interval` events.

Tests: `test_wf_snapshot::test_written_every_100_events`,
`test_wf_snapshot::test_rebuild_uses_snapshot`,
`test_wf_snapshot::test_depth_bounded`.

### 20.10 M14 — WebSocket backpressure and gap recovery

Limits: 50 connections/tenant (`workflow.ws.max_connections_per_tenant`),
10 subscribers/instance, 5 s send timeout. On connect, client sends
`{ "last_event_id": "..." }`; server replays events with
`seq > resolved_seq` before live streaming. Auth refresh: WS handler
checks cookie every 30 s; expired → sends `{ "type": "auth_expired" }`,
closes 4001; client re-auths then reconnects with exponential back-off
(1 s → 60 s cap, ±jitter). Reconnect logic in
`frontend/src/lib/workflow-ws.ts`.

Tests: `test_wf_ws::test_tenant_connection_cap`,
`test_wf_ws::test_gap_recovery_replays`,
`test_wf_ws::test_auth_expired_close`.

### 20.11 M15 — GDPR right-to-erasure

Policy: **redact PII values in-place, preserve chain structure**.

On erasure of `data_subject_id`: (1) find all instances via
`workflow_instances.subject_id`; (2) overwrite PII-path values in
`workflow_events.payload` with `"[REDACTED]"` — hash chain is NOT
recomputed (broken chain entries signal redaction to verifiers, not
tampering); (3) redact same paths in
`workflow_instance_snapshots.context`; (4) write to erasure log.

PII paths declared per-entity: `"pii_paths": ["context.intake.name", ...]`.

```sql
ums.workflow_gdpr_erasure_log (
  id               uuid pk,
  data_subject_id  uuid not null,
  tenant_id        uuid not null,
  instance_ids     uuid[] not null,
  redaction_key_id text not null,
  redacted_at      timestamptz not null default now(),
  requested_by     uuid not null
);
create index on ums.workflow_gdpr_erasure_log (data_subject_id, tenant_id);
```

Tests: `test_wf_gdpr::test_pii_redacted_non_pii_preserved`,
`test_wf_gdpr::test_broken_chain_signals_redaction`,
`test_wf_gdpr::test_erasure_log_written`.

### 20.12 Traceability

| Finding | §20 sub | Schema / algorithm | Tests |
|---|---|---|---|
| M2 timer pause | 20.1 | DSL `pause_aware` | test_wf_timer |
| M5 form drift | 20.2 | `workflow_events.form_spec_version` | test_wf_form_drift |
| M6 concurrency | 20.3 | fork-on-edit normative | test_wf_editor |
| M7 perf budgets | 20.4 | CI benchmark table | test_wf_editor_perf |
| M8 catalog deny | 20.5 | `WorkflowExposed` mixin + CI guards | test_wf_catalog |
| M9 webhook sign | 20.6 | HMAC envelope + rotation | test_wf_webhook |
| M10 why-stuck | 20.7 | typed cause enum + paging policy | test_wf_diagnosis |
| M11 perm catalog | 20.8 | `permission_catalog` table | test_wf_permissions |
| M13 snapshots | 20.9 | `workflow_instance_snapshots` + `events.seq` | test_wf_snapshot |
| M14 WS | 20.10 | limits + gap recovery + auth refresh | test_wf_ws |
| M15 GDPR | 20.11 | in-place redaction + `workflow_gdpr_erasure_log` | test_wf_gdpr |

## 19. Open Questions

1. **Gate predicate language.** Restricted DSL (jq-like) vs full JSON-Logic
   vs registered named evaluators only? Recommend: registered evaluators
   for permission/authority/document gates, plus a *narrow* expression
   language (comparison + boolean + array `any/all`) for simple guards.
2. **Per-tenant fork model.** When a tenant edits an operator-shared def,
   does it fork into a tenant-private copy, or layer overrides on top?
   Recommend: fork — simpler to reason about, no transitive override hell.
3. **Form portal access.** Public-portal forms imply unauthenticated
   render; do we expose tokenised one-shot URLs or require Keycloak login?
   Likely tokenised URLs with HMAC + expiry, similar to acknowledgement
   links.
4. **i18n storage.** Embed translations inside the spec, or external
   message catalog keyed by `form_spec_id.field_id.label`? Recommend:
   external catalog — keeps spec diff readable.
5. **Definition portability.** Do we support exporting a published def
   for review by external auditors? Recommend: yes — signed JSON bundle
   including hash + audit trail.
6. **Engine concurrency.** Compiled defs hold compiled gate evaluators in
   process memory. Cache invalidation on publish: pub/sub via Redis or
   DB notify? Recommend: PostgreSQL `LISTEN/NOTIFY` (already in the
   stack), with worker-side TTL fallback.
