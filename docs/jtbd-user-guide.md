# JTBD User Guide

This guide explains how to write, review, generate, and maintain Flowforge JTBD
(jobs-to-be-done) bundles, and how to use the visual workflow editor after a
bundle has generated a workflow definition.

## Mental Model

Flowforge has two authoring artifacts:

- **JTBD bundle**: product-level intent. It describes actors, situation,
  motivation, outcome, data capture, documents, edge cases, approvals, SLAs,
  notifications, compliance, and design tokens.
- **Workflow definition**: execution-level topology. It describes concrete
  states, transitions, guards, gates, effects, forms, escalation, delegation,
  and terminal states.

Use the JTBD bundle when you are describing what the application should do. Use
the workflow editor when you need to tune how the generated workflow behaves.

## Setup

From the Flowforge repository root:

```bash
make setup
```

This installs the Python workspace, the JS workspace, the visual-regression
harness, and verifies that the CLI starts.

For CLI-only authoring:

```bash
uv sync
uv run flowforge --help
```

## Start From the Tutorial

```bash
uv run flowforge tutorial --out /tmp/flowforge-demo --no-pause
```

The tutorial walks through a minimal bundle, generation, validation, and
simulation.

## Bundle Structure

A bundle may be JSON or YAML.

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
  permissions: [claim_intake.read, claim_intake.write]
jtbds:
  - id: claim_intake
    title: File an insurance claim
    actor:
      role: claimant
      external: true
    situation: A policyholder suffers a covered loss and needs to submit a claim.
    motivation: Recover insured losses quickly with minimal friction.
    outcome: Claim is accepted into triage and assigned to an adjuster.
    success_criteria:
      - Claim ID is generated and confirmed within 5 minutes.
      - Claim is routed to the correct triage queue within 24 hours.
    data_capture:
      - id: claimant_name
        kind: text
        label: Claimant full name
        required: true
        pii: true
      - id: loss_amount
        kind: money
        label: Estimated loss amount
        required: true
        pii: false
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

## Authoring Rules

### Identifiers

`project.package` and each `jtbds[].id` must:

- start with an ASCII lowercase letter;
- contain only ASCII lowercase letters, digits, and underscores.

Good:

```text
insurance_claim_demo
claim_intake
senior_triage
```

Bad:

```text
InsuranceClaim
claim-intake
claim intake
réclamation
```

### Required JTBD Fields

Every JTBD needs:

- `id`
- `actor`
- `situation`
- `motivation`
- `outcome`
- at least one `success_criteria`

Recommended for production-quality bundles:

- at least three `data_capture` fields;
- at least one document requirement when the job depends on evidence;
- at least one edge case;
- approvals for human-governed decisions;
- SLA and notification rules for operational workflows;
- compliance and sensitivity labels for regulated jobs.

### Field Kinds

Allowed `data_capture[].kind` values:

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

Example:

```yaml
- id: contact_email
  kind: email
  label: Contact email
  required: true
  pii: true
```

### Edge Cases

Allowed `edge_cases[].handle` values:

```text
branch, reject, escalate, compensate, loop
```

`branch` requires `branch_to`:

```yaml
- id: large_loss
  condition: loss_amount > 100000
  handle: branch
  branch_to: senior_triage
```

### Approvals

Allowed approval policies:

```text
1_of_1, 2_of_2, n_of_m, authority_tier
```

`n_of_m` requires `n`:

```yaml
- role: committee_member
  policy: n_of_m
  n: 2
```

`authority_tier` requires `tier`:

```yaml
- role: supervisor
  policy: authority_tier
  tier: 2
```

### Notifications

Standard triggers:

```text
state_enter, state_exit, sla_warn, sla_breach, approved, rejected, escalated
```

Those names are the built-in engine triggers. Bundle authors may also use custom
event names for domain-specific alerts.

Allowed channels:

```text
email, sms, slack, webhook, in_app, mail, push
```

### Design Tokens

The `project.design` block skins generated host applications:

```yaml
design:
  primary: "#0f766e"
  accent: "#f59e0b"
  font_family: '"IBM Plex Sans", system-ui, sans-serif'
  density: compact
  radius_scale: 1.5
```

`primary` and `accent` accept CSS hex values in `#RGB`, `#RRGGBB`, or
`#RRGGBBAA` form. `density` is `compact` or `comfortable`. `radius_scale` is
from `0.0` to `4.0`.

Regenerate after changing design tokens:

```bash
uv run flowforge jtbd-generate --jtbd jtbd-bundle.json --out generated --force
```

## Validate a Bundle

```bash
uv run flowforge jtbd lint --bundle jtbd-bundle.json --warn-only
```

`--warn-only` is useful during drafting and for the existing scaffold examples:
it prints lifecycle findings without blocking generation experiments. For
release-quality bundles, remove `--warn-only` and use strict mode when warnings
should block:

```bash
uv run flowforge jtbd lint --bundle jtbd-bundle.json --strict
```

The semantic linter reports lifecycle completeness separately from JSON-schema
validity. Required lifecycle stages are `discover`, `execute`, `error_handle`,
`report`, and `audit`; `undo` is recommended when compensation is possible.
When a stage is handled by another JTBD, the linter expects that delegation to
be explicit in lifecycle metadata.

## Generate an Application

Generate artifacts from a bundle:

```bash
uv run flowforge jtbd-generate \
  --jtbd jtbd-bundle.json \
  --out generated \
  --force
```

Scaffold a new host project from a bundle:

```bash
uv run flowforge new my-claims-app \
  --jtbd jtbd-bundle.json \
  --out /tmp
```

Generate an agent quickstart in the new project:

```bash
uv run flowforge new my-claims-app \
  --jtbd jtbd-bundle.json \
  --out /tmp \
  --emit-llmtxt
```

## Manage Existing JTBDs

### Add or Refresh a JTBD

Use `add-jtbd` when a generated project already exists and you want to append
or refresh one JTBD from a bundle:

```bash
uv run flowforge add-jtbd jtbd-bundle.json --project ./my-claims-app
```

If the command signature changes, use the live help as source of truth:

```bash
uv run flowforge add-jtbd --help
```

### Fork a Bundle

Use a fork when a tenant needs to customize a shared or upstream bundle:

```bash
uv run flowforge jtbd fork upstream-bundle.json \
  --tenant acme-corp \
  --out acme-corp/jtbd_bundle.json
```

Fork metadata preserves provenance so reviewers can see what was customized.

### Compare Bundle Versions

```bash
uv run flowforge bundle-diff old-bundle.json new-bundle.json
```

Use the diff before review to catch renamed IDs, field shape changes, SLA
changes, and compliance label changes.

### Review Copy Changes

`polish-copy` is an authoring-time command for wording improvements. It writes
a sidecar rather than mutating canonical bundle bytes.

```bash
uv run flowforge polish-copy \
  --bundle jtbd-bundle.json \
  --tone formal-professional \
  --require-llm \
  --commit
```

Review the sidecar before committing it.

## Verify Generated Output

Validate generated workflow definitions:

```bash
uv run flowforge validate --def generated/workflows/claim_intake/definition.json
```

Simulate a workflow:

```bash
uv run flowforge simulate \
  --def generated/workflows/claim_intake/definition.json \
  --events submit
```

Run generated tests from the generated project when present:

```bash
uv run pytest generated/backend/tests -q
```

Run Flowforge's own generator and audit tests from this repository:

```bash
uv run pytest python/flowforge-cli/tests/test_jtbd_generators.py -q
uv run pytest tests/audit_2026 -q --tb=short
```

## Use the Visual Workflow Editor

The visual editor edits workflow definitions and form specs after generation.
It is packaged as `@flowforge/designer` under
[js/flowforge-designer](../js/flowforge-designer).

### Install in a Host App

Inside this monorepo, consume it through the pnpm workspace:

```json
{
  "dependencies": {
    "@flowforge/designer": "workspace:*"
  }
}
```

Then install JS dependencies:

```bash
pnpm --dir js install --frozen-lockfile
```

### Embed the Editor

```tsx
import { Designer, createDesignerStore } from "@flowforge/designer";
import type { WorkflowDef, FormSpec } from "@flowforge/designer";

const store = createDesignerStore({
  workflow: workflowDefinition as WorkflowDef,
  form: formSpec as FormSpec,
});

export function WorkflowEditorPage() {
  return (
    <main style={{ height: "100vh" }}>
      <Designer
        store={store}
        initialTab="canvas"
      />
    </main>
  );
}
```

For quick smoke testing:

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

### Editor Tabs

| Tab | Use |
|---|---|
| `canvas` | Select states and transitions on a ReactFlow canvas |
| `form` | Build and edit the form spec |
| `validation` | Show static workflow issues |
| `simulation` | Fire event sequences against the definition |
| `diff` | Compare the current workflow to `compareTo` |

Example with diff:

```tsx
<Designer
  workflow={draftWorkflow}
  compareTo={publishedWorkflow}
  initialTab="diff"
/>
```

### Read Changes From the Store

The store is Zustand-based. Host applications can subscribe to workflow and
form changes and persist them through their own API.

```tsx
const workflow = store.getState().workflow;
const form = store.getState().form;

store.subscribe((state) => {
  saveDraft({
    workflow: state.workflow,
    form: state.form,
    version: state.version,
  });
});
```

Undo/redo are exposed through the store's temporal middleware:

```tsx
store.temporal.getState().undo();
store.temporal.getState().redo();
```

For collaborative editing, use the safe helpers:

```tsx
import { applyRemotePatch, safeRedo, safeUndo } from "@flowforge/designer";

applyRemotePatch(store, { workflow: remoteWorkflow });
const result = safeRedo(store);
if (!result.ok) {
  showToast(result.message);
}
```

### Skin the Editor in the Host Application

The generated app skin comes from `project.design`. Host applications should
map those same values into their app shell and into any CSS variables they use
around the designer.

Recommended host wrapper:

```tsx
<section
  className="flowforge-editor-shell"
  style={{
    "--ff-color-primary": design.primary,
    "--ff-color-accent": design.accent,
    "--ff-font-family": design.font_family,
  } as React.CSSProperties}
>
  <Designer store={store} />
</section>
```

The editor should live in a tenant-admin surface: fixed-height canvas region,
clear toolbar, predictable side panel, no marketing hero layout, and no
decorative chrome that hides workflow state.

### Test the Editor

```bash
pnpm --dir js --filter @flowforge/designer test
pnpm --dir js --filter @flowforge/designer build
```

For browser visual coverage:

```bash
pnpm --dir tests/visual_regression test
```

## Review Checklist

Before publishing or committing a JTBD change:

- Bundle lints cleanly.
- IDs are stable unless a migration/fork is intentional.
- All captured fields declare `pii`.
- Edge-case branches have clear targets.
- Approval policies include required `n` or `tier` fields.
- SLA and notification rules match operational reality.
- Compliance and sensitivity labels are explicit.
- Generated output was regenerated from the bundle.
- Workflow definitions validate.
- Simulation covers happy path and important edge paths.
- Visual editor changes are persisted through the host draft API.
- Human-reviewed sidecars are committed when copy was LLM-polished.

## Troubleshooting

`YAML input requires pyyaml`

: Install the full workspace with `make setup` or use JSON bundles.

`target exists and is not empty`

: Pass `--force` for deterministic regeneration into an existing output
  directory.

`field ... must declare pii`

: Add `pii: true` or `pii: false` to the field.

`handle='branch' requires branch_to`

: Add a `branch_to` target or use a non-branch handle.

Designer canvas is blank in a unit test

: Pass `withReactFlow={false}` in tests. ReactFlow needs a measured browser DOM;
  the fallback renderer preserves click and commit assertions.
