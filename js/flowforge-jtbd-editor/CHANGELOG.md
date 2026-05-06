# @flowforge/jtbd-editor changelog

## 0.1.0 — Unreleased

- E-6: visual job map.
  - `layoutJobMap(bundle)` — deterministic swimlane layout: one lane
    per actor role (first-appearance order), topological columns
    across `requires` edges, cycle detection that marks every node in
    an SCC.
  - `JobMap` React component with two render modes — `<ReactFlow>`
    for production, SVG fallback for happy-dom unit tests.
  - Click + Enter / Space keyboard handlers invoke `onSelectJtbd`.
  - Cross-lane edges paint distinctly so the dependency hop is
    visually obvious.
  - Layout pass meets the 200-JTBD perf budget called out in
    `framework/docs/jtbd-editor-arch.md` §17.
