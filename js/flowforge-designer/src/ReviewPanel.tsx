/**
 * ReviewPanel — E-18 review submission UI component.
 *
 * Renders the JTBD review form: decision picker (approve / reject /
 * request_changes), an optional prose explanation, and a submit button.
 *
 * The component is headless: the host wires ``onSubmit`` to the
 * ``POST /jtbd/{id}@{v}/reviews`` endpoint.
 *
 * Required RBAC permission: ``jtbd.review``.
 * 4-eyes rule (reviewer ≠ creator) is enforced server-side.
 *
 * @example
 * ```tsx
 * <ReviewPanel
 *   jtbdId="claim_intake"
 *   version="1.4.0"
 *   onSubmit={(decision, body) =>
 *     api.postReview({ decision, body })
 *   }
 * />
 * ```
 */

import { useState, type JSX } from "react";

export type ReviewDecision = "approve" | "reject" | "request_changes";

export interface ReviewPanelProps {
	jtbdId: string;
	version: string;
	/** Called when the reviewer submits their decision. */
	onSubmit: (decision: ReviewDecision, body?: string) => void;
	/** Disable all inputs (e.g., while a request is in-flight). */
	disabled?: boolean;
}

const DECISION_LABELS: Record<ReviewDecision, string> = {
	approve: "Approve",
	reject: "Reject",
	request_changes: "Request changes",
};

export const ReviewPanel = ({
	jtbdId,
	version,
	onSubmit,
	disabled = false,
}: ReviewPanelProps): JSX.Element => {
	const [decision, setDecision] = useState<ReviewDecision | null>(null);
	const [body, setBody] = useState("");
	const [error, setError] = useState<string | null>(null);

	const handleSubmit = (): void => {
		if (!decision) {
			setError("Please select a decision before submitting.");
			return;
		}
		onSubmit(decision, body.trim() || undefined);
		setDecision(null);
		setBody("");
		setError(null);
	};

	return (
		<div data-testid="review-panel" aria-label={`Review ${jtbdId}@${version}`}>
			<h3 data-testid="review-heading">
				Review — {jtbdId}@{version}
			</h3>

			<fieldset disabled={disabled}>
				<legend>Decision</legend>
				{(["approve", "reject", "request_changes"] as ReviewDecision[]).map(
					(d) => (
						<label key={d} data-testid={`decision-label-${d}`}>
							<input
								type="radio"
								name="review-decision"
								value={d}
								data-testid={`decision-radio-${d}`}
								checked={decision === d}
								onChange={() => {
									setDecision(d);
									setError(null);
								}}
							/>
							{DECISION_LABELS[d]}
						</label>
					),
				)}
			</fieldset>

			<label htmlFor="review-body-input">
				Comments{decision === "request_changes" ? " (required)" : " (optional)"}
			</label>
			<textarea
				id="review-body-input"
				data-testid="review-body-input"
				value={body}
				disabled={disabled}
				placeholder="Explain your decision…"
				onChange={(e) => setBody(e.target.value)}
			/>

			{error ? (
				<p role="alert" data-testid="review-error">
					{error}
				</p>
			) : null}

			<button
				type="button"
				data-testid="review-submit-btn"
				disabled={disabled}
				onClick={handleSubmit}
			>
				Submit review
			</button>

			{decision ? (
				<p data-testid="review-decision-preview">
					Selected:{" "}
					<strong data-testid="review-selected-decision">
						{DECISION_LABELS[decision]}
					</strong>
				</p>
			) : null}
		</div>
	);
};
