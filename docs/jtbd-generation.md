# JTBD application generation

How a JTBD bundle becomes a runnable FastAPI + Next.js application.

This document describes the deterministic transform pipeline implemented in [`flowforge_cli.jtbd`](../python/flowforge-cli/src/flowforge_cli/jtbd/). It complements [`jtbd-grammar.md`](jtbd-grammar.md) (the input format) and [`flowforge-handbook.md`](flowforge-handbook.md) (the runtime architecture). If you only want to *use* the generator, the relevant CLI surface is `flowforge new`, `flowforge add-jtbd`, `flowforge jtbd-generate`, and `flowforge regen-catalog`.

The generator is intentionally simple. There is no LLM call anywhere in the path. There is no plugin system at the generator layer. Everything is pure Python plus Jinja2 with `StrictUndefined`. Two invocations against the same bundle produce byte-identical output, and CI enforces this on every PR.

---

## 1. The contract

**Input.** A JTBD bundle (`jtbd-bundle.json` or `.yaml`) that validates against [`jtbd-1.0.schema.json`](../python/flowforge-core/src/flowforge/dsl/schema/jtbd-1.0.schema.json) and the canonical Pydantic v2 models in [`flowforge_jtbd.dsl.spec`](../python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py). The bundle describes *what* the application should do (jobs, actors, fields, edge cases, approvals); it never declares states, transitions, table names, or routes.

**Output.** A list of `GeneratedFile(path, content)` records, sorted by path. The CLI writes them to disk under `--out`. For a 1-JTBD bundle the output is ~18 files; an 8-JTBD bundle is ~110 files. Output is byte-identical across runs of the same generator version.

**Guarantees.**

- **Deterministic.** No timestamps, no random ids, no dict-iteration leakage. Alembic revisions are derived from `sha256(package + jtbd_id)` so they are stable across machines.
- **Schema-checked.** Parse errors fail loudly at the boundary. The generator never silently produces a half-valid file.
- **Validated end-to-end.** Every emitted `workflow_def.json` round-trips through `flowforge.compiler.validate()` in the generator tests. Every emitted `form_spec.json` round-trips through the form-spec schema. Every emitted Python file is syntax-checked.
- **Diffable.** Two runs produce the same bytes, so `git diff` over `examples/<example>/generated/` reflects only intentional bundle changes.

**Non-goals.**

- The generator is **not a no-code platform**. It produces a skeleton that a developer extends. Form rendering, business validation beyond the schema, external integrations, and detailed UI all stay in host code.
- The generator does **not** produce a complete state machine for every domain. The synthesised workflow has the obvious shape (`intake → review → done` plus edge-case branches). Authors who need parallel forks, signal waits, sub-workflows, or timer states either extend the bundle or edit `definition.json` directly post-generation (the Designer is built for this).

---

## 2. Pipeline stages

The pipeline is defined in [`flowforge_cli/jtbd/pipeline.py`](../python/flowforge-cli/src/flowforge_cli/jtbd/pipeline.py) and runs in five stages.

```
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────┐
│  parse   ├──►│ normalize├──►│ 15 generators├──►│  dedup +   ├──►│  write   │
│ (schema) │   │ (synth)  │   │  (templates) │   │  sort path │   │ to disk  │
└──────────┘   └──────────┘   └──────────────┘   └────────────┘   └──────────┘
```

### 2.1 Parse

`flowforge_cli.jtbd.parse.parse_bundle(raw)` runs the canonical `JtbdBundle.model_validate()` (`extra='forbid'`) and raises `JTBDParseError` on any structural violation. The error path includes the dotted path to the offending field (`jtbds[0].data_capture[3].kind: ...`).

This stage catches:

- Unknown keys (typo guard).
- Missing required fields (`actor`, `situation`, `motivation`, `outcome`, at least one `success_criteria`).
- Out-of-enum values (`kind`, `policy`, `trigger`, `channel`, etc.).
- Object-local validators (C-pii, C-branch, C-approval-n, C-approval-tier — see [`jtbd-grammar.md` §3.1](jtbd-grammar.md)).
- Bundle invariants (unique JTBD ids, at least one JTBD per bundle).

What it does **not** catch: cross-JTBD semantics like dependency cycles, lifecycle completeness, actor-consistency conflicts. Those belong to `flowforge jtbd lint` and run separately. See [`jtbd-grammar.md` §3.2](jtbd-grammar.md) for the full lint rule list.

### 2.2 Normalize

`flowforge_cli.jtbd.normalize.normalize(raw)` converts the parsed bundle into a `NormalizedBundle` view-model. This stage is where the **declarative-to-state-machine synthesis** happens. The output is a frozen dataclass tree (`NormalizedBundle → NormalizedProject + NormalizedJTBD[] + cross-bundle aggregates`) that every generator consumes.

Per JTBD, the normalizer derives:

| Field | Derivation |
|---|---|
| `class_name` | `pascal_case(id)` — `claim_intake` → `ClaimIntake` |
| `table_name` | `snake_case(id)` |
| `module_name` | `snake_case(id)` |
| `url_segment` | `kebab_case(id)` — `claim_intake` → `claim-intake` |
| `states` | Synthesised from approvals + edge_cases (rules below). |
| `transitions` | Synthesised from synthesised states (rules below). |
| `initial_state` | First state in the synthesised list (`intake`). |
| `fields` | Each `data_capture[i]` augmented with `sa_type`, `sql_type`, `ts_component`. |
| `permissions` | Per-JTBD permission set (rules below). |
| `audit_topics` | Per-JTBD audit-event topic strings (rules below). |
| `sla_warn_pct`, `sla_breach_seconds` | Pulled from `sla` if present. |

Cross-bundle aggregates (computed once per bundle):

| Field | Derivation |
|---|---|
| `all_permissions` | Union of every JTBD's permissions, plus `shared.permissions`, sorted, deduplicated. |
| `all_audit_topics` | Union of every JTBD's audit topics, sorted, deduplicated. |
| `all_notifications` | Union deduped on `(trigger, channel, audience)`, sorted by the same key. |

The synthesis rules are pure functions in [`flowforge_cli/jtbd/transforms.py`](../python/flowforge-cli/src/flowforge_cli/jtbd/transforms.py). All sets are lifted to sorted tuples before they enter the dataclass so two normalizations produce identical bytes.

### 2.3 Run 15 generators

Each generator is a pure function `(NormalizedBundle, NormalizedJTBD?) → GeneratedFile | list[GeneratedFile]`. They split into two cohorts:

| Cohort | Count | Run | What it emits |
|---|---|---|---|
| **Per-JTBD** | 9 | once per JTBD | Files specific to one job (model, router, service, migration, workflow_def, form_spec, simulation test, frontend step, workflow adapter). |
| **Per-bundle** | 6 | once per bundle | Cross-cutting aggregations (permissions catalog, audit taxonomy, notifications registry, alembic env, .env example, top-level README). |

Generator implementations are uniformly thin:

```python
# flowforge_cli/jtbd/generators/audit_taxonomy.py
def generate(bundle: NormalizedBundle) -> GeneratedFile:
	content = render("audit_taxonomy.py.j2", project=bundle.project, bundle=bundle)
	return GeneratedFile(
		path=f"backend/src/{bundle.project.package}/audit_taxonomy.py",
		content=content,
	)
```

The generator itself does **no** logic; the template fills in the blanks. The exception is the JSON-emitting generators (`workflow_def`, `form_spec`) which build a dict and `json.dumps(..., sort_keys=True)` — Jinja whitespace is unhelpful for JSON, so the tradeoff favours direct construction.

### 2.4 Deduplicate and sort

After every generator runs, the pipeline:

1. Deduplicates on `path` (later wins). No generator currently collides on a path; this is cheap insurance.
2. Sorts the file list by `path`. Two invocations with the same input produce the same emission order regardless of dict-iteration timing.

### 2.5 Write to disk

[`flowforge_cli.commands.jtbd_generate`](../python/flowforge-cli/src/flowforge_cli/commands/jtbd_generate.py) refuses to write into a non-empty target unless `--force` is passed, makes parent directories on demand, and writes files as UTF-8.

---

## 3. Synthesis rules (declarative → state machine)

This is the most opaque transform in the pipeline, and the one that makes the no-LLM claim work. The rules are defined in [`flowforge_cli/jtbd/transforms.py`](../python/flowforge-cli/src/flowforge_cli/jtbd/transforms.py).

### 3.1 States

The base flow is always two manual_review states plus a terminal_success:

```
intake (swimlane = actor.role)  →  review (swimlane = "reviewer")  →  done
```

Then optional states are added in this order:

| Trigger | State added |
|---|---|
| Any approval has `policy: "authority_tier"` | `escalated` (manual_review, swimlane = "supervisor") |
| Any `edge_case.handle == "branch"` | one extra manual_review state per edge case, named after `edge_case.branch_to` (or `edge_case.id` as fallback), reviewer swimlane |
| Any `edge_case.handle == "reject"` | `rejected` (terminal_fail) |
| Always | `done` (terminal_success), appended last |

State kinds are pulled from the lookup table `EDGE_HANDLE_TO_STATE_KIND`:

```python
{
	"branch":     "manual_review",
	"reject":     "terminal_fail",
	"escalate":   "manual_review",
	"compensate": "manual_review",
	"loop":       "manual_review",
}
```

### 3.2 Transitions

Every transition gets:

- A deterministic `id` of the form `<jtbd_id>_<event>` (or `<jtbd_id>_<edge_id>` for edge cases).
- A `priority`: 0 for happy-path, 5+ for edge cases (in declaration order — first edge case is priority 5, second is 6, and so on).
- A `gates: [{kind: "permission", permission: "<jtbd_id>.<event>"}]` so the lookup-permission validator stays happy and the host has real-looking RBAC.
- An `effects: [...]` list. The `submit` transition emits `create_entity` plus `audit`. `approve` emits `notify`. Edge cases emit `audit` keyed to their id.

The base set is always two transitions:

| id | event | from → to | priority | guards | effects |
|---|---|---|---|---|---|
| `<jtbd>_submit` | `submit` | `intake → review` | 0 | none | `create_entity`, `audit` |
| `<jtbd>_approve` | `approve` | `review → done` | 0 | none | `notify` |

If `escalated` is present, two more transitions are added:

| id | event | from → to | priority | effects |
|---|---|---|---|---|
| `<jtbd>_escalate` | `escalate` | `review → escalated` | 10 | `audit` |
| `<jtbd>_escalated_approve` | `approve` | `escalated → done` | 0 | `notify` |

Then, per `edge_case`, a transition is appended whose shape depends on `handle`:

| `handle` | event | from → to | priority | guards | effects |
|---|---|---|---|---|---|
| `branch` | `submit` | `intake → <branch_to>` | 5+i | `[{kind: "expr", expr: {var: "context.<edge_id>"}}]` | `audit` |
| `reject` | `reject` | `review → rejected` | 5+i | none | `audit` |
| `loop` | `request_more_info` | `review → intake` | 5+i | none | `audit` |
| `escalate` | not synthesised here (covered by approval-driven escalation above) | | | | |
| `compensate` | not yet synthesised; reserved for saga work | | | | |

The `branch` guard reads from `context.<edge_id>` because the engine evaluates guards through `flowforge.expr` against the current instance context. The host or the bundle author is expected to populate `context.<edge_id>` before firing `submit` (the worked example in `examples/insurance_claim/` puts `large_loss = loss_amount > 100_000` in `context.large_loss` before submit).

### 3.3 Permissions

```python
base = [f"{jtbd}.read", f"{jtbd}.submit", f"{jtbd}.review", f"{jtbd}.approve"]
if any edge_case.handle == "reject":          base += [f"{jtbd}.reject"]
if any approval.policy == "authority_tier":   base += [f"{jtbd}.escalate"]
# Filter out any name already in shared.permissions.
```

Per-JTBD lists are unioned at the bundle level into `all_permissions`, sorted, deduplicated. The cross-bundle `permissions.py` catalog is the single source of truth — there is exactly one place to look up "what permissions does this app define?".

### 3.4 Audit topics

```python
topics = [f"{jtbd}.submitted", f"{jtbd}.approved"]
for edge in edge_cases:
	if handle == "branch": topics += [f"{jtbd}.{edge.id}"]
	if handle == "reject": topics += [f"{jtbd}.{edge.id}_rejected"]
	if handle == "loop":   topics += [f"{jtbd}.{edge.id}_returned"]
if any approval.policy == "authority_tier": topics += [f"{jtbd}.escalated"]
```

The cross-bundle `audit_taxonomy.py` is a closed enum so callers can refer to topics by symbol rather than by string literal.

### 3.5 Field mapping

`data_capture[i].kind` decides three things at once:

- `sa_type` — the SQLAlchemy column type used in the model template.
- `sql_type` — the raw SQL column type used in the alembic migration.
- `ts_component` — the `@flowforge/renderer` component name for the form.

The complete table:

| `kind` | `sa_type` | `sql_type` | `ts_component` |
|---|---|---|---|
| `text` | `String(512)` | `VARCHAR(512)` | `TextField` |
| `textarea` | `Text()` | `TEXT` | `TextAreaField` |
| `email` | `String(320)` | `VARCHAR(320)` | `TextField` |
| `phone` | `String(40)` | `VARCHAR(40)` | `TextField` |
| `address` | `String(512)` | `VARCHAR(512)` | `TextField` |
| `number` | `Numeric()` | `NUMERIC` | `NumberField` |
| `money` | `Numeric(18, 2)` | `NUMERIC(18, 2)` | `MoneyField` |
| `date` | `Date()` | `DATE` | `DateField` |
| `datetime` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | `DateField` |
| `enum` | `String(64)` | `VARCHAR(64)` | `EnumField` |
| `boolean` | `Boolean()` | `BOOLEAN` | `BooleanField` |
| `party_ref` | `String(64)` | `VARCHAR(64)` | `LookupField` |
| `document_ref` | `String(64)` | `VARCHAR(64)` | `FileField` |
| `signature` | `String(128)` | `VARCHAR(128)` | `TextField` |
| `file` | `String(256)` | `VARCHAR(256)` | `FileField` |

`required: true` becomes `nullable=False` on the column; absent or `false` becomes `nullable=True`. The `pii` flag is preserved into the form spec and into the React step component's field metadata; **it is not** propagated into the column definition (column-level encryption stays a host responsibility, wired through the `SettingsPort`).

---

## 4. Generator catalog

### 4.1 Per-JTBD generators

| Generator | Output path | What it emits |
|---|---|---|
| `workflow_def` | `workflows/<id>/definition.json` | The JSON DSL workflow_def. Synthesised states + transitions + metadata (`title`, `actor`, `sla_breach_seconds`). Validates against `workflow_def.schema.json` in the generator tests. |
| `form_spec` | `workflows/<id>/form_spec.json` | The form spec consumed by `@flowforge/renderer`. Each `data_capture` field becomes a form field with kind, label, required, pii, optional `validation`. |
| `sa_model` | `backend/src/<pkg>/models/<id>.py` | SQLAlchemy 2.x model with typed columns. Includes the always-on columns (`id` primary key, `tenant_id`, `state`, `created_at`, `updated_at`) plus one column per `data_capture` field. |
| `db_migration` | `backend/migrations/versions/<rev>_create_<id>.py` | Alembic migration with both `upgrade()` and `downgrade()`. The revision id is `sha256(package + jtbd_id)[:12]`, stable across machines. Adds a covering index on `(tenant_id, state)`. |
| `workflow_adapter` | `backend/src/<pkg>/adapters/<id>_adapter.py` | Loads `definition.json` once, exposes `fire_event(event, payload, principal, tenant_id) -> FireResult`. |
| `domain_service` | `backend/src/<pkg>/services/<id>_service.py` | `Service` class with `submit()` and `transition(event, payload)`. Coordinates the model + adapter; tests inject the principal. |
| `domain_router` | `backend/src/<pkg>/routers/<id>_router.py` | FastAPI `APIRouter` mounted at `/<url_segment>`. Currently exposes `POST /<url_segment>/events` accepting `{event, payload}`. |
| `tests` | `backend/tests/<id>/test_simulation.py` | Pytest suite that walks the workflow with each declared event and asserts the resulting state. Uses `flowforge.simulator` against the generated `definition.json`. |
| `frontend` | `frontend/src/components/<url_segment>/<Class>Step.tsx` and `frontend/src/app/<url_segment>/page.tsx` (Next.js) | A typed React step component that lists fields and renders an event button per declared event. The page is a thin shell that mounts the component. |

### 4.2 Per-bundle generators

| Generator | Output path | What it emits |
|---|---|---|
| `permissions` | `backend/src/<pkg>/permissions.py` | The deduplicated, sorted union of every JTBD's permissions plus `shared.permissions`. Closed list, one constant per permission. |
| `audit_taxonomy` | `backend/src/<pkg>/audit_taxonomy.py` | Closed `StrEnum` of every audit-event topic emitted anywhere in the bundle. |
| `notifications` | `backend/src/<pkg>/notifications.py` | Registry of every `(trigger, channel, audience)` triple, deduplicated, sorted. |
| `alembic` | `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/alembic.ini` | The alembic harness wired to the project's metadata. |
| `env_example` | `.env.example` | Template `.env` covering `DATABASE_URL`, signing-secret guidance, RBAC mode, etc. The values are placeholders — production values are host-supplied. |
| `readme` | `README.md` | Top-level README for the generated app describing how to install, migrate, and run. |

---

## 5. Determinism guarantees

Byte-identical regen is enforced on every PR (`scripts/check_all.sh` step 8 diffs `examples/<example>/generated/` against a fresh regen). The properties that make this work:

1. **Templates use `StrictUndefined`.** A typo or missing context variable raises `UndefinedError` at render time. Silent empty strings cannot leak in.
2. **`json.dumps(..., sort_keys=True)` everywhere.** Two runs produce identical key orderings even when the source was a Python dict with insertion-order semantics.
3. **All sets are sorted before they cross the boundary.** Permissions, audit topics, deduped notifications — every aggregation is sorted before it enters a Jinja context.
4. **Alembic revisions are derived, not random.** `_stable_revision(package, jtbd_id) = sha256(...)[:12]`. No `uuid4` calls anywhere in the pipeline.
5. **No `datetime.now()` in templates.** Generated files do not carry generation timestamps.
6. **`pipeline.generate()` sorts the final file list by path.** The order in which generators ran does not affect the output.
7. **The Jinja env is cached and shared.** `_env()` is `@lru_cache(maxsize=1)`-decorated and configured once: `autoescape=False`, `trim_blocks=True`, `lstrip_blocks=True`, `keep_trailing_newline=True`. Whitespace handling is identical across templates.

Together, these mean that a bundle change moves exactly the affected files, and `git diff` over a regenerated `examples/<example>/generated/` is a faithful proxy for "what does this bundle change actually do?".

---

## 6. Output anatomy

For the insurance-claim bundle (1 JTBD, ~120 LOC of bundle), the generator emits 18 files / ~600 LOC across three top-level directories. The full layout is:

```
<out>/
├── README.md                                          ← per-bundle
├── .env.example                                       ← per-bundle
├── backend/
│   ├── alembic.ini                                    ← per-bundle
│   ├── migrations/
│   │   ├── env.py                                     ← per-bundle
│   │   ├── script.py.mako                             ← per-bundle
│   │   └── versions/
│   │       └── <rev>_create_claim_intake.py           ← per-JTBD
│   ├── src/insurance_claim_demo/
│   │   ├── audit_taxonomy.py                          ← per-bundle
│   │   ├── notifications.py                           ← per-bundle
│   │   ├── permissions.py                             ← per-bundle
│   │   ├── adapters/claim_intake_adapter.py           ← per-JTBD
│   │   ├── models/claim_intake.py                     ← per-JTBD
│   │   ├── routers/claim_intake_router.py             ← per-JTBD
│   │   └── services/claim_intake_service.py           ← per-JTBD
│   └── tests/
│       └── claim_intake/test_simulation.py            ← per-JTBD
├── frontend/src/
│   ├── app/claim-intake/page.tsx                      ← per-JTBD
│   └── components/claim-intake/ClaimIntakeStep.tsx    ← per-JTBD
└── workflows/claim_intake/
    ├── definition.json                                ← per-JTBD (synthesised state machine)
    └── form_spec.json                                 ← per-JTBD
```

For an N-JTBD bundle: 9 per-JTBD files × N + 6 per-bundle files. A 5-JTBD bundle is ~51 files; an 8-JTBD bundle is ~78. The synthesised state machine for one JTBD is 6 states + 6 transitions for the insurance-claim shape; smaller for JTBDs with no edge cases or escalation.

---

## 7. Runtime contract

The host application must wire **before** the generated code can run end-to-end. None of this is generated — the generator stops at the boundary the runtime starts at.

### 7.1 Required wiring

| Port | Why | Who supplies the adapter |
|---|---|---|
| `TenancyResolver` | The migration includes a `tenant_id` column; the engine binds it via GUC during `fire`. | `flowforge-tenancy` (`SingleTenantGUC`, `MultiTenantGUC`, or `NoTenancy` for single-tenant dev). |
| `RbacResolver` | Every transition has a `permission` gate; without an RBAC adapter, every fire is denied. | `flowforge-rbac-static` (YAML/JSON-driven, fine for dev) or `flowforge-rbac-spicedb` (SpiceDB-backed). |
| `AuditSink` | Every transition emits an `audit` effect. | `flowforge-audit-pg` for hash-chained Postgres audit. |
| `OutboxRegistry` | Every `notify` effect dispatches an envelope through the outbox. | `flowforge-outbox-pg` plus a worker process. |
| `NotificationPort` | The outbox handler invokes this to actually send the email/Slack/SMS. | `flowforge-notify-multichannel` or a noop in dev. |

### 7.2 Optional wiring

| Port | Used when |
|---|---|
| `DocumentPort` | Bundle declares `documents_required`. |
| `MoneyPort` | Bundle has `money` fields. |
| `SigningPort` | Bundle uses signature fields or signed audit events. |
| `RlsBinder` | Bundle declares `tenancy: "multi"`. |
| `MetricsPort` | Production observability. |

Every port has an in-memory fake under [`flowforge.testing.port_fakes`](../python/flowforge-core/src/flowforge/testing/port_fakes.py); calling `flowforge.config.reset_to_fakes()` in a test setup wires every port at once for offline runs.

### 7.3 The generated router is auth-stub

The `domain_router` emits a default principal of `Principal(user_id="anonymous", roles=("anonymous",))`. The intent is that the host overrides the FastAPI dependency in production:

```python
from fastapi import Depends, Request
from flowforge.ports.types import Principal
from .auth import extract_session_principal

app.dependency_overrides[get_principal] = extract_session_principal
```

The router itself does **not** know about session cookies, JWTs, or auth headers. That is host territory.

---

## 8. Customisation policy

The generator owns nine file categories: model, migration, adapter, service, router, simulation test, frontend step, workflow_def, form_spec. **Hand-editing these files is not supported** — the next regen overwrites them. The intended workflow is:

1. **Edit the bundle.** Field changes, new edge cases, new approvals — all happen in `jtbd-bundle.json`.
2. **Regenerate.** `flowforge jtbd-generate --jtbd jtbd-bundle.json --out . --force`.
3. **Diff.** `git diff` shows exactly what the bundle change moved.
4. **Run the simulation tests.** They were regenerated too; they still pass for valid bundle changes.
5. **Run alembic.** Each model change ships with a fresh migration revision (the revision id is content-hashed, so adding a field produces a new revision rather than mutating the old one — safe to apply in order).

For changes the bundle cannot express (sub-workflows, signal waits, parallel forks, custom guards), the supported escape hatches are:

- **Edit `definition.json` directly.** It's a flat JSON document validated by `flowforge validate`. The Designer (`@flowforge/designer`) is a visual editor for this file.
- **Add a domain rule pack.** Per-domain packs (e.g. `flowforge-jtbd-banking`) layer extra lint rules and template overrides without forking the generator.
- **Subclass the generated service.** The `<id>_service.py` is intentionally minimal so a host-specific subclass can extend it without touching generated code.
- **Override the form spec.** The `form_spec.json` is data; a host can ship its own.

The cross-bundle aggregations (`permissions.py`, `audit_taxonomy.py`, `notifications.py`) are also generator-owned. To add a permission that the bundle cannot derive, declare it in `bundle.shared.permissions` — the aggregator unions it in.

---

## 9. Verification

Three independent gates exercise the pipeline:

1. **Schema round-trip.** Every emitted `workflow_def.json` is loaded with `WorkflowDef.model_validate()` and validated by `flowforge.compiler.validate()` in the generator unit tests. Every emitted `form_spec.json` is round-tripped against `form_spec.schema.json`.
2. **Byte-identical regen.** [`scripts/check_all.sh`](../scripts/check_all.sh) step 8 regenerates each `examples/<example>/generated/` into a temp dir and `diff -rq`s it against the checked-in tree. Any drift fails the gate.
3. **Simulation smoke test.** The generated `test_simulation.py` exercises every transition the synthesiser produced. Adding a JTBD that triggers a state-machine shape change automatically produces simulation tests for the new shape.

For a fourth, deeper layer of confidence, the framework's [`tests/cross_runtime/`](../tests/cross_runtime/) suite ensures that the expression evaluator inside `definition.json` (e.g. the `branch` guard `{var: "context.<edge_id>"}`) produces byte-identical results in Python and TypeScript. Cross-runtime parity is architecture invariant 5.

---

## 10. Worked example: insurance_claim

The bundle [`examples/insurance_claim/jtbd-bundle.json`](../examples/insurance_claim/jtbd-bundle.json) declares one JTBD (`claim_intake`) with:

- 7 `data_capture` fields (`claimant_name`, `policy_number`, `loss_date`, `loss_amount`, `loss_description`, `contact_email`, `contact_phone`).
- 2 `documents_required` (`proof_of_loss`, `police_report`).
- 2 `edge_cases` (`large_loss` with `handle: "branch"`, `lapsed_policy` with `handle: "reject"`).
- 1 approval (`role: "supervisor"`, `policy: "authority_tier"`, `tier: 2`).
- A `sla.breach_seconds = 86400`.

The synthesiser produces:

| Synthesised | Count | Notes |
|---|---|---|
| States | 6 | `intake, review, escalated, senior_triage, rejected, done`. The `escalated` state comes from the authority-tier approval; `senior_triage` from the `large_loss` branch (`branch_to: "senior_triage"`); `rejected` from the `lapsed_policy` reject. |
| Transitions | 6 | Base: `submit`, `approve`. Authority-tier: `escalate`, `escalated_approve`. Edge cases: `large_loss` (priority 5, guard `var: context.large_loss`), `lapsed_reject` (priority 6). |
| Permissions | 6 | `claim_intake.{read, submit, review, approve, escalate, reject}`. |
| Audit topics | 5 | `claim_intake.{submitted, approved, escalated, large_loss, lapsed_policy_rejected}`. |
| Columns | 12 | 5 always-on (`id, tenant_id, state, created_at, updated_at`) + 7 from `data_capture`. |
| Files | 18 | 9 per-JTBD × 1 JTBD + 6 per-bundle + 3 alembic harness/files. |
| Migration revision | `2a43cfa86685` | `sha256("insurance_claim_demo:claim_intake")[:12]`. |
| Total LOC | ~600 | Generated code; the bundle that produced it is ~120 LOC. |

Run `flowforge jtbd-generate --jtbd examples/insurance_claim/jtbd-bundle.json --out /tmp/regen --force` and `diff -ru examples/insurance_claim/generated/ /tmp/regen/` for an empty diff against the checked-in output.

---

## 11. What this architecture buys

A few properties that fall out of the design rather than being explicitly chased.

- **The bundle is the source of truth.** Generated code is discardable. Any reviewer can read the bundle and understand what the application does without reading 600 lines of host code.
- **Migrations are reproducible.** The content-hashed revision id means two developers regenerating from the same bundle produce the same migration on the same line. Conflicts in migration ordering (a real problem in long-lived alembic histories) are bounded by bundle history.
- **The permission catalog is closed.** Because `permissions.py` is the union of every JTBD's permissions, a static check can verify that every transition's `permission` gate exists in the catalog — and it can do so without runtime introspection.
- **The audit taxonomy is closed.** Because `audit_taxonomy.py` is a `StrEnum`, an audit-trail viewer can render every topic with confidence that no run-time code emits topics outside the enum. Lint rules can enforce this.
- **Cross-runtime parity is testable.** Because the workflow_def is JSON, the same fixture is consumed by Python (engine) and TypeScript (designer/renderer/simulator). The 200-input cross-runtime fixture pins this property.
- **No-code authoring is approachable.** The Designer (`@flowforge/designer`) edits `definition.json` directly. The JTBDEditor (`flowforge-jtbd-editor`) edits the bundle. Either path produces a runnable application — and the two diverge only in how much synthesis the user wants the generator to do for them.

If you only remember one thing: the bundle describes intent in domain terms, the synthesiser turns it into a state machine using fixed rules, and 15 generators emit the runtime fixture for the state machine. There is no magic in step 2 or step 3 — the magic, such as it is, is that step 2 is enough.
