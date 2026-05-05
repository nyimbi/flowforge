import { useMemo, type JSX } from "react";

import { diffWorkflows } from "./diff.js";
import type { WorkflowDef } from "./types.js";

export interface DiffViewerProps {
	before: WorkflowDef;
	after: WorkflowDef;
}

const formatValue = (v: unknown): string => {
	if (v === undefined) return "—";
	if (typeof v === "string") return v;
	try {
		return JSON.stringify(v);
	} catch {
		return String(v);
	}
};

export const DiffViewer = ({ before, after }: DiffViewerProps): JSX.Element => {
	const entries = useMemo(() => diffWorkflows(before, after), [before, after]);
	const counts = useMemo(() => {
		const c = { added: 0, removed: 0, modified: 0 };
		for (const e of entries) c[e.kind] += 1;
		return c;
	}, [entries]);

	return (
		<section data-testid="diff-viewer" aria-label="Diff viewer">
			<h4>
				Workflow diff{" "}
				<span data-testid="diff-counts">
					(+{counts.added} −{counts.removed} ~{counts.modified})
				</span>
			</h4>
			{entries.length === 0 ? (
				<p data-testid="diff-empty">No differences.</p>
			) : (
				<ul>
					{entries.map((entry, idx) => (
						<li
							key={idx}
							data-testid={`diff-${entry.kind}-${idx}`}
							data-kind={entry.kind}
							data-path={entry.path}
						>
							<strong>{entry.kind}</strong> <code>{entry.path}</code>
							{entry.kind === "modified" ? (
								<>
									{" "}
									<span data-testid={`diff-before-${idx}`}>
										{formatValue(entry.before)}
									</span>{" "}
									→{" "}
									<span data-testid={`diff-after-${idx}`}>
										{formatValue(entry.after)}
									</span>
								</>
							) : null}
							{entry.kind === "added" ? (
								<>
									{" "}
									<span data-testid={`diff-after-${idx}`}>
										{formatValue(entry.after)}
									</span>
								</>
							) : null}
							{entry.kind === "removed" ? (
								<>
									{" "}
									<span data-testid={`diff-before-${idx}`}>
										{formatValue(entry.before)}
									</span>
								</>
							) : null}
						</li>
					))}
				</ul>
			)}
		</section>
	);
};
