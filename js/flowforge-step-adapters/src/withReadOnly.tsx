/**
 * withReadOnly — higher-order component that wraps any WorkflowStep and
 * enforces read-only mode when readOnly=true.
 *
 * In read-only mode:
 *   - The onAction callback is replaced with a no-op (actions are blocked).
 *   - readOnly=true is forwarded to the wrapped component.
 *   - An optional overlay className is added for styling.
 */
import React, { forwardRef, useCallback } from "react";
import type { ComponentType } from "react";
import type { WorkflowStepProps } from "@flowforge/types";

export interface WithReadOnlyOptions {
  /** CSS class applied to the wrapper div when readOnly=true. Defaults to "ff-step--readonly". */
  readOnlyClassName?: string;
}

export function withReadOnly<TMeta = unknown>(
  WrappedStep: ComponentType<WorkflowStepProps<TMeta>>,
  options: WithReadOnlyOptions = {},
): ComponentType<WorkflowStepProps<TMeta>> {
  const { readOnlyClassName = "ff-step--readonly" } = options;

  const ReadOnlyWrapper = (props: WorkflowStepProps<TMeta>) => {
    const blockedOnAction = useCallback(async () => {
      // Intentionally no-op in read-only mode.
    }, []);

    if (!props.readOnly) {
      return <WrappedStep {...props} />;
    }

    return (
      <div className={readOnlyClassName} aria-readonly="true">
        <WrappedStep {...props} onAction={blockedOnAction} readOnly={true} />
      </div>
    );
  };

  ReadOnlyWrapper.displayName = `withReadOnly(${
    WrappedStep.displayName ?? WrappedStep.name ?? "Step"
  })`;

  return ReadOnlyWrapper;
}
