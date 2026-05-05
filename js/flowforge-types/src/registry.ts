/**
 * Step registry shape — describes how step-kind strings map to lazy-loadable
 * components that implement WorkflowStepProps.
 */
import type { WorkflowStepProps } from "./workflow_step.js";

/** Minimal component type compatible with React.ComponentType without importing React. */
export type ComponentLike<TProps> = (props: TProps) => unknown;

/** Entry stored in the registry for a single step kind. */
export interface StepRegistryEntry<TMeta = unknown> {
  /** Logical kind string, e.g. "manual_review", "form", "document_review". */
  kind: string;
  /** Factory that returns a promise resolving to the component. Enables code-splitting. */
  load: () => Promise<{ default: ComponentLike<WorkflowStepProps<TMeta>> }>;
  /** Optional human-readable display name for tooling / designer UI. */
  displayName?: string;
}

/** The registry map: kind -> entry. */
export type StepRegistry = Map<string, StepRegistryEntry>;
