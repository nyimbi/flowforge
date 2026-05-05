# @flowforge/renderer

React 19 form renderer that consumes a `FormSpec` JSON document and renders a
working form, complete with validation, conditional fields, computed values,
and pluggable async lookup hooks. See `docs/workflow-framework-portability.md`
§3.2 for the broader scope.

## Quick start

```tsx
import { FormRenderer } from "@flowforge/renderer";

const spec = {
  id: "claim_intake",
  version: "1.0.0",
  title: "File a claim",
  fields: [
    { id: "claimant_name", kind: "text", label: "Claimant", required: true },
    { id: "claimant_email", kind: "email", label: "Email", required: true },
    { id: "amount", kind: "money", label: "Amount", validation: { currency: "USD" } },
    { id: "incident_date", kind: "date", label: "Incident date", required: true },
    {
      id: "category",
      kind: "enum",
      label: "Category",
      options: [{ v: "auto" }, { v: "home" }],
      required: true,
    },
  ],
};

<FormRenderer
  spec={spec}
  onSubmit={async (values) => api.intake.submit(values)}
/>;
```

## Supported field kinds

`text`, `textarea`, `rich_text`, `number`, `money`, `percentage`, `date`,
`datetime`, `boolean`, `enum`, `multi_select`, `file`, `signature`,
`party_picker` / `party_ref`, `document_picker` / `document_ref`, `address`,
`phone`, `email`, `url`, `color`, `json`, `hidden`, `lookup`.

Hosts can override any kind through `<FormRenderer fieldComponents={...} />`.

## Conditional logic + computed fields

Each field can declare expression-driven `visible_if`, `required_if`,
`disabled_if`, and `computed.expr` clauses. The expression DSL mirrors the
operators in `flowforge-core`:

```json
{ "id": "tax_id", "kind": "text", "visible_if": { "==": ["$.kind", "company"] } }
```

```json
{ "id": "total", "kind": "number", "computed": { "expr": { "*": ["$.qty", "$.price"] } } }
```

## Async lookup hooks

```tsx
<FormRenderer
  spec={spec}
  lookups={{
    parties: async ({ query, signal }) => {
      const res = await fetch(`/api/parties?q=${query ?? ""}`, { signal });
      return res.json();
    },
  }}
/>;
```

A field opts in via `source.hook`:

```json
{ "id": "claimant_id", "kind": "lookup", "source": { "hook": "parties" } }
```

## Validation

`buildValidator(spec)` produces an Ajv-backed validator. The renderer uses it
internally on submit and (optionally) on blur or change.

## Testing

```bash
pnpm --filter @flowforge/renderer test
```

Vitest + `@testing-library/react` cover the field set, conditional logic,
computed fields, async lookups, ajv validation, and submit gating.
