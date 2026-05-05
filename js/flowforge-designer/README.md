# @flowforge/designer

Visual designer for flowforge workflows and forms. Renders a ReactFlow canvas, a
property panel for state / transition / gate / escalation / delegation /
document / checklist editing, a drag-and-drop form builder, plus validation,
simulation, and diff panels — all backed by a Zustand store with undo/redo via
the `zundo` temporal middleware.

## Install

This package is not published. Inside the framework workspace it is consumed via
`pnpm` workspace links.

```jsonc
{
  "dependencies": {
    "@flowforge/designer": "workspace:*"
  }
}
```

## Quick start

```tsx
import { Designer, sampleWorkflow } from "@flowforge/designer";

export const App = () => (
  <Designer workflow={sampleWorkflow()} />
);
```

## Tabs

- **canvas** — ReactFlow render of the workflow with click-to-select.
- **form** — palette + canvas + preview pane + per-field property panel with
  conditional rules editor.
- **validation** — static checks mirroring `flowforge.compiler.validator`.
- **simulation** — fire a sequence of events and watch the trace land in a
  state.
- **diff** — pass `compareTo={otherWorkflow}` to render a structural diff.

## Store

```ts
import { createDesignerStore } from "@flowforge/designer";

const store = createDesignerStore({ workflow });
store.getState().addState({ id: "approved", name: "Approved", kind: "task" });
store.temporal.getState().undo();
```

The store is a vanilla Zustand store wrapped with `zundo`. Selection state is
intentionally excluded from the temporal partial so cursor moves do not consume
undo slots.

## Tests

```sh
pnpm --filter @flowforge/designer test
```

Vitest + React Testing Library + happy-dom. The Designer accepts
`withReactFlow={false}` to skip ReactFlow's measured DOM paths in unit tests
while keeping click-and-commit assertions intact.

## Scope notes

- No reactflow-pro features.
- No direct REST or WebSocket calls — that belongs to `@flowforge/runtime-client`.
- Types live locally until `@flowforge/types` (U14) ships, at which point the
  designer will re-export from there.
