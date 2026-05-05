/**
 * FormStep — generic form-submission step.
 *
 * Renders a minimal fieldset driven by FormStep meta. Full field rendering
 * is delegated to @flowforge/renderer when available; this component is
 * self-contained with plain HTML inputs so it works without that dependency.
 */
import React, { useState } from "react";
import type { WorkflowStepProps } from "@flowforge/types";

export interface FormFieldSpec {
  name: string;
  label: string;
  type: "text" | "number" | "date" | "boolean" | "textarea";
  required?: boolean;
  defaultValue?: string | number | boolean;
}

export interface FormStepMeta {
  /** Form fields to render. */
  fields: FormFieldSpec[];
  /** Action name triggered on submit. Defaults to "submit". */
  submitAction?: string;
}

export function FormStep({
  instanceId,
  stepId,
  label,
  meta,
  readOnly,
  onAction,
  validationMessages,
}: WorkflowStepProps<FormStepMeta>) {
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {};
    for (const f of meta.fields) {
      init[f.name] = f.defaultValue ?? "";
    }
    return init;
  });

  const submitAction = meta.submitAction ?? "submit";

  function handleChange(name: string, value: unknown) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onAction({ action: submitAction, data: values });
  }

  return (
    <form
      data-testid="form-step"
      data-instance-id={instanceId}
      data-step-id={stepId}
      onSubmit={handleSubmit}
    >
      {label && <h2 className="ff-step__label">{label}</h2>}
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
      <fieldset disabled={readOnly}>
        {meta.fields.map((field) => (
          <div key={field.name} className="ff-form__field">
            <label htmlFor={`${stepId}-${field.name}`}>{field.label}</label>
            {field.type === "textarea" ? (
              <textarea
                id={`${stepId}-${field.name}`}
                name={field.name}
                required={field.required}
                value={String(values[field.name] ?? "")}
                onChange={(e) => handleChange(field.name, e.target.value)}
              />
            ) : field.type === "boolean" ? (
              <input
                id={`${stepId}-${field.name}`}
                type="checkbox"
                name={field.name}
                checked={Boolean(values[field.name])}
                onChange={(e) => handleChange(field.name, e.target.checked)}
              />
            ) : (
              <input
                id={`${stepId}-${field.name}`}
                type={field.type}
                name={field.name}
                required={field.required}
                value={String(values[field.name] ?? "")}
                onChange={(e) => handleChange(field.name, e.target.value)}
              />
            )}
          </div>
        ))}
      </fieldset>
      <div className="ff-step__actions">
        <button type="submit" disabled={readOnly}>
          {submitAction.charAt(0).toUpperCase() + submitAction.slice(1)}
        </button>
      </div>
    </form>
  );
}

FormStep.displayName = "FormStep";

export default FormStep;
