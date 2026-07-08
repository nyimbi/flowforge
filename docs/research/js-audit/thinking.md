# Raw Notes

## Scope Normalization

- User requested `js/packages/flowforge-*`; actual repo uses direct package dirs:
  - `js/flowforge-types`
  - `js/flowforge-renderer`
  - `js/flowforge-designer`
  - `js/flowforge-jtbd-editor`
  - `js/flowforge-step-adapters`
  - also present: `js/flowforge-runtime-client`, `js/flowforge-integration-tests`, and root `js/package.json`.
- Designer and JTBD editor entrypoints are `src/index.ts`; no `src/index.tsx` or package `App.tsx` was found in the package listing.
- `git status --short` before edits showed only untracked `.claude/`.

## Requested Command Evidence

Build:

```text
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

Lint:

```text
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

## Static Security Scan Notes

- Searched package source for `dangerouslySetInnerHTML`, `eval(`, `new Function`, `innerHTML`, `localStorage`, `sessionStorage`, `postMessage`, `Function(`.
- No matches in inspected package source.
- React escapes rendered text in normal JSX.
- Highest concrete security issue found: `DocumentReviewStep` renders metadata `doc.url` directly into `<a href>`. `rel="noopener noreferrer"` is present, but URL schemes are not constrained.
- Renderer expression evaluator is whitelisted and does not use eval. Unknown operators return false.
- Renderer AJV schema generation accepts spec-provided regex `pattern`; this is a potential ReDoS risk if form authors are not trusted.
- Rich text field stores `textContent`, not HTML, so current default avoids XSS. Host-provided rich text component overrides need their own policy.

## Package Notes

### `@flowforge/types`

- Entrypoint only re-exports types.
- `form_spec.ts`, `workflow_def.ts`, `jtbd.ts` are generated from Python-side JSON schemas.
- Adds hand-authored `workflow_step.ts` and `registry.ts`.
- Completeness: useful compile-time type package.
- Gaps:
  - No runtime validation.
  - `unknown` and `{}` fields remain.
  - Generated canonical workflow shape uses `key`, `subject_kind`, `version: string`, `from_state`, `to_state`.
  - Designer local shape uses `id`, `name`, `version: number`, `from`, `to`.
  - JTBD editor local shape duplicates part of JTBD schema.

### `@flowforge/renderer`

- Entrypoint exports `FormRenderer`, field components, expression evaluator, AJV validator, and types.
- `FormRenderer`:
  - Controlled/uncontrolled values.
  - default values.
  - compute fields via `evaluate`.
  - AJV validation on submit/change/blur.
  - `submitting` state.
  - field dispatch to many components.
- Real implementation, not a stub.
- Gaps:
  - `computeAll` catches expression errors and ignores them.
  - `sections` memo disables exhaustive deps and may hold stale render dependencies.
  - lookup callback type includes `AbortSignal`, but `makeLookupCallback` does not pass one.
  - lookup field triggers requests on every query change, no debounce.
  - lookup failure collapses to empty options.
  - no general error boundary.
  - no no-fields empty state.
  - AJV `strict: false`; pattern risk if untrusted.

### `@flowforge/runtime-client`

- REST client has CSRF header, cookie credentials, idempotency key, retries, timeout, Zod parsing.
- WebSocket client reconnects with exponential backoff and dispatches to constructor `onEvent`.
- Hook `useFlowforgeWorkflow` dependency-injects React hooks.
- Main bug/gap:
  - hook creates private `_hookHandlers` on `wsClient`, but `FlowforgeWsClient` never reads that set, so WS refresh from hook does not happen.
  - fetch effect deps omit `client`.
  - event envelopes are untyped records.
  - no offline/auth-refresh story.

### `@flowforge/step-adapters`

- Registry, action interceptor, read-only HOC, manual-review step, form step, document-review step.
- Real but minimal.
- `FormStep` is self-contained rather than using renderer.
- `DocumentReviewStep` has unsafe direct metadata URL rendering.
- Components do not handle async `onAction` loading/error states.
- `actorRoles` unused in manual review despite being passed.
- Package config lacks `exports` and `types`; React is direct dependency.

### `@flowforge/designer`

- Entrypoint exports many components and store utilities.
- `Designer` tabs: canvas, form, validation, simulation, diff.
- `Canvas` renders ReactFlow nodes/edges and click selection.
- `Canvas` positions nodes by index; no persisted positions.
- No `onNodesChange`, `onEdgesChange`, `onConnect`, node add palette, edge creation, or keyboard layer.
- `store.ts` has add/update/remove for states, transitions, fields; zundo temporal history.
- `safeUndo`/`safeRedo` and `applyRemotePatch` exist, but `Designer` toolbar calls raw temporal `undo`/`redo`.
- `FormBuilder` has field palette, drag reorder, preview, properties, enum options, conditional rules.
- Form preview is hand-rendered and narrower than `@flowforge/renderer`.
- `ValidationPanel` lists issues only.
- `SimulationPanel` does linear event replay; guard expressions are explicitly not evaluated.
- `ReviewPanel`, `CommentThread`, `ForkButton` are headless and exported but not integrated into main designer.
- Missing: persistence, save/publish, import/export, command palette, shortcuts, a11y graph outline, error boundary, loading/saving states.

### `@flowforge/jtbd-editor`

- Entrypoint exports JobMap, animation, layout, trace, sample fixture, local JTBD types.
- `JobMap`:
  - deterministic layout.
  - ReactFlow default path with Background/Controls/MiniMap.
  - SVG fallback with virtualisation threshold 200.
  - nodes support Enter/Space in fallback mode.
  - cycle nodes always retained in fallback viewport filter.
- Real visualization/replay package.
- Not a full editor:
  - no create/edit forms.
  - no validation panel.
  - no import/export/save.
  - no comments/review integration.
  - no diff/merge.
- Perf gap:
  - default ReactFlow path maps all nodes/edges and is not virtualized.
  - fallback edge component finds source/target through `layout.nodes.find` per edge.

### `@flowforge/integration-tests`

- Cross-package tests exist and are useful.
- Reviewed examples:
  - designer-runtime integration via MSW.
  - renderer form flow.
  - runtime hook React 19 mount.
  - WS reconnect/collab conflict.
- Gaps:
  - smoke-level assertions in places.
  - no URL-scheme security tests.
  - no accessibility tests.
  - no visual regression.
  - no default ReactFlow large-graph performance tests.

## Subagent Findings Integrated

- Code review lane found:
  - HIGH: unsafe `doc.url` rendered directly in `DocumentReviewStep`.
  - MEDIUM: local designer/JTBD types diverge from canonical generated types.
  - MEDIUM: `FormRenderer` memoization can retain stale components/lookups.
  - MEDIUM: computed expression errors swallowed.
  - MEDIUM: JTBD JobMap virtualization does not cover default ReactFlow path.
  - MEDIUM: step-adapters package config can duplicate React and lacks typed export surface.
- UI/design lane found:
  - Designer shell exists but graph canvas is read/select, not authoring-grade.
  - Form builder is more complete than graph editing.
  - JTBD editor is stronger as visualization/replay than as editing surface.
  - Collaboration/review components are present but not integrated.
  - Validation/simulation are lightweight and not actionable enough.

## Recommended Priority Rationale

1. Security fix first because unsafe href can become direct script/navigation exposure.
2. Contract alignment before building more UI avoids deepening schema divergence.
3. Editable graph core is the central product missing piece.
4. Undo/redo safety should be wired before collaboration/persistence expansion.
5. Validation and runtime preview should be authoritative before publish/save workflows.
6. Performance and a11y need acceptance tests before calling the designer world-class.

