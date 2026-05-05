/**
 * Step registry: maps kind strings to lazy-loadable step components.
 *
 * Usage:
 *   registry.register({ kind: "manual_review", load: () => import("./ManualReviewStep.js") });
 *   const Comp = await loadStep(registry, "manual_review");
 */
import type { ComponentType } from "react";
import type {
  StepRegistry,
  StepRegistryEntry,
  WorkflowStepProps,
} from "@flowforge/types";

/** Create a new empty registry. */
export function createRegistry(): StepRegistry {
  return new Map<string, StepRegistryEntry>();
}

/**
 * Register a step kind. Overwrites any existing entry for the same kind.
 * Returns the registry for chaining.
 */
export function registerStep<TMeta = unknown>(
  registry: StepRegistry,
  entry: StepRegistryEntry<TMeta>,
): StepRegistry {
  registry.set(entry.kind, entry as StepRegistryEntry);
  return registry;
}

/**
 * Remove a step kind from the registry.
 * Returns true if the kind was present, false otherwise.
 */
export function unregisterStep(registry: StepRegistry, kind: string): boolean {
  return registry.delete(kind);
}

/** Return all registered kind strings. */
export function registeredKinds(registry: StepRegistry): string[] {
  return Array.from(registry.keys());
}

/**
 * Dynamically import a step component by kind.
 * Throws if the kind is not registered.
 */
export async function loadStep<TMeta = unknown>(
  registry: StepRegistry,
  kind: string,
): Promise<ComponentType<WorkflowStepProps<TMeta>>> {
  const entry = registry.get(kind);
  if (!entry) {
    throw new Error(
      `@flowforge/step-adapters: unknown step kind "${kind}". ` +
        `Registered kinds: [${registeredKinds(registry).join(", ")}]`,
    );
  }
  const mod = await entry.load();
  return mod.default as ComponentType<WorkflowStepProps<TMeta>>;
}
