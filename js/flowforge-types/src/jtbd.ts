// Generated from jtbd-1.0.schema.json — do not edit by hand.
// Run `pnpm gen` to regenerate.

export type Approval = {
  role: string;
  policy: "1_of_1" | "2_of_2" | "n_of_m" | "authority_tier";
  n?: number;
  tier?: number;
} & Approval1;
export type Approval1 =
  | {
      policy?: "n_of_m";
    }
  | {
      policy?: "authority_tier";
    }
  | {
      policy?: "1_of_1";
    }
  | {
      policy?: "2_of_2";
    };

export interface JTBDBundle {
  project: {
    name: string;
    package: string;
    domain: string;
    tenancy?: "none" | "single" | "multi";
    languages?: string[];
    currencies?: string[];
    frontend_framework?: "nextjs" | "remix" | "vite-react";
  };
  shared?: {
    roles?: string[];
    permissions?: string[];
    entities?: {}[];
  };
  /**
   * @minItems 1
   */
  jtbds: [Jtbd, ...Jtbd[]];
}
export interface Jtbd {
  id: string;
  title?: string;
  actor: Actor;
  situation: string;
  motivation: string;
  outcome: string;
  /**
   * @minItems 1
   */
  success_criteria: [string, ...string[]];
  edge_cases?: EdgeCase[];
  data_capture?: Field[];
  documents_required?: DocReq[];
  approvals?: Approval[];
  sla?: {
    warn_pct?: number;
    breach_seconds?: number;
  };
  notifications?: Notification[];
  metrics?: string[];
}
export interface Actor {
  role: string;
  department?: string;
  external?: boolean;
}
export interface EdgeCase {
  id: string;
  condition: string;
  handle: "branch" | "reject" | "escalate" | "compensate" | "loop";
  branch_to?: string;
}
export interface Field {
  id: string;
  kind:
    | "text"
    | "number"
    | "money"
    | "date"
    | "datetime"
    | "enum"
    | "boolean"
    | "party_ref"
    | "document_ref"
    | "email"
    | "phone"
    | "address"
    | "textarea"
    | "signature"
    | "file";
  label?: string;
  required?: boolean;
  pii: boolean;
  validation?: {
    [k: string]: unknown;
  };
}
export interface DocReq {
  kind: string;
  min?: number;
  max?: number;
  freshness_days?: number;
  av_required?: boolean;
}
export interface Notification {
  trigger: "state_enter" | "state_exit" | "sla_warn" | "sla_breach" | "approved" | "rejected" | "escalated";
  channel: "email" | "sms" | "slack" | "webhook" | "in_app";
  audience: string;
}
