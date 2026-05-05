import { useMemo, type JSX } from "react";
import ReactFlow, {
	Background,
	Controls,
	type Edge,
	type Node,
	type NodeMouseHandler,
} from "reactflow";

import "reactflow/dist/style.css";

import type { DesignerStore } from "./store.js";
import type { WorkflowState, WorkflowTransition } from "./types.js";

const STATE_COLORS: Record<WorkflowState["kind"], string> = {
	start: "#16a34a",
	task: "#2563eb",
	review: "#7c3aed",
	decision: "#f59e0b",
	wait: "#0891b2",
	end: "#dc2626",
};

const layoutPosition = (index: number): { x: number; y: number } => ({
	x: 80 + (index % 4) * 220,
	y: 80 + Math.floor(index / 4) * 140,
});

const toNode = (state: WorkflowState, index: number): Node => ({
	id: state.id,
	position: layoutPosition(index),
	data: { label: state.name || state.id, kind: state.kind },
	style: {
		borderRadius: 8,
		padding: 12,
		border: `2px solid ${STATE_COLORS[state.kind]}`,
		background: "#ffffff",
		fontSize: 12,
		minWidth: 140,
	},
	type: "default",
});

const toEdge = (t: WorkflowTransition): Edge => ({
	id: t.id,
	source: t.from,
	target: t.to,
	label: t.event,
	labelStyle: { fontSize: 11, fill: "#374151" },
	style: { stroke: "#6b7280" },
	animated: false,
});

export interface CanvasProps {
	store: DesignerStore;
	/** When true, render the reactflow shell. Tests pass false to skip the
	 * canvas because reactflow needs a measured DOM. */
	withReactFlow?: boolean;
}

export const Canvas = ({ store, withReactFlow = true }: CanvasProps): JSX.Element => {
	const workflow = store((s) => s.workflow);
	const select = store((s) => s.select);

	const nodes = useMemo(() => workflow.states.map(toNode), [workflow.states]);
	const edges = useMemo(() => workflow.transitions.map(toEdge), [workflow.transitions]);

	const onNodeClick: NodeMouseHandler = (_event, node) => {
		select({ kind: "state", id: node.id });
	};
	const onEdgeClick = (_event: React.MouseEvent, edge: Edge): void => {
		select({ kind: "transition", id: edge.id });
	};

	if (!withReactFlow) {
		// Fallback rendering used in unit tests where reactflow's measurement
		// path explodes under happy-dom. Renders the same data so click +
		// commit assertions still hold.
		return (
			<div data-testid="ff-canvas" role="region" aria-label="Workflow canvas">
				<ul>
					{workflow.states.map((s) => (
						<li
							key={s.id}
							data-testid={`canvas-state-${s.id}`}
							onClick={() => select({ kind: "state", id: s.id })}
						>
							{s.name} ({s.kind})
						</li>
					))}
				</ul>
				<ul>
					{workflow.transitions.map((t) => (
						<li
							key={t.id}
							data-testid={`canvas-transition-${t.id}`}
							onClick={() => select({ kind: "transition", id: t.id })}
						>
							{t.from} → {t.to}: {t.event}
						</li>
					))}
				</ul>
			</div>
		);
	}

	return (
		<div
			data-testid="ff-canvas"
			role="region"
			aria-label="Workflow canvas"
			style={{ width: "100%", height: "100%" }}
		>
			<ReactFlow
				nodes={nodes}
				edges={edges}
				onNodeClick={onNodeClick}
				onEdgeClick={onEdgeClick}
				fitView
				proOptions={{ hideAttribution: true }}
			>
				<Background />
				<Controls />
			</ReactFlow>
		</div>
	);
};
