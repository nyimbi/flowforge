# @flowforge/jtbd-editor

E-6 / E-11 deliverable: the visual job map plus its replay animation
for the JTBD editor.

A `JobMap` React component renders a `JtbdBundle` as a swimlane
canvas — one horizontal lane per actor role, one box per JTBD, edges
between JTBDs that declare `requires`. The layout is pure
(`layoutJobMap`), deterministic, and exposed for downstream callers
that want to drive their own renderer (Storybook, snapshot tests, the
debugger panel in E-3).

A `JobMapAnimation` component layers a play/pause/step/seek toolbar
over the canvas and walks a `Trace` of firing JTBDs, highlighting the
active step and fading already-fired ones (the "fired" colour) so the
author can follow the dependency graph executing.

## Surfaces

- `JobMap` — the React component. Accepts optional `firedIds` /
  `activeIds` props for animated overlays.
- `JobMapAnimation` — replay-ready wrapper with controls + slider.
- `layoutJobMap(bundle) -> JobMapLayout` — the pure layout function.
- `buildDefaultTrace(bundle)` and `buildTraceFromEvents(bundle, events)`
  — turn a bundle into a firing-order trace.
- `animationReducer` + `initialAnimationState` — the pure state
  machine driving the replay.
- TS types mirroring the canonical JTBD bundle shape from the Python
  `flowforge_jtbd.dsl` package.
- `sampleBundle()` — a worked example used by tests and Storybook.

## Render modes

```tsx
import { JobMap, sampleBundle } from "@flowforge/jtbd-editor";

<JobMap bundle={sampleBundle()} onSelectJtbd={(id) => console.log(id)} />
```

```tsx
import { JobMapAnimation, sampleBundle } from "@flowforge/jtbd-editor";

<JobMapAnimation
  bundle={sampleBundle()}
  tickMs={500}
  autoplay
  onStepChange={(state) => console.log(state.currentIndex)}
/>
```

In tests, pass `withReactFlow={false}` so the SVG fallback renders
without dragging in reactflow's measurement path. The fallback emits
the same `data-testid` markers as the React Flow path so assertions
stay portable. For `JobMapAnimation`, drive the play loop with
`vi.useFakeTimers()` + `vi.advanceTimersByTime(tickMs)`.

## Tests

```
pnpm --filter @flowforge/jtbd-editor test
```

## Out of scope

- Drag-to-reorder (E-7).
- Glossary / ontology overlay (E-8).
- Animation / debugger replay (E-3).
- Marketplace install (E-6/E-21 of evolution.md).
