// Generated from workflow_def.schema.json — do not edit by hand.
// Run `pnpm gen` to regenerate.

export interface WorkflowDef {
  key: string;
  version: string;
  subject_kind: string;
  initial_state: string;
  metadata?: {
    [k: string]: unknown;
  };
  /**
   * @minItems 1
   */
  states: [State, ...State[]];
  transitions?: Transition[];
  escalations?: Escalation[];
}
export interface State {
  name: string;
  kind:
    | "manual_review"
    | "automatic"
    | "parallel_fork"
    | "parallel_join"
    | "timer"
    | "signal_wait"
    | "subworkflow"
    | "terminal_success"
    | "terminal_fail";
  swimlane?: string;
  form_spec_id?: string;
  documents?: {}[];
  sla?: Sla;
  subworkflow_key?: string;
}
export interface Sla {
  warn_pct?: number;
  breach_seconds?: number;
  pause_aware?: boolean;
}
export interface Transition {
  id: string;
  event: string;
  from_state: string;
  to_state: string;
  priority?: number;
  guards?: Guard[];
  gates?: Gate[];
  effects?: Effect[];
}
export interface Guard {
  kind: "expr";
  expr?: unknown;
}
export interface Gate {
  kind:
    | "permission"
    | "documents_complete"
    | "checklist_complete"
    | "approval"
    | "co_signature"
    | "compliance"
    | "custom_webhook"
    | "expr";
  permission?: string;
  policy?: string;
  tier?: number;
}
export interface Effect {
  kind:
    | "create_entity"
    | "update_entity"
    | "set"
    | "notify"
    | "audit"
    | "emit_signal"
    | "start_subworkflow"
    | "compensate"
    | "http_call";
  entity?: string;
  target?: string;
  expr?: unknown;
  values?: {
    [k: string]: unknown;
  };
  template?: string;
  signal?: string;
  subworkflow_key?: string;
  compensation_kind?: string;
  url?: string;
}
export interface Escalation {
  trigger: {
    kind: "sla_breach" | "manual";
    state?: string;
  };
  actions?: {
    kind: string;
    role?: string;
    template?: string;
    [k: string]: unknown;
  }[];
  cooldown_seconds?: number;
}
