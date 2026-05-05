import { useMemo, type JSX } from "react";

import type { DesignerStore } from "./store.js";
import { validateWorkflow } from "./validation.js";

export interface ValidationPanelProps {
	store: DesignerStore;
}

export const ValidationPanel = ({ store }: ValidationPanelProps): JSX.Element => {
	const workflow = store((s) => s.workflow);
	const issues = useMemo(() => validateWorkflow(workflow), [workflow]);
	const errors = issues.filter((i) => i.severity === "error");
	const warnings = issues.filter((i) => i.severity === "warning");

	return (
		<section data-testid="validation-panel" aria-label="Validation panel">
			<h4>
				Validation{" "}
				<span data-testid="validation-counts">
					({errors.length} errors, {warnings.length} warnings)
				</span>
			</h4>
			{issues.length === 0 ? (
				<p data-testid="validation-clean">All checks passed.</p>
			) : (
				<ul>
					{issues.map((issue, idx) => (
						<li
							key={idx}
							data-testid={`validation-issue-${issue.code}-${idx}`}
							data-severity={issue.severity}
						>
							<strong>[{issue.severity}]</strong> {issue.path}: {issue.message}{" "}
							<code>({issue.code})</code>
						</li>
					))}
				</ul>
			)}
		</section>
	);
};
