# @flowforge/jtbd-editor changelog

## 0.1.0 — Unreleased

- E-11: visual swimlane animation.
  - `buildDefaultTrace(bundle)` — Kahn topological order that lands
    cycle members at the end (animation never deadlocks).
  - `buildTraceFromEvents(bundle, events)` — replay a captured event
    list; unknown ids dropped, repeats preserved.
  - `animationReducer(state, action, trace)` — pure state machine
    (play / pause / reset / step_forward / step_back / seek). No
    timers, no DOM. Total over every state × action; clamped seeks.
  - `JobMapAnimation` — React component layering a play/step/reset
    toolbar plus a replay slider on top of `JobMap`. `tickMs` controls
    the play-loop interval. `autoplay`, `onStepChange` callbacks.
  - `JobMap` gains `firedIds` / `activeIds` props plus
    `data-animation-state` so the canvas highlights the currently-
    active node and fades the visited ones.
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
