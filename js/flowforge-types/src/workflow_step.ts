/**
 * Core contract every workflow step component must satisfy.
 * The registry, read-only wrapper, and action-interception hook all depend on this shape.
 */

/** Severity level attached to a validation message. */
export type ValidationSeverity = "error" | "warning" | "info";

/** Single field-level or form-level validation message. */
export interface ValidationMessage {
  field?: string;
  message: string;
  severity: ValidationSeverity;
}

/** Data submitted when a step action fires (approve, reject, submit, etc.). */
export interface StepActionPayload {
  /** Logical name of the action, e.g. "approve", "reject", "submit". */
  action: string;
  /** Arbitrary step-specific data collected by the action. */
  data?: Record<string, unknown>;
}

/** Result returned by an action-interception hook. */
export interface StepActionInterceptResult {
  /** If false the action is cancelled and the step stays mounted. */
  proceed: boolean;
  /** Optional override payload — replaces the original if provided. */
  payload?: StepActionPayload;
}

/**
 * Props every WorkflowStep component receives.
 *
 * Generic parameter `TMeta` allows step-specific metadata (e.g. form schema,
 * document list) to be typed precisely when the registry hydrates props.
 */
export interface WorkflowStepProps<TMeta = unknown> {
  /** Unique identifier of the workflow instance. */
  instanceId: string;

  /** Identifier of the current step within the workflow definition. */
  stepId: string;

  /** Human-readable label shown in the UI chrome (optional — host may render it). */
  label?: string;

  /** Step-specific metadata supplied by the workflow definition / runtime. */
  meta: TMeta;

  /**
   * When true, the step must render in a read-only / review mode.
   * No actions should be submittable and inputs must be disabled.
   */
  readOnly?: boolean;

  /** Current actor's role identifiers — used for conditional rendering. */
  actorRoles?: string[];

  /**
   * Called when the user triggers an action (approve, reject, submit …).
   * The host is responsible for sending the payload to the runtime client.
   */
  onAction: (payload: StepActionPayload) => void | Promise<void>;

  /**
   * Optional validation messages pre-computed by the host or runtime.
   * Steps may render these alongside their own local validation.
   */
  validationMessages?: ValidationMessage[];
}
