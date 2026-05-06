/**
 * JobMap — visual swimlane canvas for a `JtbdBundle`.
 *
 * One horizontal lane per actor role; JTBDs render as boxes positioned
 * by topological order across `requires` edges. Edges connect upstream
 * → downstream JTBDs; cross-lane edges paint in a different colour so
 * the eye picks up the dependency hop.
 *
 * The canvas has two render modes:
 *
 *   * `withReactFlow={true}` (default) — wraps the laid-out nodes /
 *     edges in a `<ReactFlow>` instance for pan/zoom/minimap.
 *   * `withReactFlow={false}` — renders the same data with simple SVG
 *     so happy-dom unit tests can assert layout / click handlers
 *     without dragging in reactflow's measurement path. The pattern
 *     mirrors `flowforge-designer/Canvas.tsx`.
 *
 * Per `framework/docs/jtbd-editor-arch.md` §3.7 + §17 the canvas is
 * expected to render 200 JTBDs at 60fps; the layout is O(n + e) and
 * the SVG fallback uses no per-node React state so re-renders are
 * cheap. Heavier features (drag-to-reorder, virtualisation) ship in
 * E-7 / E-8 follow-ups.
 */

import { useMemo, type JSX } from "react";
import ReactFlow, {
	Background,
	Controls,
	MiniMap,
	type Edge,
	type Node,
} from "reactflow";

import "reactflow/dist/style.css";

import {
	LANE_HEADER_WIDTH,
	NODE_HEIGHT,
	NODE_WIDTH,
	layoutJobMap,
	type EdgeLayout,
	type JobMapLayout,
	type LaneLayout,
	type NodeLayout,
} from "./layout.js";
import type { JtbdBundle } from "./types.js";

const SAME_LANE_EDGE_COLOR = "#64748b";
const CROSS_LANE_EDGE_COLOR = "#7c3aed";
const CYCLE_NODE_BORDER = "#dc2626";
const NODE_BORDER = "#1e3a8a";
const ACTIVE_NODE_BORDER = "#16a34a";
const ACTIVE_NODE_FILL = "#dcfce7";
const FIRED_NODE_BORDER = "#0ea5e9";
const FIRED_NODE_FILL = "#e0f2fe";
const LANE_FILL_ODD = "#f8fafc";
const LANE_FILL_EVEN = "#eef2ff";

export type NodeAnimationState = "default" | "fired" | "active";

export interface JobMapProps {
	bundle: JtbdBundle;
	/** Click handler invoked with the JTBD id whose box was clicked. */
	onSelectJtbd?: (jtbdId: string) => void;
	/** Test-mode escape hatch — see component doc-comment. */
	withReactFlow?: boolean;
	/** Optional className on the outer wrapper, used for theming. */
	className?: string;
	/** Set of JTBD ids that have already fired in the current
	 * animation. Rendered in a "visited" colour. */
	firedIds?: ReadonlySet<string>;
	/** Set of JTBD ids that are currently active in the animation
	 * (typically just one). Rendered with a highlighted border. */
	activeIds?: ReadonlySet<string>;
}

const animationStateFor = (
	jtbdId: string,
	firedIds: ReadonlySet<string> | undefined,
	activeIds: ReadonlySet<string> | undefined,
): NodeAnimationState => {
	if (activeIds?.has(jtbdId)) {
		return "active";
	}
	if (firedIds?.has(jtbdId)) {
		return "fired";
	}
	return "default";
};

const styleForState = (
	cycle: boolean,
	state: NodeAnimationState,
): { border: string; background: string } => {
	if (state === "active") {
		return { border: ACTIVE_NODE_BORDER, background: ACTIVE_NODE_FILL };
	}
	if (state === "fired") {
		return { border: FIRED_NODE_BORDER, background: FIRED_NODE_FILL };
	}
	return {
		border: cycle ? CYCLE_NODE_BORDER : NODE_BORDER,
		background: "#ffffff",
	};
};

const toReactFlowNode = (
	n: NodeLayout,
	state: NodeAnimationState,
): Node => {
	const { border, background } = styleForState(n.inCycle, state);
	return {
		id: n.jtbdId,
		position: { x: n.x, y: n.y },
		data: { label: `${n.title}\n(${n.role})` },
		style: {
			width: n.width,
			height: n.height,
			borderRadius: 8,
			border: `2px solid ${border}`,
			background,
			fontSize: 12,
			display: "flex",
			alignItems: "center",
			justifyContent: "center",
			whiteSpace: "pre-line",
			textAlign: "center",
			padding: 8,
		},
		type: "default",
	};
};

const toReactFlowEdge = (e: EdgeLayout): Edge => ({
	id: e.id,
	source: e.source,
	target: e.target,
	style: {
		stroke: e.crossLane ? CROSS_LANE_EDGE_COLOR : SAME_LANE_EDGE_COLOR,
		strokeWidth: 2,
	},
	animated: false,
});

export const JobMap = ({
	bundle,
	onSelectJtbd,
	withReactFlow = true,
	className,
	firedIds,
	activeIds,
}: JobMapProps): JSX.Element => {
	const layout = useMemo<JobMapLayout>(() => layoutJobMap(bundle), [bundle]);

	const nodes = useMemo(
		() =>
			layout.nodes.map((n) =>
				toReactFlowNode(n, animationStateFor(n.jtbdId, firedIds, activeIds)),
			),
		[layout.nodes, firedIds, activeIds],
	);
	const edges = useMemo(() => layout.edges.map(toReactFlowEdge), [layout.edges]);

	if (!withReactFlow) {
		return (
			<div
				data-testid="ff-jobmap"
				role="region"
				aria-label="JTBD job map"
				className={className}
				style={{ position: "relative", width: layout.width, height: layout.height }}
			>
				<svg
					width={layout.width}
					height={layout.height}
					data-testid="ff-jobmap-svg"
					style={{ position: "absolute", inset: 0 }}
				>
					{layout.lanes.map((lane) => (
						<LaneStrip key={lane.role} lane={lane} totalWidth={layout.width} />
					))}
					{layout.edges.map((edge) => (
						<JobMapEdge key={edge.id} edge={edge} layout={layout} />
					))}
				</svg>
				{layout.nodes.map((node) => (
					<JobMapNode
						key={node.jtbdId}
						node={node}
						onSelect={onSelectJtbd}
						animationState={animationStateFor(node.jtbdId, firedIds, activeIds)}
					/>
				))}
			</div>
		);
	}

	return (
		<div
			data-testid="ff-jobmap"
			role="region"
			aria-label="JTBD job map"
			className={className}
			style={{ width: "100%", height: "100%", minHeight: layout.height }}
		>
			<ReactFlow
				nodes={nodes}
				edges={edges}
				fitView
				proOptions={{ hideAttribution: true }}
				onNodeClick={(_, node) => {
					if (onSelectJtbd) {
						onSelectJtbd(node.id);
					}
				}}
			>
				<Background />
				<Controls />
				<MiniMap />
			</ReactFlow>
		</div>
	);
};

interface LaneStripProps {
	lane: LaneLayout;
	totalWidth: number;
}

const LaneStrip = ({ lane, totalWidth }: LaneStripProps): JSX.Element => {
	const fill = lane.index % 2 === 0 ? LANE_FILL_EVEN : LANE_FILL_ODD;
	return (
		<g data-testid={`ff-jobmap-lane-${lane.role}`}>
			<rect
				x={0}
				y={lane.y}
				width={totalWidth}
				height={lane.height}
				fill={fill}
				stroke="#cbd5e1"
				strokeWidth={1}
			/>
			<text
				x={12}
				y={lane.y + lane.height / 2}
				dominantBaseline="middle"
				fontSize={13}
				fontWeight={600}
				fill="#1e293b"
				data-testid={`ff-jobmap-lane-label-${lane.role}`}
			>
				{lane.role}
			</text>
			<line
				x1={LANE_HEADER_WIDTH}
				y1={lane.y}
				x2={LANE_HEADER_WIDTH}
				y2={lane.y + lane.height}
				stroke="#94a3b8"
				strokeWidth={1}
			/>
		</g>
	);
};

interface JobMapNodeProps {
	node: NodeLayout;
	onSelect?: (jtbdId: string) => void;
	animationState?: NodeAnimationState;
}

const JobMapNode = ({
	node,
	onSelect,
	animationState = "default",
}: JobMapNodeProps): JSX.Element => {
	const { border, background } = styleForState(node.inCycle, animationState);
	const handleClick = (): void => {
		if (onSelect) {
			onSelect(node.jtbdId);
		}
	};
	const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
		if (event.key === "Enter" || event.key === " ") {
			event.preventDefault();
			handleClick();
		}
	};
	return (
		<div
			role="button"
			tabIndex={0}
			data-testid={`ff-jobmap-node-${node.jtbdId}`}
			data-incycle={node.inCycle ? "true" : "false"}
			data-role={node.role}
			data-column={String(node.column)}
			data-animation-state={animationState}
			onClick={handleClick}
			onKeyDown={handleKeyDown}
			style={{
				position: "absolute",
				left: node.x,
				top: node.y,
				width: node.width,
				height: node.height,
				border: `2px solid ${border}`,
				borderRadius: 8,
				padding: 8,
				background,
				boxSizing: "border-box",
				display: "flex",
				flexDirection: "column",
				justifyContent: "center",
				cursor: onSelect ? "pointer" : "default",
				fontSize: 12,
				lineHeight: 1.3,
				transition: "background 200ms ease, border-color 200ms ease",
			}}
		>
			<strong style={{ fontSize: 13 }}>{node.title}</strong>
			<span style={{ color: "#475569", fontSize: 11 }}>{node.jtbdId}</span>
		</div>
	);
};

interface JobMapEdgeProps {
	edge: EdgeLayout;
	layout: JobMapLayout;
}

const JobMapEdge = ({ edge, layout }: JobMapEdgeProps): JSX.Element | null => {
	const source = layout.nodes.find((n) => n.jtbdId === edge.source);
	const target = layout.nodes.find((n) => n.jtbdId === edge.target);
	if (!source || !target) {
		return null;
	}
	const stroke = edge.crossLane ? CROSS_LANE_EDGE_COLOR : SAME_LANE_EDGE_COLOR;
	const x1 = source.x + NODE_WIDTH;
	const y1 = source.y + NODE_HEIGHT / 2;
	const x2 = target.x;
	const y2 = target.y + NODE_HEIGHT / 2;
	const midX = (x1 + x2) / 2;
	const path = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
	return (
		<path
			data-testid={`ff-jobmap-edge-${edge.id}`}
			data-crosslane={edge.crossLane ? "true" : "false"}
			d={path}
			fill="none"
			stroke={stroke}
			strokeWidth={2}
			markerEnd="url(#ff-jobmap-arrow)"
		/>
	);
};
