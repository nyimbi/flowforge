# JTBD bundle grammar (jtbd-1.0)

This is the canonical wire-format grammar for a JTBD bundle as it lives on disk. It is the single source of truth shared by the generator, the lockfile, the storage layer, and the linter.

The grammar is split into three layers:

1. **Lexical** — token shapes (id, semver, hash).
2. **Structural** — JSON object/array shape.
3. **Semantic** — cross-field constraints not expressible in pure structure.

The structural layer mirrors the Pydantic v2 models in [`flowforge_jtbd.dsl.spec`](../python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py) and the JSON schema at [`flowforge.dsl.schema.jtbd-1.0.schema.json`](../python/flowforge-core/src/flowforge/dsl/schema/jtbd-1.0.schema.json). Both carry `extra='forbid'` / `additionalProperties: false`: any field not listed below is a parse-time error. The lint-facing models in [`flowforge_jtbd.spec`](../python/flowforge-jtbd/src/flowforge_jtbd/spec.py) keep `extra='allow'` so the linter can survive forward-compatible additions; the canonical contract does not.

Notation used in this document:

| Symbol | Meaning |
|---|---|
| `::=` | production |
| `\|` | alternation |
| `?` | optional |
| `*` | zero or more |
| `+` | one or more |
| `{ ... }` | JSON object with named fields |
| `[ ... ]` | JSON array |
| `"lit"` | string literal (one of an enum) |
| `<name>` | non-terminal |
| `field!` | required field (no default) |
| `field` | optional field (has a default or is nullable) |
| `;;` | comment |

YAML and JSON are both accepted on disk; the YAML loader produces the same Python object graph, so the grammar is identical in either surface syntax.

---

## 1. Lexical grammar

```ebnf
<id>          ::= /[a-z][a-z0-9_]*/
                  ;; ASCII only. audit E-64 / IT-04 class 3 forbids
                  ;; cross-script identifiers (e.g. "café_run").
                  ;; Used for: JtbdSpec.id, JtbdProject.package.

<semver>      ::= MAJOR "." MINOR "." PATCH ( "-" PRERELEASE )? ( "+" BUILD )?
                  ;; Strict PEP 440 / semver shape, validated through
                  ;; packaging.version.Version. Empty pre-release/build
                  ;; suffixes ("1.0.0-", "1.0.0+") are rejected (audit J-09).
                  ;; The MAJOR.MINOR.PATCH triple must be three digit-only
                  ;; segments; "1.0" alone is not accepted.

<spec_hash>   ::= "sha256:" 64*HEXDIG-LOWER
                  ;; SHA-256 of the canonical-JSON body (RFC-8785-aligned).
                  ;; Lowercase hex only.

<currency>    ::= ISO-4217 alpha-3       ;; e.g. "USD", "ZAR"
<language>    ::= BCP-47 language tag    ;; e.g. "en", "fr-CA"
<str>         ::= JSON string
<int>         ::= JSON integer
<bool>        ::= true | false
```

---

## 2. Structural grammar

### 2.1 Top-level: bundle

```ebnf
<Bundle>      ::= {
                    project:  <Project>!,
                    shared:   <Shared>,                ;; default: {}
                    jtbds:    [ <JtbdSpec>+ ]!,        ;; min_length = 1
                  }
```

### 2.2 Project block

```ebnf
<Project>     ::= {
                    name:                <str>!,
                    package:             <id>!,
                    domain:              <str>!,
                    tenancy:             <Tenancy>,                  ;; default: "single"
                    languages:           [ <language>* ],
                    currencies:          [ <currency>* ],
                    frontend_framework:  <FrontendFramework>,        ;; default: "nextjs"
                    compliance:          [ <ComplianceRegime>* ],
                    data_sensitivity:    [ <DataSensitivity>* ],
                  }

<Tenancy>           ::= "none" | "single" | "multi"
<FrontendFramework> ::= "nextjs" | "remix" | "vite-react"
```

### 2.3 Shared block

```ebnf
<Shared>      ::= {
                    roles:        [ <str>* ],
                    permissions:  [ <str>* ],
                    entities:     [ <object>* ],   ;; opaque host-defined dicts
                  }
```

### 2.4 JTBD spec

```ebnf
<JtbdSpec>    ::= {
                    ;; identity
                    id:                  <id>!,
                    title:               <str>?,
                    version:             <semver>,                   ;; default: "1.0.0"
                    spec_hash:           <spec_hash>?,               ;; computed at publish
                    parent_version_id:   <str>?,                     ;; set by storage
                    replaced_by:         <str>?,
                    status:              <JtbdStatus>,               ;; default: "draft"

                    ;; jtbd body
                    actor:               <Actor>!,
                    situation:           <str>!,
                    motivation:          <str>!,
                    outcome:             <str>!,
                    success_criteria:    [ <str>+ ]!,                ;; min_length = 1
                    edge_cases:          [ <EdgeCase>* ],
                    data_capture:        [ <Field>* ],
                    documents_required:  [ <DocReq>* ],
                    approvals:           [ <Approval>* ],
                    sla:                 <Sla>?,
                    notifications:       [ <Notification>* ],
                    metrics:             [ <str>* ],

                    ;; governance
                    requires:            [ <str>* ],                 ;; <id> of other JTBDs
                    compliance:          [ <ComplianceRegime>* ],
                    data_sensitivity:    [ <DataSensitivity>* ],

                    ;; audit (set by storage; authors leave these unset)
                    created_by:          <str>?,
                    published_by:        <str>?,
                  }

<JtbdStatus>  ::= "draft" | "in_review" | "published" | "deprecated" | "archived"
```

### 2.5 Sub-objects

```ebnf
<Actor>       ::= {
                    role:        <str>!,
                    department:  <str>?,
                    external:    <bool>,                            ;; default: false
                  }

<Field>       ::= {
                    id:          <str>!,
                    kind:        <FieldKind>!,
                    label:       <str>?,
                    required:    <bool>,                            ;; default: false
                    pii:         <bool>?,                           ;; required if kind ∈ SENSITIVE_FIELD_KINDS
                    validation:  <object>?,                         ;; opaque
                    sensitivity: [ <DataSensitivity>* ],
                  }

<EdgeCase>    ::= {
                    id:          <str>!,
                    condition:   <str>!,                            ;; expression in flowforge.expr
                    handle:      <EdgeCaseHandle>!,
                    branch_to:   <str>?,                            ;; required when handle = "branch"
                  }

<DocReq>      ::= {
                    kind:            <str>!,
                    min:             <int>,                         ;; default: 1
                    max:             <int>?,
                    freshness_days:  <int>?,
                    av_required:     <bool>,                        ;; default: true
                  }

<Approval>    ::= {
                    role:    <str>!,
                    policy:  <ApprovalPolicy>!,
                    n:       <int>?,                                ;; required when policy = "n_of_m"
                    tier:    <int>?,                                ;; required when policy = "authority_tier"
                  }

<Sla>         ::= {
                    warn_pct:        <int>?,                        ;; 1 ≤ x ≤ 99
                    breach_seconds:  <int>?,                        ;; ≥ 60
                  }

<Notification>::= {
                    trigger:   <NotificationTrigger>!,
                    channel:   <NotificationChannel>!,
                    audience:  <str>!,
                  }
```

### 2.6 Enumerations

```ebnf
<FieldKind>          ::= "text" | "number" | "money" | "date" | "datetime"
                       | "enum" | "boolean" | "party_ref" | "document_ref"
                       | "email" | "phone" | "address" | "textarea"
                       | "signature" | "file"

<EdgeCaseHandle>     ::= "branch" | "reject" | "escalate" | "compensate" | "loop"

<ApprovalPolicy>     ::= "1_of_1" | "2_of_2" | "n_of_m" | "authority_tier"

<NotificationTrigger>::= "state_enter" | "state_exit" | "sla_warn" | "sla_breach"
                       | "approved" | "rejected" | "escalated"

<NotificationChannel>::= "email" | "sms" | "slack" | "webhook" | "in_app"

<DataSensitivity>    ::= "PII" | "PHI" | "PCI" | "secrets" | "regulated"

<ComplianceRegime>   ::= "GDPR" | "SOX" | "HIPAA" | "PCI-DSS" | "ISO27001"
                       | "SOC2" | "NIST-800-53" | "CCPA"

;; The set of FieldKinds that REQUIRE an explicit `pii` declaration.
SENSITIVE_FIELD_KINDS ::= { "email", "phone", "party_ref", "signature",
                            "file", "address", "text", "textarea" }
```

---

## 3. Semantic constraints

These are validated by `model_validator` (parse time) or by the linter (semantic time). A pure parser cannot enforce them.

### 3.1 Object-local (parse time)

| ID | Where | Rule |
|---|---|---|
| **C-pii** | `Field` | If `kind ∈ SENSITIVE_FIELD_KINDS`, then `pii` MUST be present (`true` or `false`). It is an error to omit it. |
| **C-branch** | `EdgeCase` | `handle == "branch"` ⇒ `branch_to` is non-empty. |
| **C-approval-n** | `Approval` | `policy == "n_of_m"` ⇒ `n` is set. |
| **C-approval-tier** | `Approval` | `policy == "authority_tier"` ⇒ `tier` is set. |
| **C-sla-warn** | `Sla.warn_pct` | If present, `1 ≤ warn_pct ≤ 99`. |
| **C-sla-breach** | `Sla.breach_seconds` | If present, `breach_seconds ≥ 60`. |
| **C-bundle-unique-ids** | `Bundle` | All `<JtbdSpec>.id` are unique within `jtbds[]`. |
| **C-spec-hash** | `JtbdSpec.spec_hash` | If present, MUST equal `sha256(canonical_json(hash_body))` where `hash_body` excludes `spec_hash`, `parent_version_id`, `status`, `created_by`, `published_by`. Canonical JSON is RFC-8785-aligned. |
| **C-strict** | every object | Unknown keys are rejected. The canonical models carry `extra='forbid'`; the JSON schema carries `additionalProperties: false`. |

### 3.2 Bundle-wide (linter)

These run during `flowforge jtbd lint`. The linter is described in [`docs/jtbd-editor-arch.md`](jtbd-editor-arch.md) §2.5; the implementation lives in [`flowforge_jtbd.lint`](../python/flowforge-jtbd/src/flowforge_jtbd/lint/).

| Rule id | Severity | Rule |
|---|---|---|
| `requires_unknown_jtbd` | error | Every entry in `JtbdSpec.requires` must reference an `id` in the same bundle. |
| `duplicate_requires` | warning | An id repeated in `requires`. |
| `requires_self` | error | A spec lists its own id in `requires`. |
| `cycle_detected` | error | The dependency graph induced by `requires` must be acyclic. Detection uses iterative Tarjan's SCC; self-loops count. |
| `missing_required_stage` | error | Each spec must cover the five required stages (`discover`, `execute`, `error_handle`, `report`, `audit`) directly or by delegation (`stages: [{name: audit, handled_by: <other_id>}]`). The optional `undo` stage emits `optional_stage_recommended` (info) when missing. |
| `stage_delegation_unresolved` | error | Delegating to a JTBD that is not in the bundle. |
| `stage_delegation_unfulfilled` | error | Delegating to a JTBD that is in the bundle but does not declare the stage itself. |
| `duplicate_stage` | warning | A stage name appears more than once on one spec. |
| `actor_role_undeclared` | warning | `actor.role` is not in `bundle.shared.roles`. |
| `actor_authority_insufficient` | error | `actor.tier > bundle.shared.roles[actor.role].default_tier`. |
| `actor_role_conflict` | warning | The same `(role, context)` pair acts in two conflicting capacities. The default conflict pairs are `{creator, approver}`, `{submitter, approver}`, `{requester, approver}`, `{author, reviewer}`. Per-domain rule packs may extend this set. |

The linter additionally computes a topological order over `requires` (Kahn's algorithm with alphabetical tiebreak for deterministic output). The order is `null` when a cycle is detected.

### 3.3 Pluggable rule packs

Per-domain packs (e.g. `flowforge-jtbd-banking`, `flowforge-jtbd-healthcare`) register additional rules through `RuleRegistry.register()`. Examples:

- A spec declaring `compliance: [SOX]` must declare both `audit` AND `undo` stages.
- A spec declaring `compliance: [HIPAA]` must declare `data_sensitivity: [PHI]`.
- A spec declaring `data_capture` with `kind: signature` must list at least one approval lane.

Rule-pack rules are not part of jtbd-1.0 itself; they are layered at lint time and a bundle without the pack is unaffected.

---

## 4. Lint-side compatibility

The lint-facing model `JtbdLintSpec` ([`flowforge_jtbd.spec`](../python/flowforge-jtbd/src/flowforge_jtbd/spec.py)) keeps `extra='allow'` and uses `jtbd_id` instead of `id`. The CLI adapter at [`flowforge_cli.commands.jtbd_lint`](../python/flowforge-cli/src/flowforge_cli/commands/jtbd_lint.py) translates the on-disk vocabulary before lint:

- `JtbdSpec.id` → `JtbdLintSpec.jtbd_id`
- `Bundle.project.name` → `JtbdLintSpec.bundle_id`
- `Bundle.shared.roles` (list) → `Bundle.shared_roles` (dict, keyed by role name)
- Missing `version` defaults to `"1.0.0"` (pre-E-1 bundles).

The lint side also accepts a `stages: [<StageDecl>]` field per spec, where each `StageDecl` is `{ name: <str>!, handled_by: <str>? }`. Authors writing against the canonical schema can include `stages` thanks to `extra='allow'` on the lint side; canonical jtbd-1.0 itself does not yet promote `stages` to a first-class field.

---

## 5. Hashing and content addressing

### 5.1 spec_hash

Per `JtbdSpec.compute_hash()`:

```
spec_hash := "sha256:" + lowercase_hex( sha256( canonical_json( hash_body() ) ) )

hash_body() := dump(self) - { spec_hash, parent_version_id, status,
                              created_by, published_by }
```

Canonical JSON is RFC-8785-aligned: sorted keys, no insignificant whitespace, UTF-8, integers as the shortest valid representation. Two processes computing the hash on the same logical spec produce byte-identical output regardless of dict iteration order.

### 5.2 Lockfile

A lockfile (`JtbdLockfile`) pins the resolved bundle composition by content hash. Its canonical body is restricted to an explicit allow-list (`_BODY_KEYS`, audit J-08); new top-level fields require explicit registration before they participate in the hash. This prevents accidental hash-set inflation on minor releases.

---

## 6. Worked example

A minimum legal bundle:

```json
{
  "project": {
    "name": "minimal",
    "package": "minimal",
    "domain": "demo"
  },
  "jtbds": [
    {
      "id": "do_the_thing",
      "actor": { "role": "operator" },
      "situation": "Operator needs to do the thing.",
      "motivation": "Doing the thing is the job.",
      "outcome": "The thing is done.",
      "success_criteria": ["The thing was done."]
    }
  ]
}
```

Adding one field that is sensitive without `pii` would be rejected at parse time (constraint **C-pii**):

```json
{
  "data_capture": [
    { "id": "claimant_name", "kind": "text", "required": true }
    /* parse error: kind 'text' is in SENSITIVE_FIELD_KINDS;
       pii must be declared explicitly (true or false). */
  ]
}
```

Three fully worked bundles ship with the framework: [`examples/insurance_claim/`](../examples/insurance_claim/), [`examples/hiring-pipeline/`](../examples/hiring-pipeline/), [`examples/building-permit/`](../examples/building-permit/).

---

## 7. Validation entry points

| Layer | Code | What it checks |
|---|---|---|
| Schema | `JtbdBundle.model_validate(raw)` ([`spec.py`](../python/flowforge-jtbd/src/flowforge_jtbd/dsl/spec.py)) | Lexical + structural + object-local semantic (C-pii, C-branch, C-approval-*, C-bundle-unique-ids). |
| JSON schema | [`jtbd-1.0.schema.json`](../python/flowforge-core/src/flowforge/dsl/schema/jtbd-1.0.schema.json) | Same as above for non-Python clients (the TS designer / `flowforge-jtbd-editor`). |
| Linter | `flowforge jtbd lint` ([`linter.py`](../python/flowforge-jtbd/src/flowforge_jtbd/lint/linter.py)) | Bundle-wide semantic (requires graph, lifecycle completeness, actor consistency, pluggable rules). |
| Hash | `JtbdSpec.compute_hash()` ([`canonical.py`](../python/flowforge-jtbd/src/flowforge_jtbd/dsl/canonical.py)) | Bytes-identity over the body. |
| CI | [`.github/workflows/jtbd-lint.yml`](../.github/workflows/jtbd-lint.yml) | Runs `flowforge jtbd lint --strict?` on every `*jtbd*bundle*.{json,yaml}` in the tree. |

A bundle that passes all four is well-formed, complete, internally consistent, and content-addressable.
