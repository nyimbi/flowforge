/**
 * Unit tests for @flowforge/step-adapters
 *
 * Tests:
 *  - Step registry: register, load, unregister, loadStep throws on unknown kind
 *  - ManualReviewStep: renders with sample props, calls onAction on button click
 *  - FormStep: renders fields, calls onAction with form data on submit
 *  - DocumentReviewStep: renders docs, records decisions, calls onAction on submit
 *  - withReadOnly HOC: blocks onAction and disables controls when readOnly=true
 *  - useActionInterceptor: runs chain, cancels when proceed=false, replaces payload
 */
import React from "react";
import {
  render,
  screen,
  fireEvent,
  renderHook,
  act,
} from "@testing-library/react";

import {
  createRegistry,
  registerStep,
  unregisterStep,
  registeredKinds,
  loadStep,
} from "../src/registry.js";
import { ManualReviewStep } from "../src/ManualReviewStep.js";
import { FormStep } from "../src/FormStep.js";
import { DocumentReviewStep } from "../src/DocumentReviewStep.js";
import { withReadOnly } from "../src/withReadOnly.js";
import { useActionInterceptor } from "../src/useActionInterceptor.js";

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

describe("step registry", () => {
  it("starts empty", () => {
    const reg = createRegistry();
    expect(registeredKinds(reg)).toHaveLength(0);
  });

  it("registers and retrieves a step kind", async () => {
    const reg = createRegistry();
    registerStep(reg, {
      kind: "manual_review",
      load: async () => ({ default: ManualReviewStep }),
    });
    expect(registeredKinds(reg)).toContain("manual_review");
    const Comp = await loadStep(reg, "manual_review");
    expect(Comp).toBe(ManualReviewStep);
  });

  it("unregisters a step kind", () => {
    const reg = createRegistry();
    registerStep(reg, { kind: "form", load: async () => ({ default: FormStep }) });
    expect(unregisterStep(reg, "form")).toBe(true);
    expect(registeredKinds(reg)).not.toContain("form");
    expect(unregisterStep(reg, "form")).toBe(false);
  });

  it("loadStep throws for unknown kind", async () => {
    const reg = createRegistry();
    await expect(loadStep(reg, "ghost_step")).rejects.toThrow(
      'unknown step kind "ghost_step"',
    );
  });

  it("overwrites existing entry on re-register", async () => {
    const reg = createRegistry();
    registerStep(reg, { kind: "form", load: async () => ({ default: ManualReviewStep }) });
    registerStep(reg, { kind: "form", load: async () => ({ default: FormStep }) });
    const Comp = await loadStep(reg, "form");
    expect(Comp).toBe(FormStep);
  });
});

// ---------------------------------------------------------------------------
// ManualReviewStep
// ---------------------------------------------------------------------------

describe("ManualReviewStep", () => {
  const baseProps = {
    instanceId: "inst-1",
    stepId: "step-review",
    label: "Review Application",
    meta: {
      description: "Please review the submitted application.",
      subject: { applicant: "Alice", amount: "1000" },
    },
    onAction: vi.fn(),
  };

  beforeEach(() => vi.clearAllMocks());

  it("renders label, description and subject", () => {
    render(<ManualReviewStep {...baseProps} />);
    expect(screen.getByText("Review Application")).toBeInTheDocument();
    expect(screen.getByText("Please review the submitted application.")).toBeInTheDocument();
    expect(screen.getByText("applicant")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders default approve and reject buttons", () => {
    render(<ManualReviewStep {...baseProps} />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
  });

  it("calls onAction with approve payload", () => {
    render(<ManualReviewStep {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(baseProps.onAction).toHaveBeenCalledWith({ action: "approve", data: {} });
  });

  it("uses custom actions from meta", () => {
    render(
      <ManualReviewStep {...baseProps} meta={{ ...baseProps.meta, actions: ["escalate"] }} />,
    );
    expect(screen.getByRole("button", { name: /escalate/i })).toBeInTheDocument();
  });

  it("renders validation messages", () => {
    render(
      <ManualReviewStep
        {...baseProps}
        validationMessages={[{ field: "amount", message: "Too large", severity: "error" }]}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Too large/)).toBeInTheDocument();
  });

  it("disables buttons when readOnly=true", () => {
    render(<ManualReviewStep {...baseProps} readOnly />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// FormStep
// ---------------------------------------------------------------------------

describe("FormStep", () => {
  const baseProps = {
    instanceId: "inst-2",
    stepId: "step-form",
    label: "Intake Form",
    meta: {
      fields: [
        { name: "name", label: "Full Name", type: "text" as const, required: true },
        { name: "age", label: "Age", type: "number" as const },
        { name: "notes", label: "Notes", type: "textarea" as const },
        { name: "active", label: "Active?", type: "boolean" as const },
      ],
    },
    onAction: vi.fn(),
  };

  beforeEach(() => vi.clearAllMocks());

  it("renders all fields", () => {
    render(<FormStep {...baseProps} />);
    expect(screen.getByLabelText("Full Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Age")).toBeInTheDocument();
    expect(screen.getByLabelText("Notes")).toBeInTheDocument();
    expect(screen.getByLabelText("Active?")).toBeInTheDocument();
  });

  it("calls onAction with form data on submit", () => {
    render(<FormStep {...baseProps} />);
    fireEvent.change(screen.getByLabelText("Full Name"), { target: { value: "Bob" } });
    fireEvent.submit(screen.getByTestId("form-step"));
    expect(baseProps.onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "submit", data: expect.objectContaining({ name: "Bob" }) }),
    );
  });

  it("uses custom submitAction from meta", () => {
    render(<FormStep {...baseProps} meta={{ ...baseProps.meta, submitAction: "save_draft" }} />);
    expect(screen.getByRole("button", { name: /save_draft/i })).toBeInTheDocument();
  });

  it("disables fieldset when readOnly=true", () => {
    render(<FormStep {...baseProps} readOnly />);
    expect(screen.getByRole("group")).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// DocumentReviewStep
// ---------------------------------------------------------------------------

describe("DocumentReviewStep", () => {
  const baseProps = {
    instanceId: "inst-3",
    stepId: "step-docs",
    label: "Review Documents",
    meta: {
      documents: [
        { id: "doc-1", name: "ID.pdf", mimeType: "application/pdf", classification: "RESTRICTED" },
        { id: "doc-2", name: "Proof.png", url: "https://example.com/proof.png" },
      ],
      commentLabel: "Reviewer notes",
    },
    onAction: vi.fn(),
  };

  beforeEach(() => vi.clearAllMocks());

  it("renders all documents", () => {
    render(<DocumentReviewStep {...baseProps} />);
    expect(screen.getByText("ID.pdf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Proof.png" })).toBeInTheDocument();
    expect(screen.getByText("RESTRICTED")).toBeInTheDocument();
  });

  it("renders comment textarea when commentLabel is set", () => {
    render(<DocumentReviewStep {...baseProps} />);
    expect(screen.getByLabelText("Reviewer notes")).toBeInTheDocument();
  });

  it("calls onAction with approve when all docs accepted", () => {
    render(<DocumentReviewStep {...baseProps} />);
    // Accept both documents
    const acceptButtons = screen.getAllByRole("button", { name: /accept/i });
    acceptButtons.forEach((btn) => fireEvent.click(btn));
    fireEvent.click(screen.getByRole("button", { name: /submit decision/i }));
    expect(baseProps.onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "approve" }),
    );
  });

  it("calls onAction with reject when any doc rejected", () => {
    render(<DocumentReviewStep {...baseProps} />);
    const rejectButtons = screen.getAllByRole("button", { name: /reject/i });
    fireEvent.click(rejectButtons[0]);
    fireEvent.click(screen.getByRole("button", { name: /submit decision/i }));
    expect(baseProps.onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: "reject" }),
    );
  });

  it("disables action buttons when readOnly=true", () => {
    render(<DocumentReviewStep {...baseProps} readOnly />);
    const submitBtn = screen.getByRole("button", { name: /submit decision/i });
    expect(submitBtn).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// withReadOnly HOC
// ---------------------------------------------------------------------------

describe("withReadOnly", () => {
  it("renders the wrapped step normally when readOnly=false", () => {
    const Wrapped = withReadOnly(ManualReviewStep);
    render(
      <Wrapped
        instanceId="i"
        stepId="s"
        meta={{}}
        onAction={vi.fn()}
        readOnly={false}
      />,
    );
    expect(screen.getByTestId("manual-review-step")).toBeInTheDocument();
  });

  it("wraps in readonly div and blocks onAction when readOnly=true", () => {
    const onAction = vi.fn();
    const Wrapped = withReadOnly(ManualReviewStep);
    const { container } = render(
      <Wrapped
        instanceId="i"
        stepId="s"
        meta={{}}
        onAction={onAction}
        readOnly={true}
      />,
    );
    expect(container.querySelector(".ff-step--readonly")).toBeInTheDocument();
    // All buttons disabled
    const buttons = screen.getAllByRole("button");
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  it("accepts a custom readOnlyClassName", () => {
    const Wrapped = withReadOnly(ManualReviewStep, { readOnlyClassName: "my-readonly" });
    const { container } = render(
      <Wrapped instanceId="i" stepId="s" meta={{}} onAction={vi.fn()} readOnly />,
    );
    expect(container.querySelector(".my-readonly")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// useActionInterceptor
// ---------------------------------------------------------------------------

describe("useActionInterceptor", () => {
  it("calls onAction when no interceptors present", async () => {
    const onAction = vi.fn();
    const { result } = renderHook(() => useActionInterceptor({ onAction }));
    await act(() => result.current.interceptedOnAction({ action: "approve" }));
    expect(onAction).toHaveBeenCalledWith({ action: "approve" });
  });

  it("allows the chain through when all interceptors return proceed=true", async () => {
    const onAction = vi.fn();
    const pass = vi.fn().mockResolvedValue({ proceed: true });
    const { result } = renderHook(() =>
      useActionInterceptor({ onAction, interceptors: [pass] }),
    );
    await act(() => result.current.interceptedOnAction({ action: "submit" }));
    expect(pass).toHaveBeenCalledWith({ action: "submit" });
    expect(onAction).toHaveBeenCalledWith({ action: "submit" });
  });

  it("cancels onAction when interceptor returns proceed=false", async () => {
    const onAction = vi.fn();
    const cancel = vi.fn().mockResolvedValue({ proceed: false });
    const { result } = renderHook(() =>
      useActionInterceptor({ onAction, interceptors: [cancel] }),
    );
    await act(() => result.current.interceptedOnAction({ action: "reject" }));
    expect(onAction).not.toHaveBeenCalled();
  });

  it("replaces payload when interceptor provides an override", async () => {
    const onAction = vi.fn();
    const mutate = vi.fn().mockResolvedValue({
      proceed: true,
      payload: { action: "approve", data: { enriched: true } },
    });
    const { result } = renderHook(() =>
      useActionInterceptor({ onAction, interceptors: [mutate] }),
    );
    await act(() => result.current.interceptedOnAction({ action: "approve" }));
    expect(onAction).toHaveBeenCalledWith({ action: "approve", data: { enriched: true } });
  });

  it("addInterceptor appends to the chain at runtime", async () => {
    const onAction = vi.fn();
    const late = vi.fn().mockResolvedValue({ proceed: true });
    const { result } = renderHook(() => useActionInterceptor({ onAction }));
    act(() => result.current.addInterceptor(late));
    await act(() => result.current.interceptedOnAction({ action: "submit" }));
    expect(late).toHaveBeenCalled();
    expect(onAction).toHaveBeenCalled();
  });

  it("removeInterceptor removes from chain", async () => {
    const onAction = vi.fn();
    const interceptor = vi.fn().mockResolvedValue({ proceed: true });
    const { result } = renderHook(() =>
      useActionInterceptor({ onAction, interceptors: [interceptor] }),
    );
    act(() => result.current.removeInterceptor(interceptor));
    await act(() => result.current.interceptedOnAction({ action: "approve" }));
    expect(interceptor).not.toHaveBeenCalled();
    expect(onAction).toHaveBeenCalled();
  });

  it("halts chain at first cancelling interceptor", async () => {
    const onAction = vi.fn();
    const first = vi.fn().mockResolvedValue({ proceed: false });
    const second = vi.fn().mockResolvedValue({ proceed: true });
    const { result } = renderHook(() =>
      useActionInterceptor({ onAction, interceptors: [first, second] }),
    );
    await act(() => result.current.interceptedOnAction({ action: "submit" }));
    expect(first).toHaveBeenCalled();
    expect(second).not.toHaveBeenCalled();
    expect(onAction).not.toHaveBeenCalled();
  });
});
