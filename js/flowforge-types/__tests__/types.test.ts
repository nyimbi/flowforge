/**
 * types.test.ts — structural correctness tests for @flowforge/types.
 *
 * Strategy: construct literal objects that must satisfy the generated interfaces,
 * then assert shape properties at runtime. TypeScript enforces correctness at
 * compile time; vitest confirms values at runtime.
 */
import { describe, it, expect } from "vitest";
import type {
  WorkflowDef,
  State,
  Transition,
  Effect,
  Gate,
  Escalation,
} from "../src/workflow_def.js";
import type { FormSpec } from "../src/form_spec.js";
import type { JTBDBundle, Jtbd, Field, Actor } from "../src/jtbd.js";
import type {
  WorkflowStepProps,
  StepActionPayload,
  ValidationMessage,
} from "../src/workflow_step.js";
import type { StepRegistryEntry } from "../src/registry.js";

// ---------------------------------------------------------------------------
// Sample DSL fixtures — must satisfy the generated TS types exactly.
// ---------------------------------------------------------------------------

const sampleState: State = {
  name: "triage",
  kind: "manual_review",
  swimlane: "adjuster",
};

const sampleTransition: Transition = {
  id: "t1",
  event: "approve",
  from_state: "triage",
  to_state: "approved",
  priority: 1,
  guards: [{ kind: "expr", expr: { ">": ["$.amount", 0] } }],
  gates: [{ kind: "permission", permission: "claims.approve" }],
  effects: [{ kind: "audit", target: "claim" }],
};

const sampleEscalation: Escalation = {
  trigger: { kind: "sla_breach", state: "triage" },
  actions: [{ kind: "notify", role: "manager", template: "sla_breach" }],
  cooldown_seconds: 3600,
};

const sampleWorkflowDef: WorkflowDef = {
  key: "claim_intake",
  version: "1.0.0",
  subject_kind: "claim",
  initial_state: "triage",
  states: [sampleState],
  transitions: [sampleTransition],
  escalations: [sampleEscalation],
};

const sampleFormSpec: FormSpec = {
  id: "claim_form_v1",
  version: "1.0.0",
  title: "Claim Intake Form",
  fields: [
    {
      id: "claimant_name",
      kind: "text",
      label: "Claimant Name",
      required: true,
      pii: true,
    },
    {
      id: "loss_amount",
      kind: "money",
      label: "Loss Amount",
      required: true,
      pii: false,
    },
  ],
};

const sampleActor: Actor = {
  role: "claimant",
  external: true,
};

const sampleField: Field = {
  id: "policy_number",
  kind: "text",
  label: "Policy Number",
  required: true,
  pii: false,
};

const sampleJtbd: Jtbd = {
  id: "file_claim",
  title: "File a claim",
  actor: sampleActor,
  situation: "Customer has suffered a loss",
  motivation: "Recover financially",
  outcome: "Claim settled promptly",
  success_criteria: ["Claim submitted within 24h", "Decision in 5 days"],
  data_capture: [sampleField],
};

const sampleBundle: JTBDBundle = {
  project: {
    name: "Claims Demo",
    package: "claims_demo",
    domain: "insurance",
    tenancy: "multi",
    frontend_framework: "nextjs",
  },
  jtbds: [sampleJtbd],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WorkflowDef schema types", () => {
  it("required fields are present", () => {
    expect(sampleWorkflowDef.key).toBe("claim_intake");
    expect(sampleWorkflowDef.version).toBe("1.0.0");
    expect(sampleWorkflowDef.subject_kind).toBe("claim");
    expect(sampleWorkflowDef.initial_state).toBe("triage");
  });

  it("states array contains at least one item", () => {
    expect(sampleWorkflowDef.states.length).toBeGreaterThanOrEqual(1);
  });

  it("state kind is one of the schema enum values", () => {
    const validKinds = [
      "manual_review",
      "automatic",
      "parallel_fork",
      "parallel_join",
      "timer",
      "signal_wait",
      "subworkflow",
      "terminal_success",
      "terminal_fail",
    ];
    for (const s of sampleWorkflowDef.states) {
      expect(validKinds).toContain(s.kind);
    }
  });

  it("transition has required id, event, from_state, to_state", () => {
    const t = sampleWorkflowDef.transitions![0];
    expect(t.id).toBeTruthy();
    expect(t.event).toBeTruthy();
    expect(t.from_state).toBeTruthy();
    expect(t.to_state).toBeTruthy();
  });

  it("gate kind is one of schema enum values", () => {
    const validGateKinds = [
      "permission",
      "documents_complete",
      "checklist_complete",
      "approval",
      "co_signature",
      "compliance",
      "custom_webhook",
      "expr",
    ];
    const gate: Gate = { kind: "permission", permission: "claims.approve" };
    expect(validGateKinds).toContain(gate.kind);
  });

  it("effect kind is one of schema enum values", () => {
    const validEffectKinds = [
      "create_entity",
      "update_entity",
      "set",
      "notify",
      "audit",
      "emit_signal",
      "start_subworkflow",
      "compensate",
      "http_call",
    ];
    const effect: Effect = { kind: "audit", target: "claim" };
    expect(validEffectKinds).toContain(effect.kind);
  });

  it("escalation trigger kind is one of schema enum values", () => {
    expect(["sla_breach", "manual"]).toContain(
      sampleWorkflowDef.escalations![0].trigger.kind
    );
  });
});

describe("FormSpec schema types", () => {
  it("required fields are present", () => {
    expect(sampleFormSpec.id).toBe("claim_form_v1");
    expect(sampleFormSpec.version).toBe("1.0.0");
    expect(sampleFormSpec.title).toBe("Claim Intake Form");
  });

  it("fields array contains at least one item", () => {
    expect(sampleFormSpec.fields.length).toBeGreaterThanOrEqual(1);
  });

  it("field kinds are valid schema enum values", () => {
    const validKinds = [
      "text", "number", "money", "date", "datetime", "enum",
      "boolean", "party_ref", "document_ref", "email", "phone",
      "address", "textarea", "signature", "file", "lookup",
    ];
    for (const f of sampleFormSpec.fields) {
      expect(validKinds).toContain(f.kind);
    }
  });

  it("pii flag is boolean", () => {
    for (const f of sampleFormSpec.fields) {
      expect(typeof f.pii).toBe("boolean");
    }
  });
});

describe("JTBDBundle schema types", () => {
  it("project required fields present", () => {
    expect(sampleBundle.project.name).toBe("Claims Demo");
    expect(sampleBundle.project.package).toBe("claims_demo");
    expect(sampleBundle.project.domain).toBe("insurance");
  });

  it("jtbds array non-empty", () => {
    expect(sampleBundle.jtbds.length).toBeGreaterThanOrEqual(1);
  });

  it("jtbd required fields present", () => {
    const j = sampleBundle.jtbds[0];
    expect(j.id).toBe("file_claim");
    expect(j.actor.role).toBe("claimant");
    expect(j.success_criteria.length).toBeGreaterThanOrEqual(1);
  });

  it("field pii is a boolean", () => {
    const f = sampleBundle.jtbds[0].data_capture![0];
    expect(typeof f.pii).toBe("boolean");
  });

  it("tenancy enum values respected", () => {
    expect(["none", "single", "multi"]).toContain(
      sampleBundle.project.tenancy
    );
  });

  it("frontend_framework enum values respected", () => {
    expect(["nextjs", "remix", "vite-react"]).toContain(
      sampleBundle.project.frontend_framework
    );
  });
});

describe("WorkflowStepProps contract", () => {
  it("StepActionPayload has action and optional data", () => {
    const payload: StepActionPayload = { action: "approve", data: { note: "ok" } };
    expect(payload.action).toBe("approve");
    expect(payload.data?.note).toBe("ok");
  });

  it("ValidationMessage severity is one of error|warning|info", () => {
    const msg: ValidationMessage = {
      field: "loss_amount",
      message: "Must be positive",
      severity: "error",
    };
    expect(["error", "warning", "info"]).toContain(msg.severity);
  });

  it("WorkflowStepProps shape is assignable", () => {
    const props: WorkflowStepProps<{ formId: string }> = {
      instanceId: "inst-1",
      stepId: "triage",
      meta: { formId: "claim_form_v1" },
      onAction: (_p) => {},
    };
    expect(props.instanceId).toBe("inst-1");
    expect(props.meta.formId).toBe("claim_form_v1");
  });
});

describe("StepRegistry contract", () => {
  it("StepRegistryEntry shape is assignable", () => {
    const entry: StepRegistryEntry<{ formId: string }> = {
      kind: "manual_review",
      displayName: "Manual Review",
      load: () =>
        Promise.resolve({
          default: (_props: WorkflowStepProps<{ formId: string }>) => null,
        }),
    };
    expect(entry.kind).toBe("manual_review");
    expect(typeof entry.load).toBe("function");
  });
});
