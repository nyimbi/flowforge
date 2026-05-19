# Flowforge

Flowforge is a portable workflow framework for building regulated, multi-tenant
business applications from declarative workflow definitions and JTBD
(jobs-to-be-done) bundles.

It gives host applications:

- A JSON workflow DSL with a compiler, simulator, deterministic replay, and a
  two-phase fire engine.
- A pure Python core with no I/O dependencies and 14 explicit host-wired ports.
- Adapter packages for FastAPI, SQLAlchemy/Postgres, tenancy, audit, outbox,
  RBAC, documents, signing, notifications, metrics, and related infrastructure.
- A TypeScript frontend surface: form renderer, runtime client, visual workflow
  designer, and JTBD editor.
- A deterministic JTBD-to-application generator that emits backend, frontend,
  workflow, form, tests, seed data, docs, and design-token assets.

Flowforge was extracted from UMS, but UMS is not a runtime dependency. A UMS
checkout is used only for explicit downstream release-certification parity
tests. Nothing under this repository should import from UMS or require UMS for
ordinary package development.

> v0.1.0 shipped 2026-05-08 as the audit-2026 release. It includes one
> SECURITY-BREAKING change: HMAC default secrets were removed. Read
> [docs/audit-2026/SECURITY-NOTE.md](docs/audit-2026/SECURITY-NOTE.md) and run
> `flowforge pre-upgrade-check` before upgrading an existing host.

## One-Command Setup

From a fresh source checkout:

```bash
make setup
```

That runs [scripts/setup.sh](scripts/setup.sh), which:

- verifies `uv`, Python, Node, and `pnpm` are available;
- installs the full Python workspace with `uv sync`;
- installs the JS workspace under [js](js);
- installs the visual-regression harness under
  [tests/visual_regression](tests/visual_regression);
- smoke-checks the `flowforge` CLI.

Equivalent direct command:

```bash
bash scripts/setup.sh
```

Useful setup switches:

```bash
FLOWFORGE_SKIP_JS=1 bash scripts/setup.sh
FLOWFORGE_SKIP_VISREG=1 bash scripts/setup.sh
FLOWFORGE_SETUP_SMOKE=0 bash scripts/setup.sh
```

Prerequisites:

- Python 3.11+
- `uv`
- Node 22 for the repo CI-compatible JS path
- `pnpm` 11.1.3 for the repo's `allowBuilds` semantics

If you only need the CLI in a source checkout:

```bash
uv sync
uv run flowforge --help
```

Flowforge is path-dependency/source-first in this repository and is not yet
published as a single PyPI install target.

## Five-Minute Tour

Run the interactive tutorial:

```bash
uv run flowforge tutorial --out /tmp/flowforge-demo --no-pause
```

Generate a complete example application from the insurance JTBD bundle:

```bash
uv run flowforge jtbd-generate \
  --jtbd examples/insurance_claim/jtbd-bundle.json \
  --out /tmp/flowforge-insurance \
  --force
```

Validate or simulate a generated workflow:

```bash
uv run flowforge validate --def /tmp/flowforge-insurance/workflows/claim_intake/definition.json
uv run flowforge simulate --def /tmp/flowforge-insurance/workflows/claim_intake/definition.json --events submit
```

Run the normal local gate:

```bash
bash scripts/check_all.sh
```

Run the fail-closed local release gate:

```bash
make audit-2026-release-local
```

The external release bundle intentionally remains separate because it requires
browser execution, retained visual evidence, optional LLM sidecar evidence,
downstream UMS parity, and live Postgres checks:

```bash
make audit-2026-release-external-preflight
```

See
[docs/audit-2026/external-release-runbook.md](docs/audit-2026/external-release-runbook.md)
for the manual release-certification workflow.

## What Flowforge Builds

Flowforge has three authoring levels:

1. **JTBD bundle**: a product/workflow author describes the job, actors, data,
   documents, approvals, SLAs, notifications, compliance, and design tokens.
2. **Generator output**: `flowforge jtbd-generate` emits application code,
   workflow definitions, form specs, tests, docs, i18n, and design tokens.
3. **Workflow DSL**: the visual designer or code author edits the generated
   `definition.json` directly when a workflow needs more precision than the
   bundle synthesis provides.

For one JTBD such as `claim_intake`, the generator emits a host app surface that
typically includes:

| Output | Purpose |
|---|---|
| `workflows/<id>/definition.json` | Flowforge workflow DSL |
| `workflows/<id>/form_spec.json` | Form renderer schema |
| `workflows/<id>/diagram.mmd` | Mermaid source diagram |
| `workflows/<id>/reachability.json` or `reachability_skipped.txt` | Optional reachability proof |
| `backend/src/<pkg>/models.py` | SQLAlchemy model |
| `backend/src/<pkg>/services/<id>_service.py` | Domain service |
| `backend/src/<pkg>/routers/<id>_router.py` | FastAPI route surface |
| `backend/src/<pkg>/adapters/<id>_adapter.py` | EntityAdapter and fire wrapper |
| `backend/tests/<id>/test_simulation.py` | Simulator tests |
| `backend/tests/<id>/test_property.py` | Property tests |
| `frontend/src/.../Step.tsx` | React workflow step |
| `frontend/src/.../runtimeClient.ts` | Runtime API client |
| `frontend/src/.../design_tokens.css` | Host skin/theme tokens |
| `frontend-admin/...` | Admin shell and matching theme tokens |
| `tests/e2e/<id>.spec.ts` | Playwright happy path |
| `docs/ops/<bundle>/restore-runbook.md` | Generated operational runbook |

The generator is deterministic. Given the same bundle and sidecars, it emits the
same bytes. CI diffs committed example output against fresh regeneration.

## JTBD Bundle Grammar

A JTBD bundle is JSON or YAML. The canonical models live in
[python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py](python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py),
and the CLI validates bundles against the bundled `jtbd-1.0` JSON schema.

Top-level shape:

```yaml
project:
  name: insurance-claim-demo
  package: insurance_claim_demo
  domain: claims
  tenancy: single
  languages: [en, fr-CA]
  currencies: [USD, ZAR]
  frontend_framework: nextjs
  frontend:
    form_renderer: real
  design:
    primary: "#0f766e"
    accent: "#f59e0b"
    font_family: '"IBM Plex Sans", system-ui, sans-serif'
    density: compact
    radius_scale: 1.5
shared:
  roles: [adjuster, supervisor, claimant]
  permissions: [claim_intake.read]
jtbds:
  - id: claim_intake
    title: File an insurance claim
    actor:
      role: claimant
      external: true
    situation: A policyholder suffers a covered loss.
    motivation: Recover insured losses quickly.
    outcome: Claim is accepted into triage.
    success_criteria:
      - Claim ID is generated within 5 minutes.
    data_capture:
      - id: claimant_name
        kind: text
        label: Claimant full name
        required: true
        pii: true
    documents_required:
      - kind: proof_of_loss
        min: 1
        freshness_days: 90
        av_required: true
    edge_cases:
      - id: large_loss
        condition: loss_amount > 100000
        handle: branch
        branch_to: senior_triage
    approvals:
      - role: adjuster
        policy: 1_of_1
    sla:
      warn_pct: 80
      breach_seconds: 86400
    notifications:
      - trigger: state_enter
        channel: email
        audience: claimant
    metrics:
      - claim_intake.submission_count
    compliance: [SOC2]
    data_sensitivity: [PII]
```

### Top-Level Fields

| Field | Required | Meaning |
|---|---:|---|
| `project` | yes | Bundle metadata and host-app defaults |
| `shared` | no | Shared roles, permissions, and entity metadata |
| `jtbds` | yes | One or more JTBD specs; IDs must be unique |

### `project`

| Field | Required | Allowed values / notes |
|---|---:|---|
| `name` | yes | Human-readable project name |
| `package` | yes | ASCII snake_case identifier |
| `domain` | yes | Host domain label |
| `tenancy` | no | `none`, `single`, `multi`; default `single` |
| `languages` | no | Locale tags used for generated i18n catalogs |
| `currencies` | no | Currency codes used by forms/money fields |
| `frontend_framework` | no | `nextjs`, `remix`, `vite-react`; default `nextjs` |
| `frontend.form_renderer` | no | `skeleton` or `real`; default `skeleton` |
| `design.primary` | no | CSS hex `#RGB`, `#RRGGBB`, or `#RRGGBBAA` |
| `design.accent` | no | CSS hex |
| `design.font_family` | no | CSS font-family string |
| `design.density` | no | `compact` or `comfortable` |
| `design.radius_scale` | no | Number from `0.0` to `4.0` |
| `compliance` | no | Project-wide compliance regimes |
| `data_sensitivity` | no | Project-wide sensitivity labels |

### `jtbds[]`

| Field | Required | Meaning |
|---|---:|---|
| `id` | yes | ASCII snake_case JTBD ID |
| `title` | no | Human title |
| `version` | no | Strict `MAJOR.MINOR.PATCH`; default `1.0.0` |
| `status` | no | `draft`, `in_review`, `published`, `deprecated`, `archived` |
| `actor` | yes | `role`, optional `department`, optional `external` |
| `situation` | yes | Context that triggers the job |
| `motivation` | yes | Why the actor wants the job done |
| `outcome` | yes | Desired end state |
| `success_criteria` | yes | At least one measurable criterion |
| `data_capture` | no | Fields captured by forms and models |
| `documents_required` | no | Required supporting documents |
| `edge_cases` | no | Known branches/reject/escalate/compensate paths |
| `approvals` | no | Approval lanes and policies |
| `sla` | no | Warning percentage and breach budget |
| `notifications` | no | Notification rules |
| `metrics` | no | Metric names emitted/generated for the workflow |
| `requires` | no | IDs or capabilities this JTBD depends on |
| `compliance` | no | JTBD-level compliance regimes |
| `data_sensitivity` | no | JTBD-level sensitivity labels |

### Enums and Validation Rules

`data_capture[].kind`:

```text
text, number, money, date, datetime, enum, boolean, party_ref, document_ref,
email, phone, address, textarea, signature, file
```

The current `jtbd-1.0` JSON schema requires every `data_capture` field to
declare `pii` explicitly as `true` or `false`. The parser also produces focused
errors for these sensitive field kinds:

```text
email, phone, party_ref, signature, file, address, text, textarea
```

`edge_cases[].handle`:

```text
branch, reject, escalate, compensate, loop
```

If `handle` is `branch`, `branch_to` is required.

`approvals[].policy`:

```text
1_of_1, 2_of_2, n_of_m, authority_tier
```

If `policy` is `n_of_m`, `n` is required. If `policy` is `authority_tier`,
`tier` is required.

`notifications[].trigger`:

```text
state_enter, state_exit, sla_warn, sla_breach, approved, rejected, escalated
```

`notifications[].channel`:

```text
email, sms, slack, webhook, in_app
```

`compliance`:

```text
GDPR, SOX, HIPAA, PCI-DSS, ISO27001, SOC2, NIST-800-53, CCPA
```

`data_sensitivity`:

```text
PII, PHI, PCI, secrets, regulated
```

Identifier fields such as `project.package` and `jtbds[].id` must start with an
ASCII lowercase letter and then contain only ASCII lowercase letters, digits,
and underscores.

## Generate Applications

Use the generator directly when you already have a bundle:

```bash
uv run flowforge jtbd-generate \
  --jtbd path/to/jtbd-bundle.json \
  --out ./generated \
  --force
```

Use the project scaffolder when you want a new host project skeleton:

```bash
uv run flowforge new my-claims-app \
  --jtbd examples/insurance_claim/jtbd-bundle.json \
  --out /tmp
```

Add or refresh a JTBD inside an existing generated project:

```bash
uv run flowforge add-jtbd path/to/jtbd-bundle.json --project ./my-claims-app
```

Lint a bundle before generation:

```bash
uv run flowforge jtbd lint --bundle path/to/jtbd-bundle.json --warn-only
```

Authoring loop:

1. Edit `jtbd-bundle.json`.
2. Run `uv run flowforge jtbd lint --bundle jtbd-bundle.json --warn-only` while drafting.
   Remove `--warn-only` for release-quality lifecycle lint.
3. Run `uv run flowforge jtbd-generate --jtbd jtbd-bundle.json --out generated --force`.
4. Run generated tests and inspect generated diffs.
5. Edit `workflows/<id>/definition.json` in the visual designer when the
   synthesized workflow needs manual topology changes.

## Workflow DSL

A workflow definition is one JSON document with a canonical schema. The
compiler validates topology before execution: unreachable states, duplicate
transition priorities, dead ends, invalid sub-workflow references, and related
shape errors fail before runtime.

Minimal shape:

```json
{
  "key": "claim_intake",
  "version": "0.1.0",
  "subject_kind": "claim",
  "initial_state": "intake",
  "states": [
    { "name": "intake", "kind": "manual_review", "swimlane": "claimant" },
    { "name": "review", "kind": "manual_review", "swimlane": "adjuster" },
    { "name": "done", "kind": "terminal_success" }
  ],
  "transitions": [
    {
      "id": "submit",
      "event": "submit",
      "from_state": "intake",
      "to_state": "review",
      "priority": 0,
      "guards": [],
      "gates": [],
      "effects": []
    }
  ]
}
```

Validate it:

```bash
uv run flowforge validate --def workflows/claim_intake/definition.json
```

Simulate it:

```bash
uv run flowforge simulate --def workflows/claim_intake/definition.json --events submit
```

## Visual Workflow Editor

The visual workflow editor lives in
[js/flowforge-designer](js/flowforge-designer). It is a React package around
ReactFlow plus Flowforge-specific panels:

- canvas for states and transitions;
- property panel for state, transition, gate, escalation, delegation, document,
  and checklist fields;
- form builder;
- validation panel;
- simulation panel;
- diff viewer;
- review/comment helpers.

Embed it in a host admin application:

```tsx
import { Designer, sampleWorkflow } from "@flowforge/designer";

export function WorkflowEditorPage() {
  return (
    <main style={{ height: "100vh" }}>
      <Designer workflow={sampleWorkflow()} />
    </main>
  );
}
```

The generated host applications are skinnable through `project.design`. A
single bundle-level token block drives:

- CSS variables in generated `design_tokens.css`;
- Tailwind theme config;
- TypeScript theme exports;
- customer-facing frontend styling;
- admin-console styling.

Example:

```json
{
  "project": {
    "design": {
      "primary": "#0f766e",
      "accent": "#f59e0b",
      "font_family": "\"IBM Plex Sans\", system-ui, sans-serif",
      "density": "compact",
      "radius_scale": 1.5
    }
  }
}
```

Host applications should wrap `@flowforge/designer` in their own app shell and
map host design tokens to Flowforge CSS variables. The editor must remain a
tenant-admin tool, not a marketing page: dense controls, predictable layout,
clear status, and no decorative chrome.

Designer verification:

```bash
pnpm --dir js --filter @flowforge/designer test
pnpm --dir js --filter @flowforge/designer build
```

Visual-regression harness:

```bash
pnpm --dir tests/visual_regression test
```

## Runtime Architecture

Flowforge core is I/O-free. The host application wires ports at startup and can
swap adapters without changing workflow definitions.

The engine is two-phase:

1. Evaluate guards and choose one transition.
2. Commit effects, saga steps, outbox envelopes, audit records, and snapshots.

If audit or outbox dispatch fails, the engine restores the pre-fire snapshot.
Per-instance fire is serialized; concurrent fires for one instance raise
`ConcurrentFireRejected`.

The expression evaluator is a frozen operator registry. There is no `eval`, no
arbitrary Python execution, and Python/TypeScript parity is tested on every PR.

### The 14 Ports

| # | Port | Purpose | Typical implementation |
|---|---|---|---|
| 1 | `TenancyResolver` | Resolve tenant and bind session scope | `flowforge-tenancy` |
| 2 | `RbacResolver` | Permission checks and seed registration | static or SpiceDB |
| 3 | `AuditSink` | Hash-chain audit recording and verification | `flowforge-audit-pg` |
| 4 | `OutboxRegistry` | Register and dispatch outbox envelopes | `flowforge-outbox-pg` |
| 5 | `DocumentPort` | Document attachment and classification | S3/document adapter |
| 6 | `MoneyPort` | Money formatting and conversion | `flowforge-money` |
| 7 | `SettingsPort` | Host settings | host supplied |
| 8 | `SigningPort` | Sign and verify payloads | KMS or explicit dev HMAC |
| 9 | `NotificationPort` | Render and send notifications | multichannel adapter |
| 10 | `RlsBinder` | Bind Postgres RLS context | `flowforge-sqlalchemy` |
| 11 | `EntityAdapter` | Domain create/update/lookup/compensate | generated/host supplied |
| 12 | `MetricsPort` | Emit metrics | host supplied or OTel |
| 13 | `TaskTrackerPort` | Create operational tasks | host supplied |
| 14 | `AccessGrantPort` | Temporary access grants | host supplied |

Tests use in-memory fakes through `flowforge.testing.port_fakes`.

## Repository Layout

```text
flowforge/
  python/                         uv workspace packages
    flowforge-core/                DSL, compiler, engine, simulator, ports
    flowforge-fastapi/             HTTP/WS adapter
    flowforge-sqlalchemy/          durable Postgres storage and RLS
    flowforge-cli/                 Typer CLI
    flowforge-jtbd/                canonical JTBD models/schema
    flowforge-jtbd-hub/            registry/hub surface
    flowforge-jtbd-*/              domain JTBD libraries
  js/
    flowforge-types/               TypeScript workflow/form types
    flowforge-renderer/            form renderer and TS expression evaluator
    flowforge-runtime-client/      REST/WS runtime client
    flowforge-step-adapters/       reusable generated-step adapters
    flowforge-designer/            visual workflow editor
    flowforge-jtbd-editor/         JTBD authoring editor
    flowforge-integration-tests/   cross-runtime JS tests
  examples/
    insurance_claim/
    hiring-pipeline/
    building-permit/
  tests/
    audit_2026/
    conformance/
    property/
    chaos/
    cross_runtime/
    edge_cases/
    observability/
    integration/
    visual_regression/
  docs/
  scripts/
```

The monorepo currently has 46 Python workspace members and 7 JS workspace
members. Tier-1 engine/adapters are the package surface. Domain
`flowforge-jtbd-*` libraries remain source/workspace members until each is
reviewed and flipped to package publishing.

## Development Commands

Install:

```bash
make setup
```

Common loops:

```bash
uv run pytest python/flowforge-core/tests -q
uv run pytest tests/audit_2026 -q --tb=short
uv run pytest tests/conformance -m invariant_p0
uv run pyright python/flowforge-core/src --pythonversion 3.11

pnpm --dir js -r test
pnpm --dir js --filter @flowforge/designer test
pnpm --dir js --filter @flowforge-renderer test
```

Full local gate:

```bash
bash scripts/check_all.sh
```

Local release gate:

```bash
make audit-2026-release-local
```

External release gate:

```bash
make audit-2026-release-external-preflight
make audit-2026-release-external
```

The external gate requires a browser-capable environment, `BACKEND_ROOT` for
downstream UMS parity when that proof is being collected, a live
`FLOWFORGE_TEST_PG_URL`, and reviewed sidecar evidence. It is manual
release-certification evidence, not a normal package dependency.

## CLI Surface

Run `uv run flowforge --help` for the live command list.

Frequently used commands:

| Command | Purpose |
|---|---|
| `flowforge tutorial` | Interactive JTBD-to-workflow walkthrough |
| `flowforge new` | Scaffold a host project from a JTBD bundle |
| `flowforge add-jtbd` | Add/refresh one JTBD in a generated project |
| `flowforge jtbd-generate` | Deterministically generate app artifacts |
| `flowforge jtbd lint` | Lint a JTBD bundle |
| `flowforge validate` | Validate workflow definitions |
| `flowforge simulate` | Walk a workflow through events |
| `flowforge replay` | Replay workflow events |
| `flowforge diff` | Diff workflow/JTBD structures |
| `flowforge pre-upgrade-check` | Check host upgrade readiness |
| `flowforge generate-llmtxt` | Generate an agent quickstart |
| `flowforge audit verify` | Verify audit-chain evidence |
| `flowforge audit-2026 health` | Query release-health probes |

## CI and Release Gates

Pull requests run the standalone gates:

- `flowforge-gate.yml`: wraps `scripts/check_all.sh`.
- `audit-2026.yml`: matrix over unit, conformance, property, cross-runtime,
  edge, e2e, ratchets, and signoff checks.
- `audit-2026-dom-baselines.yml`: reviewable DOM baseline artifacts.
- `audit-2026-browser-e2e.yml`: browser full-stack generated workflow.
- `jtbd-lint.yml`: advisory or strict JTBD linting, depending on
  `JTBD_LINT_STRICT`.

Manual release certification uses:

- `audit-2026-release-external.yml`: browser, sidecar, UMS parity, and live
  Postgres evidence bundle.

## Security Posture

Non-negotiable safety gates:

- No default HMAC signing secret.
- No string-interpolated SQL.
- No `==` comparison for HMAC digests.
- No silent `except Exception: pass`.
- Conformance tests enforce tenant isolation, two-phase atomicity, replay
  determinism, snapshot isolation, cross-runtime expression parity, RBAC seed
  integrity, audit-chain monotonicity, migration/RLS safety, and parallel-fork
  token primitives.
- Security-impacting changes must be documented in
  [docs/audit-2026/SECURITY-NOTE.md](docs/audit-2026/SECURITY-NOTE.md).

## Examples

| Example | Demonstrates |
|---|---|
| [examples/insurance_claim](examples/insurance_claim) | Claim intake, triage, adjudication, payout, documents, signing, audit |
| [examples/hiring-pipeline](examples/hiring-pipeline) | Candidate sourcing, screening, interviews, offer workflow |
| [examples/building-permit](examples/building-permit) | Permit intake, plan review, inspections, issuance, tenant data |

## Documentation

- [docs/flowforge-handbook.md](docs/flowforge-handbook.md): comprehensive
  system handbook.
- [docs/jtbd-user-guide.md](docs/jtbd-user-guide.md): how to write, manage,
  generate, review, and edit JTBD-driven applications.
- [docs/jtbd-generation.md](docs/jtbd-generation.md): generator behavior,
  emitted files, and host integration.
- [docs/workflow-framework-portability.md](docs/workflow-framework-portability.md):
  portability/source architecture.
- [docs/workflow-ed.md](docs/workflow-ed.md): workflow editor capability spec.
- [docs/workflow-ed-arch.md](docs/workflow-ed-arch.md): workflow editor
  architecture.
- [docs/jtbd-editor-arch.md](docs/jtbd-editor-arch.md): JTBD editor and hub
  design.
- [llm.txt](llm.txt): root AI/agent quickstart.
- [docs/llm.txt](docs/llm.txt): legacy extended AI quickstart.
- [docs/audit-2026](docs/audit-2026): audit reports, signoff, runbooks, and
  release evidence.

Per-package READMEs live beside their `pyproject.toml` or `package.json`.

## License

Apache-2.0. A dual-license commercial track is planned.
