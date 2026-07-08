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

import { useEffect, useMemo, useRef, useState, type JSX } from "react";
import ReactFlow, {
	Background,
	Controls,
	MiniMap,
	type Edge,
	type Node,
	type ReactFlowInstance,
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

/**
 * E-67 / JS-07 — viewport virtualisation threshold.
 *
 * Bundles below this node count render every node unconditionally; the
 * SVG-fallback render path is fast enough that the bookkeeping cost of
 * filtering by viewport overshadows the saved work. At or above this
 * count, only nodes whose layout bbox intersects the visible viewport
 * (plus a one-screen over-render margin) are rendered to the DOM.
 *
 * Bumping the threshold lower trades a little memory churn for a
 * smoother scroll on weaker devices; raising it does the opposite.
 */
export const VIRTUALISATION_THRESHOLD = 200;
const VIRTUALISATION_OVERSCAN = 200; // px around the viewport in every direction

const SAME_LANE_EDGE_COLOR = "var(--ff-jobmap-edge, #64748b)";
const CROSS_LANE_EDGE_COLOR = "var(--ff-jobmap-edge-cross-lane, #7c3aed)";
const CYCLE_NODE_BORDER = "var(--ff-jobmap-node-cycle-border, #dc2626)";
const NODE_BORDER = "var(--ff-jobmap-node-border, #1e3a8a)";
const ACTIVE_NODE_BORDER = "var(--ff-jobmap-node-active-border, #16a34a)";
const ACTIVE_NODE_FILL = "var(--ff-jobmap-node-active-bg, #dcfce7)";
const SELECTED_NODE_BORDER = "var(--ff-jobmap-node-selected-border, #f59e0b)";
const SELECTED_NODE_FILL = "var(--ff-jobmap-node-selected-bg, #fffbeb)";
const FIRED_NODE_BORDER = "var(--ff-jobmap-node-fired-border, #0ea5e9)";
const FIRED_NODE_FILL = "var(--ff-jobmap-node-fired-bg, #e0f2fe)";
const LANE_FILL_ODD = "var(--ff-jobmap-lane-odd-bg, #f8fafc)";
const LANE_FILL_EVEN = "var(--ff-jobmap-lane-even-bg, #eef2ff)";
const NODE_FILL = "var(--ff-jobmap-node-bg, #ffffff)";
const NODE_TEXT = "var(--ff-jobmap-node-fg, #0f172a)";
const NODE_MUTED_TEXT = "var(--ff-jobmap-node-muted-fg, #475569)";
const LANE_TEXT = "var(--ff-jobmap-lane-fg, #1e293b)";
const LANE_BORDER = "var(--ff-jobmap-lane-border, #cbd5e1)";
const LANE_DIVIDER = "var(--ff-jobmap-lane-divider, #94a3b8)";

export type NodeAnimationState = "default" | "fired" | "active";

/** A rectangular viewport in layout coordinates. */
export interface JobMapViewport {
	x: number;
	y: number;
	width: number;
	height: number;
}

/**
 * E-67 / JS-07: filter *nodes* down to those whose bounding box
 * intersects *viewport* (with an overscan margin). Nodes with cycles
 * are always retained so the user always sees them as warning
 * indicators even when off-screen.
 *
 * Exported for unit-test reach; production code goes through the
 * `<JobMap>` component.
 */
export const nodesInViewport = (
	nodes: readonly NodeLayout[],
	viewport: JobMapViewport,
	overscan: number = VIRTUALISATION_OVERSCAN,
): NodeLayout[] => {
	const left = viewport.x - overscan;
	const right = viewport.x + viewport.width + overscan;
	const top = viewport.y - overscan;
	const bottom = viewport.y + viewport.height + overscan;
	return nodes.filter((n) => {
		if (n.inCycle) {
			return true; // always-on indicator
		}
		const nLeft = n.x;
		const nRight = n.x + n.width;
		const nTop = n.y;
		const nBottom = n.y + n.height;
		return nRight >= left && nLeft <= right && nBottom >= top && nTop <= bottom;
	});
};

/**
 * E-67 / JS-07: keep edges whose source AND target are in the visible
 * node set. Edges spanning out-of-viewport endpoints would render as
 * dangling arrows, so we drop them; the user pans to the missing end
 * and the edge re-appears.
 */
export const edgesInViewport = (
	edges: readonly EdgeLayout[],
	visibleNodeIds: ReadonlySet<string>,
): EdgeLayout[] =>
	edges.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));

export interface JobMapProps {
	bundle: JtbdBundle;
	/** Click handler invoked with the JTBD id whose box was clicked. */
	onSelectJtbd?: (jtbdId: string) => void;
	/** Click handler invoked with the dependency edge id (`source->target`). */
	onSelectDependency?: (dependencyId: string) => void;
	/** JTBD id rendered as selected in authoring flows. */
	selectedJtbdId?: string | null;
	/** Dependency edge id rendered as selected in authoring flows. */
	selectedDependencyId?: string | null;
	/** JTBD id to center in the viewport. */
	focusJtbdId?: string | null;
	/** Increment to re-run focus even when `focusJtbdId` is unchanged. */
	focusRequest?: number;
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
	/**
	 * E-67 / JS-07: explicit viewport in layout coordinates. When set,
	 * the SVG-fallback mode renders only nodes whose bbox intersects
	 * this rectangle (with an overscan margin). When unset, the
	 * component reads `clientWidth/Height/scrollLeft/scrollTop` from
	 * the wrapper div on every scroll event.
	 *
	 * Tests pass the viewport directly to bypass the scroll listener
	 * (happy-dom does not lay out elements; clientWidth is always 0
	 * so the auto path collapses to "render nothing"). Production code
	 * leaves this unset.
	 */
	viewport?: JobMapViewport;
	/**
	 * E-67 / JS-07: opt-out of virtualisation. Defaults to the global
	 * threshold; set `false` to force-render every node, or a number
	 * to override the threshold per-instance.
	 */
	virtualise?: boolean | number;
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
	selected: boolean,
): { border: string; background: string } => {
	if (selected) {
		return { border: SELECTED_NODE_BORDER, background: SELECTED_NODE_FILL };
	}
	if (state === "active") {
		return { border: ACTIVE_NODE_BORDER, background: ACTIVE_NODE_FILL };
	}
	if (state === "fired") {
		return { border: FIRED_NODE_BORDER, background: FIRED_NODE_FILL };
	}
	return {
		border: cycle ? CYCLE_NODE_BORDER : NODE_BORDER,
		background: NODE_FILL,
	};
};

const toReactFlowNode = (
	n: NodeLayout,
	state: NodeAnimationState,
	selected: boolean,
): Node => {
	const { border, background } = styleForState(n.inCycle, state, selected);
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

const toReactFlowAuthoringEdge = (e: EdgeLayout, selected: boolean): Edge => ({
	...toReactFlowEdge(e),
	style: {
		stroke: e.crossLane ? CROSS_LANE_EDGE_COLOR : SAME_LANE_EDGE_COLOR,
		strokeWidth: selected ? 4 : 2,
	},
	selected,
});

export const JobMap = ({
	bundle,
	onSelectJtbd,
	onSelectDependency,
	selectedJtbdId,
	selectedDependencyId,
	focusJtbdId,
	focusRequest = 0,
	withReactFlow = true,
	className,
	firedIds,
	activeIds,
	viewport,
	virtualise,
}: JobMapProps): JSX.Element => {
	const layout = useMemo<JobMapLayout>(() => layoutJobMap(bundle), [bundle]);

	const nodes = useMemo(
		() =>
			layout.nodes.map((n) =>
				toReactFlowNode(
					n,
					animationStateFor(n.jtbdId, firedIds, activeIds),
					n.jtbdId === selectedJtbdId,
				),
			),
		[layout.nodes, firedIds, activeIds, selectedJtbdId],
	);
	const edges = useMemo(
		() => layout.edges.map((e) => toReactFlowAuthoringEdge(e, e.id === selectedDependencyId)),
		[layout.edges, selectedDependencyId],
	);
	const nodeMap = useMemo(() => new Map(layout.nodes.map((n) => [n.jtbdId, n])), [layout.nodes]);
	const nodeCount = nodes.length;

	// E-67 / JS-07: viewport-aware filtering for the SVG-fallback mode.
	const wrapperRef = useRef<HTMLDivElement | null>(null);
	const [autoViewport, setAutoViewport] = useState<JobMapViewport | null>(null);
	const [reactFlow, setReactFlow] = useState<ReactFlowInstance | null>(null);

	const threshold =
		virtualise === false
			? Number.POSITIVE_INFINITY
			: typeof virtualise === "number"
				? virtualise
				: VIRTUALISATION_THRESHOLD;
	const shouldVirtualise = !withReactFlow && nodeCount >= threshold;

	useEffect(() => {
		if (withReactFlow && nodeCount > VIRTUALISATION_THRESHOLD) {
			console.warn(
				`Flowforge JobMap is rendering ${nodeCount} ReactFlow nodes. Consider withReactFlow={false} to use the SVG fallback with viewport virtualisation.`,
			);
		}
	}, [nodeCount, withReactFlow]);

	useEffect(() => {
		if (!shouldVirtualise || viewport !== undefined) {
			return;
		}
		const el = wrapperRef.current;
		if (!el) {
			return;
		}
		const measure = (): void => {
			setAutoViewport({
				x: el.scrollLeft,
				y: el.scrollTop,
				width: el.clientWidth,
				height: el.clientHeight,
			});
		};
		measure();
		el.addEventListener("scroll", measure, { passive: true });
		// Window resize re-measures because the wrapper's clientWidth
		// follows the parent layout.
		window.addEventListener("resize", measure);
		return () => {
			el.removeEventListener("scroll", measure);
			window.removeEventListener("resize", measure);
		};
	}, [shouldVirtualise, viewport]);

	useEffect(() => {
		if (!focusJtbdId) {
			return;
		}
		const node = nodeMap.get(focusJtbdId);
		if (!node) {
			return;
		}
		const centerX = node.x + node.width / 2;
		const centerY = node.y + node.height / 2;
		if (withReactFlow) {
			reactFlow?.setCenter(centerX, centerY, { zoom: 1, duration: 300 });
			return;
		}
		const wrapper = wrapperRef.current;
		if (!wrapper || typeof wrapper.scrollTo !== "function") {
			return;
		}
		wrapper.scrollTo({
			left: Math.max(centerX - wrapper.clientWidth / 2, 0),
			top: Math.max(centerY - wrapper.clientHeight / 2, 0),
			behavior: "smooth",
		});
	}, [focusJtbdId, focusRequest, nodeMap, reactFlow, withReactFlow]);

	const effectiveViewport = viewport ?? autoViewport;
	const { visibleNodes, visibleEdges } = useMemo(() => {
		if (!shouldVirtualise || !effectiveViewport) {
			return {
				visibleNodes: layout.nodes,
				visibleEdges: layout.edges,
			};
		}
		const filteredNodes = nodesInViewport(layout.nodes, effectiveViewport);
		const visibleIds = new Set(filteredNodes.map((n) => n.jtbdId));
		return {
			visibleNodes: filteredNodes,
			visibleEdges: edgesInViewport(layout.edges, visibleIds),
		};
	}, [shouldVirtualise, effectiveViewport, layout.nodes, layout.edges]);

	if (!withReactFlow) {
		return (
			<div
				ref={wrapperRef}
				data-testid="ff-jobmap"
				role="region"
				aria-label="JTBD job map"
				className={className}
				data-virtualised={shouldVirtualise ? "true" : "false"}
				data-rendered-nodes={String(visibleNodes.length)}
				style={{ position: "relative", width: layout.width, height: layout.height }}
			>
				<svg
					width={layout.width}
					height={layout.height}
					data-testid="ff-jobmap-svg"
					style={{ position: "absolute", inset: 0 }}
				>
					<defs>
						<marker
							id="ff-jobmap-arrow"
							viewBox="0 0 10 10"
							refX="9"
							refY="5"
							markerWidth="6"
							markerHeight="6"
							orient="auto-start-reverse"
						>
							<path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
						</marker>
					</defs>
					{layout.lanes.map((lane) => (
						<LaneStrip key={lane.role} lane={lane} totalWidth={layout.width} />
					))}
					{visibleEdges.map((edge) => (
						<JobMapEdge
							key={edge.id}
							edge={edge}
							nodeMap={nodeMap}
							onSelect={onSelectDependency}
							selected={edge.id === selectedDependencyId}
						/>
					))}
				</svg>
				{visibleNodes.map((node) => (
					<JobMapNode
						key={node.jtbdId}
						node={node}
						onSelect={onSelectJtbd}
						animationState={animationStateFor(node.jtbdId, firedIds, activeIds)}
						selected={node.jtbdId === selectedJtbdId}
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
				onEdgeClick={(_, edge) => {
					if (onSelectDependency) {
						onSelectDependency(edge.id);
					}
				}}
				onInit={setReactFlow}
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
				stroke={LANE_BORDER}
				strokeWidth={1}
			/>
			<text
				x={12}
				y={lane.y + lane.height / 2}
				dominantBaseline="middle"
				fontSize={13}
				fontWeight={600}
				fill={LANE_TEXT}
				data-testid={`ff-jobmap-lane-label-${lane.role}`}
			>
				{lane.role}
			</text>
			<line
				x1={LANE_HEADER_WIDTH}
				y1={lane.y}
				x2={LANE_HEADER_WIDTH}
				y2={lane.y + lane.height}
				stroke={LANE_DIVIDER}
				strokeWidth={1}
			/>
		</g>
	);
};

interface JobMapNodeProps {
	node: NodeLayout;
	onSelect?: (jtbdId: string) => void;
	animationState?: NodeAnimationState;
	selected?: boolean;
}

const JobMapNode = ({
	node,
	onSelect,
	animationState = "default",
	selected = false,
}: JobMapNodeProps): JSX.Element => {
	const { border, background } = styleForState(node.inCycle, animationState, selected);
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
			data-selected={selected ? "true" : "false"}
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
				color: NODE_TEXT,
				transition: "background 200ms ease, border-color 200ms ease",
			}}
		>
			<strong style={{ fontSize: 13 }}>{node.title}</strong>
			<span style={{ color: NODE_MUTED_TEXT, fontSize: 11 }}>{node.jtbdId}</span>
		</div>
	);
};

interface JobMapEdgeProps {
	edge: EdgeLayout;
	nodeMap: ReadonlyMap<string, NodeLayout>;
	onSelect?: (dependencyId: string) => void;
	selected?: boolean;
}

const JobMapEdge = ({
	edge,
	nodeMap,
	onSelect,
	selected = false,
}: JobMapEdgeProps): JSX.Element | null => {
	const source = nodeMap.get(edge.source);
	const target = nodeMap.get(edge.target);
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
	const handleSelect = (): void => {
		if (onSelect) {
			onSelect(edge.id);
		}
	};
	const handleKeyDown = (event: React.KeyboardEvent<SVGPathElement>): void => {
		if (event.key === "Enter" || event.key === " ") {
			event.preventDefault();
			handleSelect();
		}
	};
	return (
		<path
			role={onSelect ? "button" : undefined}
			tabIndex={onSelect ? 0 : undefined}
			data-testid={`ff-jobmap-edge-${edge.id}`}
			data-crosslane={edge.crossLane ? "true" : "false"}
			data-selected={selected ? "true" : "false"}
			d={path}
			fill="none"
			stroke={stroke}
			strokeWidth={selected ? 4 : 2}
			markerEnd="url(#ff-jobmap-arrow)"
			onClick={handleSelect}
			onKeyDown={handleKeyDown}
			style={{
				cursor: onSelect ? "pointer" : "default",
				pointerEvents: "stroke",
			}}
		/>
	);
};
