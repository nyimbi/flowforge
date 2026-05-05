# @flowforge/designer changelog

## 0.1.0 — U18

- ReactFlow canvas with click-to-select state/transition wiring.
- Property panel with editors for state metadata, transitions, gates,
  escalation, delegation, required documents, and checklists.
- Drag-and-drop form builder with field palette, preview pane, per-field
  property panel, and conditional rules editor.
- Zustand store with `zundo` temporal middleware (undo/redo, partialized to
  the working DSL).
- Validation panel mirroring `flowforge.compiler.validator` rules.
- Simulation panel that walks a comma- or whitespace-separated event list
  through the current workflow.
- Diff viewer for two workflow versions.
- Vitest + React Testing Library suite covering store, validators,
  simulator, diff, and full Designer integration paths.

## 0.0.0

- Package skeleton scaffolded; implementation pending in dedicated unit.
