/**
 * ManualReviewStep — generic human-review step.
 *
 * Displays a summary of the subject under review and presents
 * configurable action buttons (default: approve / reject).
 */
import React from "react";
import type { WorkflowStepProps } from "@flowforge/types";

export interface ManualReviewMeta {
  /** Short description shown to the reviewer. */
  description?: string;
  /** Available action names. Defaults to ["approve", "reject"]. */
  actions?: string[];
  /** Arbitrary structured data to display in the review panel. */
  subject?: Record<string, unknown>;
}

export function ManualReviewStep({
  instanceId,
  stepId,
  label,
  meta,
  readOnly,
  actorRoles,
  onAction,
  validationMessages,
}: WorkflowStepProps<ManualReviewMeta>) {
  const actions = meta.actions ?? ["approve", "reject"];

  return (
    <div
      data-testid="manual-review-step"
      data-instance-id={instanceId}
      data-step-id={stepId}
    >
      {label && <h2 className="ff-step__label">{label}</h2>}
      {meta.description && (
        <p className="ff-step__description">{meta.description}</p>
      )}
      {meta.subject && (
        <dl className="ff-step__subject">
          {Object.entries(meta.subject).map(([key, value]) => (
            <React.Fragment key={key}>
              <dt>{key}</dt>
              <dd>{String(value)}</dd>
            </React.Fragment>
          ))}
        </dl>
      )}
      {validationMessages && validationMessages.length > 0 && (
        <ul className="ff-step__validation" role="alert">
          {validationMessages.map((msg, i) => (
            <li key={i} data-severity={msg.severity}>
              {msg.field ? `${msg.field}: ` : ""}
              {msg.message}
            </li>
          ))}
        </ul>
      )}
      <div className="ff-step__actions">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            disabled={readOnly}
            data-action={action}
            onClick={() => onAction({ action, data: {} })}
          >
            {action.charAt(0).toUpperCase() + action.slice(1)}
          </button>
        ))}
      </div>
    </div>
  );
}

ManualReviewStep.displayName = "ManualReviewStep";

export default ManualReviewStep;
