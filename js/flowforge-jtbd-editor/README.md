# @flowforge/jtbd-editor

E-6 deliverable: the visual job map for the JTBD editor.

A `JobMap` React component renders a `JtbdBundle` as a swimlane
canvas — one horizontal lane per actor role, one box per JTBD, edges
between JTBDs that declare `requires`. The layout is pure
(`layoutJobMap`), deterministic, and exposed for downstream callers
that want to drive their own renderer (Storybook, snapshot tests, the
debugger panel in E-3).

## Surfaces

- `JobMap` — the React component.
- `layoutJobMap(bundle) -> JobMapLayout` — the pure layout function.
- TS types mirroring the canonical JTBD bundle shape from the Python
  `flowforge_jtbd.dsl` package.
- `sampleBundle()` — a worked example used by tests and Storybook.

## Render modes

```tsx
import { JobMap, sampleBundle } from "@flowforge/jtbd-editor";

<JobMap bundle={sampleBundle()} onSelectJtbd={(id) => console.log(id)} />
```

In tests, pass `withReactFlow={false}` so the SVG fallback renders
without dragging in reactflow's measurement path. The fallback emits
the same `data-testid` markers as the React Flow path so assertions
stay portable.

## Tests

```
pnpm --filter @flowforge/jtbd-editor test
```

## Out of scope

- Drag-to-reorder (E-7).
- Glossary / ontology overlay (E-8).
- Animation / debugger replay (E-3).
- Marketplace install (E-6/E-21 of evolution.md).
