import { useMemo, useState, type JSX } from "react";

import { simulate } from "./simulation.js";
import type { DesignerStore } from "./store.js";

export interface SimulationPanelProps {
	store: DesignerStore;
}

export const SimulationPanel = ({ store }: SimulationPanelProps): JSX.Element => {
	const workflow = store((s) => s.workflow);
	const [eventsText, setEventsText] = useState("");

	const result = useMemo(() => {
		const events = eventsText
			.split(/[\s,]+/)
			.map((e) => e.trim())
			.filter(Boolean);
		return simulate(workflow, { events });
	}, [workflow, eventsText]);

	return (
		<section data-testid="simulation-panel" aria-label="Simulation panel">
			<h4>Simulation</h4>
			<label>
				<span>Events (comma- or whitespace-separated)</span>
				<textarea
					data-testid="simulation-events"
					value={eventsText}
					onChange={(e) => setEventsText(e.target.value)}
					rows={3}
				/>
			</label>
			<dl>
				<dt>Initial state</dt>
				<dd data-testid="simulation-initial">{workflow.initial_state || "(unset)"}</dd>
				<dt>Final state</dt>
				<dd data-testid="simulation-final">{result.final_state ?? "(none)"}</dd>
				<dt>Terminated</dt>
				<dd data-testid="simulation-terminated">{result.terminated ? "yes" : "no"}</dd>
			</dl>
			<ol data-testid="simulation-trace">
				{result.trace.map((step, idx) => (
					<li key={idx} data-testid={`simulation-step-${idx}`}>
						{step.from} → <strong>{step.to}</strong> on <code>{step.event}</code>
					</li>
				))}
			</ol>
		</section>
	);
};
