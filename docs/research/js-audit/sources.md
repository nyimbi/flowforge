# Sources Examined

No external web sources were used. This audit is based on local repository files, codebase-memory search results, and the requested local build/lint commands.

## Commands

- `find . -maxdepth 3 -name AGENTS.md -o -name package.json -o -name pnpm-workspace.yaml -o -name tsconfig.json`
- `find js -maxdepth 3 \( -name package.json -o -name index.ts -o -name index.tsx -o -name App.tsx -o -name tsconfig.json -o -name vite.config.ts \) | sort`
- `git status --short`
- `(cd js && pnpm -r build 2>&1 | tail -20)`
- `(cd js && pnpm -r --if-present lint 2>&1 | tail -20)`
- Codebase-memory indexed project status for `Users-nyimbiodero-src-pjs-flowforge`
- Codebase-memory searches for public exports and unsafe patterns across `js/flowforge-*`

## Workspace Config

- `js/package.json`
- `js/pnpm-workspace.yaml`

## Package Config

- `js/flowforge-designer/package.json`
- `js/flowforge-designer/tsconfig.json`
- `js/flowforge-integration-tests/package.json`
- `js/flowforge-integration-tests/tsconfig.json`
- `js/flowforge-jtbd-editor/package.json`
- `js/flowforge-jtbd-editor/tsconfig.json`
- `js/flowforge-renderer/package.json`
- `js/flowforge-renderer/tsconfig.json`
- `js/flowforge-runtime-client/package.json`
- `js/flowforge-runtime-client/tsconfig.json`
- `js/flowforge-step-adapters/package.json`
- `js/flowforge-step-adapters/tsconfig.json`
- `js/flowforge-types/package.json`
- `js/flowforge-types/tsconfig.json`

## Entrypoints Requested

- `js/flowforge-types/src/index.ts`
- `js/flowforge-renderer/src/index.ts`
- `js/flowforge-designer/src/index.ts`
- `js/flowforge-jtbd-editor/src/index.ts`
- `js/flowforge-step-adapters/src/index.ts`

## Types Package

- `js/flowforge-types/src/form_spec.ts`
- `js/flowforge-types/src/jtbd.ts`
- `js/flowforge-types/src/registry.ts`
- `js/flowforge-types/src/workflow_def.ts`
- `js/flowforge-types/src/workflow_step.ts`
- `js/flowforge-types/scripts/gen.ts`

## Renderer Package

- `js/flowforge-renderer/src/FormRenderer.tsx`
- `js/flowforge-renderer/src/expr.ts`
- `js/flowforge-renderer/src/types.ts`
- `js/flowforge-renderer/src/validators/ajv.ts`
- `js/flowforge-renderer/src/fields/common.tsx`
- `js/flowforge-renderer/src/fields/TextAreaField.tsx`
- `js/flowforge-renderer/src/fields/LookupField.tsx`
- `js/flowforge-renderer/src/fields/FileField.tsx`
- `js/flowforge-renderer/src/fields/JsonField.tsx`
- `js/flowforge-renderer/src/fields/TextField.tsx`

## Designer Package

- `js/flowforge-designer/src/Designer.tsx`
- `js/flowforge-designer/src/Canvas.tsx`
- `js/flowforge-designer/src/store.ts`
- `js/flowforge-designer/src/PropertyPanel.tsx`
- `js/flowforge-designer/src/FormBuilder.tsx`
- `js/flowforge-designer/src/ValidationPanel.tsx`
- `js/flowforge-designer/src/SimulationPanel.tsx`
- `js/flowforge-designer/src/validation.ts`
- `js/flowforge-designer/src/simulation.ts`
- `js/flowforge-designer/src/DiffViewer.tsx`
- `js/flowforge-designer/src/diff.ts`
- `js/flowforge-designer/src/ReviewPanel.tsx`
- `js/flowforge-designer/src/ForkButton.tsx`
- `js/flowforge-designer/src/CommentThread.tsx`
- `js/flowforge-designer/src/JobMap/JobMap.tsx`

## JTBD Editor Package

- `js/flowforge-jtbd-editor/src/JobMap.tsx`
- `js/flowforge-jtbd-editor/src/JobMapAnimation.tsx`
- `js/flowforge-jtbd-editor/src/layout.ts`
- `js/flowforge-jtbd-editor/src/animation.ts`
- `js/flowforge-jtbd-editor/src/trace.ts`
- `js/flowforge-jtbd-editor/src/types.ts`

## Step Adapters Package

- `js/flowforge-step-adapters/src/registry.ts`
- `js/flowforge-step-adapters/src/useActionInterceptor.ts`
- `js/flowforge-step-adapters/src/withReadOnly.tsx`
- `js/flowforge-step-adapters/src/ManualReviewStep.tsx`
- `js/flowforge-step-adapters/src/FormStep.tsx`
- `js/flowforge-step-adapters/src/DocumentReviewStep.tsx`

## Runtime Client Package

- `js/flowforge-runtime-client/src/index.ts`
- `js/flowforge-runtime-client/src/client.ts`
- `js/flowforge-runtime-client/src/ws.ts`
- `js/flowforge-runtime-client/src/hooks/useFlowforgeWorkflow.ts`
- `js/flowforge-runtime-client/src/hooks/useTenantQueryKey.ts`

## Integration Tests

- `js/flowforge-integration-tests/designer-runtime-integration.spec.ts`
- `js/flowforge-integration-tests/renderer-form-flow.spec.tsx`
- `js/flowforge-integration-tests/use-flowforge-workflow.test.tsx`
- `js/flowforge-integration-tests/ws-reconnect-collab.test.ts`

## Tests and File Listings Considered

These were listed as package test coverage or package file inventory during the audit:

- `js/flowforge-types/__tests__/types.test.ts`
- `js/flowforge-renderer/__tests__/FormRenderer.test.tsx`
- `js/flowforge-renderer/__tests__/expr.test.ts`
- `js/flowforge-renderer/__tests__/validators.test.ts`
- `js/flowforge-designer/__tests__/E_62_acceptance.test.tsx`
- `js/flowforge-designer/__tests__/designer.test.tsx`
- `js/flowforge-jtbd-editor/__tests__/animation.test.tsx`
- `js/flowforge-jtbd-editor/__tests__/jobmap-virtualisation.test.tsx`
- `js/flowforge-jtbd-editor/__tests__/jobmap.test.tsx`
- `js/flowforge-step-adapters/__tests__/steps.test.tsx`
- `js/flowforge-runtime-client/__tests__/client.test.ts`
- `js/flowforge-integration-tests/expr-parity.test.ts`
- `js/flowforge-integration-tests/private-ratchet.test.ts`
- `js/flowforge-integration-tests/step-adapter-runtime.spec.tsx`
- `js/flowforge-integration-tests/vitest.config.ts`
- `js/flowforge-integration-tests/vitest.setup.ts`

