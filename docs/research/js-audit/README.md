# Flowforge JS Package Audit

Date: 2026-07-08

Scope: JS workspace packages under `js/`. The mission paths used `js/packages/<name>`, but this repository stores packages directly under `js/<name>`. The designer and JTBD editor entrypoints are `src/index.ts`, not `index.tsx`; no package-level `App.tsx` entry was present.

## Verification

Requested commands:

```text
$ (cd js && pnpm -r build 2>&1 | tail -20)
Scope: 7 of 8 workspace projects
flowforge-designer build$ tsc --noEmit
flowforge-jtbd-editor build$ tsc --noEmit
flowforge-runtime-client build$ tsc --noEmit
flowforge-types build$ tsc --noEmit
flowforge-runtime-client build: Done
flowforge-types build: Done
flowforge-jtbd-editor build: Done
flowforge-designer build: Done
flowforge-renderer build$ tsc -p tsconfig.json --noEmit
flowforge-step-adapters build$ tsc --noEmit
flowforge-step-adapters build: Done
flowforge-renderer build: Done
flowforge-integration-tests build$ tsc --noEmit
flowforge-integration-tests build: Done
```

```text
$ (cd js && pnpm -r --if-present lint 2>&1 | tail -20)
Scope: 7 of 8 workspace projects
flowforge-designer lint$ tsc --noEmit
flowforge-types lint$ tsc --noEmit
flowforge-runtime-client lint$ tsc --noEmit
flowforge-jtbd-editor lint$ tsc --noEmit
flowforge-runtime-client lint: Done
flowforge-types lint: Done
flowforge-jtbd-editor lint: Done
flowforge-designer lint: Done
flowforge-renderer lint$ tsc -p tsconfig.json --noEmit
flowforge-step-adapters lint$ tsc --noEmit
flowforge-step-adapters lint: Done
flowforge-renderer lint: Done
flowforge-integration-tests lint$ tsc --noEmit
flowforge-integration-tests lint: Done
```

Interpretation: build and lint currently pass, but both are TypeScript `tsc --noEmit` checks. There is no ESLint pass, production bundle check, visual smoke test, or accessibility audit in these two commands.

## Per-Package Assessment

| Package | Purpose | Completeness | Key Gaps and Risks |
| --- | --- | --- | --- |
| `flowforge-js-workspace` | Private workspace root with recursive `build`, `lint`, and `test` scripts plus pnpm workspace config. | Thin workspace orchestrator, not product code. | No central shared TS config, lint config, or package-release policy. Overrides pin several transitive packages, but there is no documented browser support, bundle policy, or security audit command. |
| `@flowforge/types` | Generated TypeScript definitions for workflow definitions, form specs, JTBD bundles, plus step component registry contracts. | Real type surface, but compile-time only. | Not a runtime validator. Generated types still include `unknown` and `{}` pockets. Designer and JTBD editor define divergent local DSL types instead of consuming or adapting these canonical types. |
| `@flowforge/renderer` | React form renderer with field components, conditional expression evaluation, computed fields, async lookups, and AJV validation. | Substantial implementation; the most mature runtime UI package. | `FormRenderer` memoization can hold stale `fieldComponents`/lookup hooks. Computed expression errors are swallowed. Lookup requests fire on every query change with no debounce and do not pass the declared `AbortSignal`. Regex validation from specs can create ReDoS risk if untrusted authors control patterns. Loading exists for submit and lookup, but lookup error and empty-option states are weak. |
| `@flowforge/runtime-client` | Typed REST and WebSocket client with CSRF header support, idempotency keys, retries, timeouts, Zod response parsing, and React-hook helpers. | Real client package with useful tests. | `useFlowforgeWorkflow` records hook handlers on a private `_hookHandlers` set that `FlowforgeWsClient` never dispatches, so WS-triggered refresh is not actually wired. Hook dependency arrays omit `client` in the fetch effect. No auth refresh, tenant mismatch, offline, or server event schema validation beyond raw record envelopes. |
| `@flowforge/step-adapters` | Registry utilities, action interception, read-only wrapper, and generic manual-review/form/document-review step components. | Useful but intentionally thin. | High-priority security gap: `DocumentReviewStep` renders metadata-provided `doc.url` directly in `<a href>`, so `javascript:`, `data:`, or unexpected schemes can be exposed. Components lack pending/error states for async `onAction`, local validation depth, permission-aware disabled reasons, and stronger document preview controls. Package config has React as a direct dependency and lacks `types`/`exports`, increasing duplicate-React and public-surface risk. |
| `@flowforge/designer` | React designer shell with tabs for canvas, form builder, validation, simulation, diff, plus Zustand/Zundo store, comments, review, fork, and job-map exports. | More than a stub, but still a prototype/workbench rather than world-class workflow designer. | Canvas is mostly read/select: no node palette, `onConnect`, `onNodesChange`, persisted positions, multi-select, keyboard layer, copy/paste, lasso, graph import/export, or save/publish workflow. Toolbar calls raw zundo `undo`/`redo`, bypassing exported `safeUndo`/`safeRedo` conflict messaging. Validation is list-only and not clickable/actionable. Simulation ignores guards/context. Error boundaries, loading states, save states, and full accessibility semantics are missing. Local workflow/form types diverge from `@flowforge/types`. |
| `@flowforge/jtbd-editor` | JTBD dependency/job-map visualization with deterministic swimlane layout, ReactFlow canvas, SVG fallback, virtualization in fallback mode, cycle highlighting, and replay controls. | Solid visualization/replay package, not an editor yet. | No authoring forms, validation panel, diff/merge, persistence, comments/review integration, or publish workflow. Virtualization is only applied to SVG fallback mode; default ReactFlow mode maps all nodes and edges. SVG edge rendering performs per-edge node lookup. Empty/error/loading states are minimal. Types restate a partial JTBD schema locally. |
| `@flowforge/integration-tests` | Cross-package tests for designer-runtime flow, renderer form flow, step adapters, runtime hook, WS reconnect/collab, expression parity, and private API ratchets. | Real test package, useful as a guardrail. | Several tests are smoke-level. Example: renderer submit wiring accepts "no crash" rather than asserting a submitted payload, and React hook coverage does not prove WS-triggered refresh. No visual regression, axe/accessibility, bundle-size, large-graph default ReactFlow performance, or security regression tests for unsafe URLs/regex. |

## Security Assessment

No `dangerouslySetInnerHTML`, `eval`, `new Function`, direct `innerHTML`, browser storage, or unsafe storage usage was found in the inspected package source.

Material issues:

1. `@flowforge/step-adapters`: `DocumentReviewStep` renders `doc.url` directly as an anchor `href`. `rel="noopener noreferrer"` prevents tabnabbing but does not block `javascript:` or `data:` URLs. Add URL parsing, scheme/origin allowlisting, and regression tests.
2. `@flowforge/renderer`: spec-controlled regex patterns are compiled into AJV schemas. If workflow/form authors are untrusted, this needs pattern vetting or a safe-regex policy to reduce ReDoS risk.
3. `@flowforge/renderer`: computed expression failures are swallowed in `computeAll`, so invalid computed specs can produce missing or stale submitted data without visible evidence.
4. `@flowforge/designer`: collaboration-aware `safeUndo`/`safeRedo` exists but is not used by the visible toolbar. This can hide conflict feedback from users.
5. `@flowforge/runtime-client`: WebSocket envelopes are parsed as untyped records; event-specific validation is absent. Invalid frames are ignored or forwarded without schema checks.

## Performance Assessment

Key hot spots:

1. `@flowforge/jtbd-editor` maps every layout node/edge into ReactFlow nodes/edges in the default path. Fallback virtualization does not protect normal production usage.
2. `@flowforge/jtbd-editor` SVG fallback edge rendering uses `layout.nodes.find` for each edge endpoint, creating avoidable O(E * N) work.
3. `@flowforge/renderer` recomputes computed fields and conditional visibility during render and on changes. This is acceptable for small forms, but large forms need profiling, dependency-indexed recomputation, and stable memo dependencies.
4. `@flowforge/renderer` lookup fields call async lookup on every query change. Add debounce, stale-result handling, and explicit lookup error/empty states.
5. `@flowforge/designer` canvas positions are generated from array index and not persisted, so larger workflows cannot preserve user layout work or avoid full relayout churn.

## Error, Loading, and Empty States

Present:

- Renderer submit button loading state.
- Lookup field loading text.
- Form builder empty text for no fields.
- Validation panel clean state.
- Diff viewer empty/no-compare states.
- Runtime hook `isLoading` and `error`.

Missing or weak:

- Designer-level error boundary.
- JTBD editor loading, empty bundle, invalid bundle, and layout-error states.
- Async action pending/error states in step adapters.
- Save/autosave/publish/loading/error states in designer.
- Lookup failure and no-results distinction.
- Permission/read-only explanations.
- Recovery flow for bad imported JSON or incompatible workflow versions.

## TypeScript Strictness Gaps

The workspace broadly uses `strict: true`, and the requested build/lint checks pass. Remaining gaps:

- `skipLibCheck: true` is enabled across package configs.
- `@flowforge/runtime-client` sets `exactOptionalPropertyTypes: false`.
- `@flowforge/step-adapters` lacks `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `types`, and `exports`; React is a direct dependency rather than a peer.
- Most packages export source `.ts` files instead of built declarations/artifacts.
- Designer and JTBD editor duplicate local DSL types instead of depending on canonical `@flowforge/types` or explicit adapters.
- Generated types contain broad `unknown` and `{}` fields, so compile-time acceptance does not mean runtime-safe input.

## Top 10 UI Improvements for a World-Class Designer/JTBD Editor

1. **Canonical model boundary:** add explicit adapters between designer drafts, JTBD bundles, renderer form specs, and generated `@flowforge/types`; prove import/export round trips with tests.
2. **Editable graph canvas:** implement ReactFlow `onNodesChange`, `onEdgesChange`, `onConnect`, persisted node positions, transition creation, node/edge deletion, and auto-layout.
3. **Workflow palette:** add searchable state templates, transition templates, guard/gate/effect blocks, SLA/escalation blocks, and form-step templates.
4. **Command system:** add keyboard shortcuts, command palette, undo/redo through `safeUndo`/`safeRedo`, delete/duplicate, copy/paste, fit view, zoom, search, and multi-select/lasso.
5. **Inspector-grade property panels:** replace minimal forms with structured state, transition, guard, gate, effect, role, document, SLA, notification, and metadata editors.
6. **Actionable validation:** show schema and semantic validation inline, link each issue to the relevant graph/form field, and support autofix suggestions where safe.
7. **Runtime-accurate preview and simulation:** use `@flowforge/renderer` for form preview, evaluate guards against sample context, animate runtime traces onto the graph, and show failed transition reasons.
8. **Persistence and collaboration:** add draft autosave, dirty-state tracking, import/export, publish/version workflow, remote patch conflict UI, comments, review decisions, and presence.
9. **Accessibility and responsive UX:** implement real tabs/tabpanels, keyboard graph navigation, focus management, screen-reader outline mode, high-contrast states, and responsive inspector collapse.
10. **Operational polish:** add loading skeletons, empty canvases with clear actions, error boundaries, offline/retry states, audit/security badges, bundle-size/performance budgets, and visual regression coverage.

## Specific Missing UI Components

- State/node palette and transition connector palette.
- Drag-to-create graph nodes and drag-to-connect transitions.
- Persisted node positioning and auto-layout controls.
- Minimap in the designer canvas.
- Multi-select, lasso select, group/ungroup, duplicate, copy/paste, delete.
- Keyboard shortcut layer and shortcut reference.
- Command palette and searchable workflow outline.
- Undo/redo history drawer using safe collaboration-aware helpers.
- Structured guard, gate, effect, SLA, escalation, notification, and role editors.
- JSON source editor with schema validation and import/export.
- Runtime preview panel using the actual renderer.
- Trace/timeline panel for simulation and replay.
- Clickable validation issue list and inline error badges.
- Save/autosave/publish/version controls.
- Collaboration presence, comments, review queue, and conflict-resolution UI integrated into the main designer.
- Accessibility outline mode for graph readers.
- Loading skeletons, first-run empty states, failed-save states, and package/version incompatibility states.

## Recommended Implementation Order

1. **Fix security and package hygiene first:** sanitize document URLs, move step-adapters React to peer/dev dependencies, add `exports`/`types`, and add regression tests for unsafe URLs.
2. **Unify contracts:** define canonical adapter functions between local designer/JTBD types and `@flowforge/types`; block further UI expansion on round-trip tests.
3. **Make the canvas truly editable:** add node/edge mutation handlers, persisted layout, creation/deletion flows, and undoable graph operations.
4. **Route undo/redo through safe helpers:** wire Designer toolbar and keyboard shortcuts to `safeUndo`/`safeRedo` and show conflict messages.
5. **Upgrade validation:** add schema plus semantic validation for graph, forms, guards, gates, effects, SLAs, and JTBD dependencies; make issues navigable.
6. **Replace preview stubs with runtime components:** use `@flowforge/renderer` in the designer form preview and align simulation with guard/context semantics.
7. **Add persistence and import/export:** implement dirty state, autosave/save, JSON import/export, publish/version controls, and recovery for invalid drafts.
8. **Build command/a11y layer:** command palette, keyboard shortcuts, proper tabs, focus management, graph outline, and screen-reader-friendly alternatives.
9. **Scale performance:** add large-graph tests for default ReactFlow, virtualize/cull normal graph rendering, debounce lookups, and index edge endpoint lookups.
10. **Polish collaboration and lifecycle states:** integrate comments/reviews/presence, add loading/error/empty/read-only states, and add visual/accessibility regression tests.

