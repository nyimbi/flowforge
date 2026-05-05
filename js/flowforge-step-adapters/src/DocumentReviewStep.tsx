/**
 * DocumentReviewStep — generic document-review step.
 *
 * Lists attached documents and allows the reviewer to accept or reject
 * each one, then submit a consolidated decision.
 */
import React, { useState } from "react";
import type { WorkflowStepProps } from "@flowforge/types";

export interface DocumentRef {
  id: string;
  name: string;
  /** MIME type for display hints (e.g. "application/pdf"). */
  mimeType?: string;
  /** Pre-signed URL for preview/download. */
  url?: string;
  /** Classification label, e.g. "CONFIDENTIAL". */
  classification?: string;
}

export interface DocumentReviewMeta {
  documents: DocumentRef[];
  /** Action name when the reviewer approves all docs. Defaults to "approve". */
  approveAction?: string;
  /** Action name when the reviewer rejects at least one doc. Defaults to "reject". */
  rejectAction?: string;
  /** Free-text comment field label. Omit to hide. */
  commentLabel?: string;
}

type DocDecision = "pending" | "accepted" | "rejected";

export function DocumentReviewStep({
  instanceId,
  stepId,
  label,
  meta,
  readOnly,
  onAction,
  validationMessages,
}: WorkflowStepProps<DocumentReviewMeta>) {
  const approveAction = meta.approveAction ?? "approve";
  const rejectAction = meta.rejectAction ?? "reject";

  const [decisions, setDecisions] = useState<Record<string, DocDecision>>(
    () => Object.fromEntries(meta.documents.map((d) => [d.id, "pending"])),
  );
  const [comment, setComment] = useState("");

  function decide(docId: string, decision: DocDecision) {
    if (readOnly) return;
    setDecisions((prev) => ({ ...prev, [docId]: decision }));
  }

  function handleSubmit() {
    const anyRejected = Object.values(decisions).some((d) => d === "rejected");
    const action = anyRejected ? rejectAction : approveAction;
    onAction({ action, data: { decisions, comment } });
  }

  return (
    <div
      data-testid="document-review-step"
      data-instance-id={instanceId}
      data-step-id={stepId}
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
      <ul className="ff-doc-review__list">
        {meta.documents.map((doc) => (
          <li key={doc.id} className="ff-doc-review__item" data-doc-id={doc.id}>
            <span className="ff-doc-review__name">
              {doc.url ? (
                <a href={doc.url} target="_blank" rel="noopener noreferrer">
                  {doc.name}
                </a>
              ) : (
                doc.name
              )}
            </span>
            {doc.classification && (
              <span className="ff-doc-review__classification">
                {doc.classification}
              </span>
            )}
            <span className="ff-doc-review__decision" data-decision={decisions[doc.id]}>
              {decisions[doc.id]}
            </span>
            <button
              type="button"
              disabled={readOnly}
              onClick={() => decide(doc.id, "accepted")}
              data-action="accept"
            >
              Accept
            </button>
            <button
              type="button"
              disabled={readOnly}
              onClick={() => decide(doc.id, "rejected")}
              data-action="reject"
            >
              Reject
            </button>
          </li>
        ))}
      </ul>
      {meta.commentLabel && (
        <div className="ff-doc-review__comment">
          <label htmlFor={`${stepId}-comment`}>{meta.commentLabel}</label>
          <textarea
            id={`${stepId}-comment`}
            value={comment}
            disabled={readOnly}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
      )}
      <div className="ff-step__actions">
        <button type="button" disabled={readOnly} onClick={handleSubmit}>
          Submit Decision
        </button>
      </div>
    </div>
  );
}

DocumentReviewStep.displayName = "DocumentReviewStep";

export default DocumentReviewStep;
