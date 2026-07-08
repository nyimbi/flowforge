import {
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
	type CSSProperties,
	type JSX,
} from "react";
import ReactFlow, {
	Background,
	ConnectionMode,
	Controls,
	MarkerType,
	type Connection,
	type Edge,
	type EdgeChange,
	type Node,
	type NodeChange,
	type NodeMouseHandler,
	type OnSelectionChangeParams,
	type ReactFlowInstance,
} from "reactflow";
import { useStore } from "zustand";

import "reactflow/dist/style.css";

import { DiffViewer } from "./DiffViewer.js";
import { FormBuilder } from "./FormBuilder.js";
import { PropertyPanel } from "./PropertyPanel.js";
import { SimulationPanel } from "./SimulationPanel.js";
import {
	createDesignerStore,
	safeRedo,
	safeUndo,
	type CanvasPosition,
	type DesignerStore,
	type NodePaletteType,
} from "./store.js";
import type {
	FormSpec,
	ValidationIssue,
	WorkflowDef,
	WorkflowState,
	WorkflowTransition,
} from "./types.js";
import { validateWorkflow } from "./validation.js";

export type DesignerTab = "canvas" | "form" | "validation" | "simulation" | "diff";

export interface DesignerProps {
	workflow?: WorkflowDef;
	form?: FormSpec | null;
	/** Optional second workflow used by the diff tab. */
	compareTo?: WorkflowDef;
	/** Inject an external store; useful for tests and host apps that need to
	 * subscribe to designer state changes. */
	store?: DesignerStore;
	/** Skip reactflow's measured DOM render (used by tests). */
	withReactFlow?: boolean;
	/** Initial tab. Defaults to canvas. */
	initialTab?: DesignerTab;
	/** Optional host class hook for skinning. */
	className?: string;
	/** Optional host style hook, commonly used for CSS custom properties. */
	style?: CSSProperties;
}

type FlowNodeData = {
	label: string;
	kind: WorkflowState["kind"];
};

type FlowEdgeData = {
	event: string;
};

const PALETTE_MIME = "application/x-flowforge-node";

const STATE_COLORS: Record<WorkflowState["kind"], string> = {
	manual_review: "var(--ff-designer-state-manual-review, #7c3aed)",
	automatic: "var(--ff-designer-state-automatic, #2563eb)",
	parallel_fork: "var(--ff-designer-state-parallel-fork, #0ea5e9)",
	parallel_join: "var(--ff-designer-state-parallel-join, #0e7490)",
	timer: "var(--ff-designer-state-timer, #0891b2)",
	signal_wait: "var(--ff-designer-state-signal-wait, #a16207)",
	subworkflow: "var(--ff-designer-state-subworkflow, #475569)",
	terminal_success: "var(--ff-designer-state-terminal-success, #16a34a)",
	terminal_fail: "var(--ff-designer-state-terminal-fail, #dc2626)",
};

const PALETTE_ITEMS: Array<{
	type: NodePaletteType;
	label: string;
	title: string;
	icon: JSX.Element;
}> = [
	{
		type: "state",
		label: "State node",
		title: "State",
		icon: (
			<svg viewBox="0 0 20 20" aria-hidden="true" width="18" height="18">
				<circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
			</svg>
		),
	},
	{
		type: "transition",
		label: "Transition node",
		title: "Transition",
		icon: (
			<svg viewBox="0 0 20 20" aria-hidden="true" width="18" height="18">
				<path
					d="M4 10h10M10 6l4 4-4 4"
					fill="none"
					stroke="currentColor"
					strokeLinecap="round"
					strokeLinejoin="round"
					strokeWidth="2"
				/>
			</svg>
		),
	},
	{
		type: "task",
		label: "Task node",
		title: "Task",
		icon: (
			<svg viewBox="0 0 20 20" aria-hidden="true" width="18" height="18">
				<rect x="4" y="4" width="12" height="12" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
				<path
					d="M7 10l2 2 4-5"
					fill="none"
					stroke="currentColor"
					strokeLinecap="round"
					strokeLinejoin="round"
					strokeWidth="2"
				/>
			</svg>
		),
	},
	{
		type: "gate",
		label: "Gate node",
		title: "Gate",
		icon: (
			<svg viewBox="0 0 20 20" aria-hidden="true" width="18" height="18">
				<path d="M10 3l7 7-7 7-7-7 7-7z" fill="none" stroke="currentColor" strokeWidth="2" />
			</svg>
		),
	},
];

const layoutPosition = (index: number): CanvasPosition => ({
	x: 80 + (index % 4) * 220,
	y: 80 + Math.floor(index / 4) * 140,
});

const isNodePaletteType = (value: string): value is NodePaletteType =>
	value === "state" || value === "transition" || value === "task" || value === "gate";

const toNode = (
	state: WorkflowState,
	index: number,
	position: CanvasPosition | undefined,
	selected: boolean,
): Node<FlowNodeData> => ({
	id: state.id,
	position: position ?? layoutPosition(index),
	data: { label: state.name || state.id, kind: state.kind },
	selected,
	style: {
		borderRadius: 8,
		padding: 12,
		border: `2px solid ${STATE_COLORS[state.kind]}`,
		background: "var(--ff-designer-node-bg, #ffffff)",
		color: "var(--ff-designer-node-fg, #172033)",
		fontSize: 12,
		minWidth: 140,
		boxShadow: selected
			? "0 0 0 4px var(--ff-designer-node-selected, rgba(37, 99, 235, 0.18))"
			: "0 1px 2px rgba(15, 23, 42, 0.08)",
	},
	type: "default",
});

const toEdge = (transition: WorkflowTransition, selected: boolean): Edge<FlowEdgeData> => ({
	id: transition.id,
	source: transition.from,
	target: transition.to,
	label: transition.event,
	data: { event: transition.event },
	selected,
	labelStyle: { fontSize: 11, fill: "var(--ff-designer-edge-label, #374151)" },
	style: {
		stroke: selected
			? "var(--ff-designer-edge-selected, #2563eb)"
			: "var(--ff-designer-edge, #6b7280)",
		strokeWidth: selected ? 2.5 : 1.5,
	},
	markerEnd: { type: MarkerType.ArrowClosed },
	animated: Boolean(transition.guard),
});

const nextTransitionId = (transitions: WorkflowTransition[]): string => {
	const used = new Set(transitions.map((transition) => transition.id));
	let index = transitions.length + 1;
	let id = `transition_${index}`;
	while (used.has(id)) {
		index += 1;
		id = `transition_${index}`;
	}
	return id;
};

const inputTarget = (target: EventTarget | null): target is HTMLElement =>
	target instanceof HTMLElement;

const isEditableKeyTarget = (target: EventTarget | null): boolean => {
	if (!inputTarget(target)) return false;
	const tag = target.tagName.toLowerCase();
	return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
};

const issueTargetNodeId = (
	issue: ValidationIssue,
	workflow: WorkflowDef,
): string | null => {
	const stateIds = new Set(workflow.states.map((state) => state.id));
	const [kind, id, property] = issue.path.split("/");

	if (kind === "states" && id && stateIds.has(id)) {
		return id;
	}
	if (issue.path === "initial_state" && stateIds.has(workflow.initial_state)) {
		return workflow.initial_state;
	}
	if (kind === "terminal_states" && id && stateIds.has(id)) {
		return id;
	}
	if (kind !== "transitions" || !id) {
		return null;
	}

	const transition = workflow.transitions.find((candidate) => candidate.id === id);
	if (!transition) return null;
	if (property === "from" && stateIds.has(transition.from)) return transition.from;
	if (property === "to" && stateIds.has(transition.to)) return transition.to;
	if (stateIds.has(transition.from)) return transition.from;
	if (stateIds.has(transition.to)) return transition.to;
	return null;
};

interface NodePaletteProps {
	onAddNode: (type: NodePaletteType, position?: CanvasPosition) => void;
}

const NodePalette = ({ onAddNode }: NodePaletteProps): JSX.Element => (
	<aside
		data-testid="node-palette"
		aria-label="Node palette"
		className="ff-designer__node-palette"
		style={{
			borderRight: "1px solid var(--ff-designer-border, #e5e7eb)",
			padding: 12,
			background: "var(--ff-designer-panel-bg, #f8fafc)",
			display: "grid",
			alignContent: "start",
			gap: 8,
		}}
	>
		{PALETTE_ITEMS.map((item) => (
			<button
				key={item.type}
				type="button"
				draggable
				className="ff-designer__node-palette-item"
				data-testid={`palette-node-${item.type}`}
				aria-label={item.label}
				title={item.label}
				onClick={() => onAddNode(item.type)}
				onDragStart={(event) => {
					event.dataTransfer.effectAllowed = "copy";
					event.dataTransfer.setData(PALETTE_MIME, item.type);
					event.dataTransfer.setData("text/plain", item.type);
				}}
				style={{
					display: "grid",
					gridTemplateColumns: "24px minmax(0, 1fr)",
					alignItems: "center",
					gap: 8,
					width: "100%",
					minHeight: 40,
					border: "1px solid var(--ff-designer-border, #d1d5db)",
					borderRadius: 8,
					background: "var(--ff-designer-button-bg, #ffffff)",
					color: "var(--ff-designer-button-fg, #172033)",
					cursor: "grab",
					font: "inherit",
					textAlign: "left",
					padding: "8px 10px",
				}}
			>
				<span aria-hidden="true" style={{ display: "inline-flex" }}>
					{item.icon}
				</span>
				<span>{item.title}</span>
			</button>
		))}
	</aside>
);

interface EmptyCanvasStateProps {
	onAddState: () => void;
}

const EmptyCanvasState = ({ onAddState }: EmptyCanvasStateProps): JSX.Element => (
	<div
		data-testid="canvas-empty-state"
		className="ff-designer__canvas-empty"
		style={{
			position: "absolute",
			inset: 0,
			display: "grid",
			placeItems: "center",
			pointerEvents: "none",
		}}
	>
		<div
			style={{
				display: "grid",
				justifyItems: "center",
				gap: 10,
				color: "var(--ff-designer-muted, #475569)",
				pointerEvents: "auto",
			}}
		>
			<svg
				viewBox="0 0 56 56"
				width="56"
				height="56"
				aria-hidden="true"
				style={{ color: "var(--ff-designer-accent, #2563eb)" }}
			>
				<circle cx="14" cy="16" r="6" fill="none" stroke="currentColor" strokeWidth="3" />
				<circle cx="42" cy="16" r="6" fill="none" stroke="currentColor" strokeWidth="3" />
				<circle cx="28" cy="40" r="6" fill="none" stroke="currentColor" strokeWidth="3" />
				<path
					d="M20 16h16M18 21l7 13M38 21l-7 13"
					fill="none"
					stroke="currentColor"
					strokeLinecap="round"
					strokeWidth="3"
				/>
			</svg>
			<strong style={{ color: "var(--ff-designer-fg, #172033)" }}>Add your first state</strong>
			<button
				type="button"
				data-testid="canvas-empty-add-state"
				onClick={onAddState}
				style={{
					border: 0,
					borderRadius: 8,
					background: "var(--ff-designer-accent, #2563eb)",
					color: "#ffffff",
					cursor: "pointer",
					font: "inherit",
					fontWeight: 600,
					padding: "8px 12px",
				}}
			>
				+ Add State
			</button>
		</div>
	</div>
);

interface EditableCanvasProps {
	store: DesignerStore;
	withReactFlow: boolean;
	selectedNodeIds: string[];
	selectedTransitionIds: string[];
	focusNodeId: string | null;
	onFocusHandled: () => void;
	onAddNode: (type: NodePaletteType, position?: CanvasPosition) => void;
	onSelectedNodeIdsChange: (ids: string[]) => void;
	onSelectedTransitionIdsChange: (ids: string[]) => void;
}

const EditableCanvas = ({
	store,
	withReactFlow,
	selectedNodeIds,
	selectedTransitionIds,
	focusNodeId,
	onFocusHandled,
	onAddNode,
	onSelectedNodeIdsChange,
	onSelectedTransitionIdsChange,
}: EditableCanvasProps): JSX.Element => {
	const wrapperRef = useRef<HTMLDivElement | null>(null);
	const [reactFlowInstance, setReactFlowInstance] =
		useState<ReactFlowInstance<FlowNodeData, FlowEdgeData> | null>(null);
	const workflow = store((s) => s.workflow);
	const nodeMeta = store((s) => s.nodes);
	const select = store((s) => s.select);
	const updateNodePosition = store((s) => s.updateNodePosition);
	const removeElements = store((s) => s.removeElements);
	const addTransition = store((s) => s.addTransition);

	const selectedNodeSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds]);
	const selectedTransitionSet = useMemo(
		() => new Set(selectedTransitionIds),
		[selectedTransitionIds],
	);

	const nodes = useMemo(
		() =>
			workflow.states.map((state, index) =>
				toNode(state, index, nodeMeta[state.id]?.position, selectedNodeSet.has(state.id)),
			),
		[nodeMeta, selectedNodeSet, workflow.states],
	);
	const edges = useMemo(
		() =>
			workflow.transitions.map((transition) =>
				toEdge(transition, selectedTransitionSet.has(transition.id)),
			),
		[selectedTransitionSet, workflow.transitions],
	);

	const syncSelection = useCallback(
		(nextNodeIds: string[], nextTransitionIds: string[]): void => {
			onSelectedNodeIdsChange(nextNodeIds);
			onSelectedTransitionIdsChange(nextTransitionIds);
			if (nextNodeIds.length === 1 && nextTransitionIds.length === 0) {
				select({ kind: "state", id: nextNodeIds[0] });
			} else if (nextTransitionIds.length === 1 && nextNodeIds.length === 0) {
				select({ kind: "transition", id: nextTransitionIds[0] });
			} else {
				select({ kind: "none" });
			}
		},
		[onSelectedNodeIdsChange, onSelectedTransitionIdsChange, select],
	);

	const onNodeClick: NodeMouseHandler = (_event, node) => {
		syncSelection([node.id], []);
	};
	const onEdgeClick = (_event: React.MouseEvent, edge: Edge<FlowEdgeData>): void => {
		syncSelection([], [edge.id]);
	};

	const onNodesChange = useCallback(
		(changes: NodeChange[]): void => {
			const removed: string[] = [];
			let nextSelected: Set<string> | null = null;
			for (const change of changes) {
				if (change.type === "position" && change.position) {
					updateNodePosition(change.id, change.position);
				}
				if (change.type === "remove") {
					removed.push(change.id);
				}
				if (change.type === "select") {
					nextSelected = nextSelected ?? new Set(selectedNodeIds);
					if (change.selected) {
						nextSelected.add(change.id);
					} else {
						nextSelected.delete(change.id);
					}
				}
			}

			if (removed.length > 0) {
				removeElements({ stateIds: removed });
				onSelectedNodeIdsChange(selectedNodeIds.filter((id) => !removed.includes(id)));
			}
			if (nextSelected) {
				onSelectedNodeIdsChange([...nextSelected]);
			}
		},
		[
			onSelectedNodeIdsChange,
			removeElements,
			selectedNodeIds,
			updateNodePosition,
		],
	);

	const onEdgesChange = useCallback(
		(changes: EdgeChange[]): void => {
			const removed: string[] = [];
			let nextSelected: Set<string> | null = null;
			for (const change of changes) {
				if (change.type === "remove") {
					removed.push(change.id);
				}
				if (change.type === "select") {
					nextSelected = nextSelected ?? new Set(selectedTransitionIds);
					if (change.selected) {
						nextSelected.add(change.id);
					} else {
						nextSelected.delete(change.id);
					}
				}
			}

			if (removed.length > 0) {
				removeElements({ transitionIds: removed });
				onSelectedTransitionIdsChange(
					selectedTransitionIds.filter((id) => !removed.includes(id)),
				);
			}
			if (nextSelected) {
				onSelectedTransitionIdsChange([...nextSelected]);
			}
		},
		[
			onSelectedTransitionIdsChange,
			removeElements,
			selectedTransitionIds,
		],
	);

	const onConnect = useCallback(
		(connection: Connection): void => {
			if (!connection.source || !connection.target || connection.source === connection.target) {
				return;
			}
			const id = nextTransitionId(workflow.transitions);
			addTransition({
				id,
				from: connection.source,
				to: connection.target,
				event: `to_${connection.target}`,
			});
			syncSelection([], [id]);
		},
		[addTransition, syncSelection, workflow.transitions],
	);

	const onSelectionChange = useCallback(
		(params: OnSelectionChangeParams): void => {
			syncSelection(
				params.nodes.map((node) => node.id),
				params.edges.map((edge) => edge.id),
			);
		},
		[syncSelection],
	);

	const dropPosition = useCallback(
		(event: React.DragEvent<HTMLDivElement>): CanvasPosition => {
			if (reactFlowInstance) {
				return reactFlowInstance.screenToFlowPosition({
					x: event.clientX,
					y: event.clientY,
				});
			}
			const bounds = wrapperRef.current?.getBoundingClientRect();
			return {
				x: bounds ? event.clientX - bounds.left : 80,
				y: bounds ? event.clientY - bounds.top : 80,
			};
		},
		[reactFlowInstance],
	);

	const onDrop = useCallback(
		(event: React.DragEvent<HTMLDivElement>): void => {
			event.preventDefault();
			const rawType =
				event.dataTransfer.getData(PALETTE_MIME) ||
				event.dataTransfer.getData("text/plain");
			if (!isNodePaletteType(rawType)) return;
			onAddNode(rawType, dropPosition(event));
		},
		[dropPosition, onAddNode],
	);

	const onDragOver = useCallback((event: React.DragEvent<HTMLDivElement>): void => {
		event.preventDefault();
		event.dataTransfer.dropEffect = "copy";
	}, []);

	useEffect(() => {
		if (!focusNodeId) return;
		if (!withReactFlow) {
			onFocusHandled();
			return;
		}
		if (!reactFlowInstance || !workflow.states.some((state) => state.id === focusNodeId)) {
			return;
		}
		window.requestAnimationFrame(() => {
			reactFlowInstance.fitView({
				nodes: [{ id: focusNodeId }],
				padding: 0.35,
				duration: 250,
			});
			onFocusHandled();
		});
	}, [focusNodeId, onFocusHandled, reactFlowInstance, withReactFlow, workflow.states]);

	const emptyState = (
		<EmptyCanvasState
			onAddState={() => onAddNode("state", reactFlowInstance?.screenToFlowPosition({ x: 180, y: 160 }))}
		/>
	);

	return (
		<section
			className="ff-designer__canvas-shell"
			style={{
				display: "grid",
				gridTemplateColumns: "180px minmax(0, 1fr)",
				minHeight: 480,
				minWidth: 0,
				border: "1px solid var(--ff-designer-border, #e5e7eb)",
				borderRadius: 8,
				overflow: "hidden",
				background: "var(--ff-designer-canvas-bg, #ffffff)",
			}}
		>
			<NodePalette onAddNode={onAddNode} />
			<div
				ref={wrapperRef}
				data-testid="ff-canvas"
				role="region"
				aria-label="Workflow canvas"
				onDragOver={onDragOver}
				onDrop={onDrop}
				style={{ position: "relative", width: "100%", height: "100%", minHeight: 480 }}
			>
				{withReactFlow ? (
					<ReactFlow
						nodes={nodes}
						edges={edges}
						onInit={setReactFlowInstance}
						onNodesChange={onNodesChange}
						onEdgesChange={onEdgesChange}
						onNodeClick={onNodeClick}
						onEdgeClick={onEdgeClick}
						onConnect={onConnect}
						onSelectionChange={onSelectionChange}
						connectionMode={ConnectionMode.Loose}
						deleteKeyCode={null}
						multiSelectionKeyCode={["Meta", "Control", "Shift"]}
						selectionOnDrag
						fitView
						proOptions={{ hideAttribution: true }}
					>
						<Background />
						<Controls />
					</ReactFlow>
				) : (
					<div style={{ padding: 16 }}>
						<ul>
							{workflow.states.map((state) => (
								<li
									key={state.id}
									data-testid={`canvas-state-${state.id}`}
									onClick={() => syncSelection([state.id], [])}
								>
									{state.name} ({state.kind})
								</li>
							))}
						</ul>
						<ul>
							{workflow.transitions.map((transition) => (
								<li
									key={transition.id}
									data-testid={`canvas-transition-${transition.id}`}
									onClick={() => syncSelection([], [transition.id])}
								>
									{transition.from} -&gt; {transition.to}: {transition.event}
								</li>
							))}
						</ul>
					</div>
				)}
				{workflow.states.length === 0 ? emptyState : null}
			</div>
		</section>
	);
};

interface ClickableValidationPanelProps {
	store: DesignerStore;
	onIssueFocus: (issue: ValidationIssue) => void;
}

const ClickableValidationPanel = ({
	store,
	onIssueFocus,
}: ClickableValidationPanelProps): JSX.Element => {
	const workflow = store((s) => s.workflow);
	const issues = useMemo(() => validateWorkflow(workflow), [workflow]);
	const errors = issues.filter((issue) => issue.severity === "error");
	const warnings = issues.filter((issue) => issue.severity === "warning");

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
					{issues.map((issue, index) => (
						<li
							key={`${issue.code}-${index}`}
							data-severity={issue.severity}
						>
							<button
								type="button"
								data-testid={`validation-issue-${issue.code}-${index}`}
								data-target-node={issueTargetNodeId(issue, workflow) ?? ""}
								onClick={() => onIssueFocus(issue)}
								style={{
									width: "100%",
									border: "1px solid var(--ff-designer-border, #e5e7eb)",
									borderRadius: 8,
									background: "var(--ff-designer-button-bg, #ffffff)",
									color: "inherit",
									cursor: "pointer",
									font: "inherit",
									padding: "8px 10px",
									textAlign: "left",
								}}
							>
								<strong>[{issue.severity}]</strong> {issue.path}: {issue.message}{" "}
								<code>({issue.code})</code>
							</button>
						</li>
					))}
				</ul>
			)}
		</section>
	);
};

export const Designer = ({
	workflow,
	form,
	compareTo,
	store: externalStore,
	withReactFlow = true,
	initialTab = "canvas",
	className,
	style,
}: DesignerProps): JSX.Element => {
	const internalStore = useMemo(
		() =>
			externalStore ??
			createDesignerStore({ workflow, form: form ?? null }),
		// Intentionally only build once per Designer mount.
		// eslint-disable-next-line react-hooks/exhaustive-deps
		[],
	);
	const store = externalStore ?? internalStore;
	const previousWorkflowProp = useRef(workflow);
	const previousFormProp = useRef(form);
	const [tab, setTab] = useState<DesignerTab>(initialTab);
	const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
	const [selectedTransitionIds, setSelectedTransitionIds] = useState<string[]>([]);
	const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
	const selectedNodeIdsRef = useRef<string[]>(selectedNodeIds);
	const selectedTransitionIdsRef = useRef<string[]>(selectedTransitionIds);
	const currentWorkflowRef = useRef<WorkflowDef | null>(null);
	const tabRef = useRef<DesignerTab>(tab);

	useEffect(() => {
		if (externalStore) return;
		if (workflow !== undefined && workflow !== previousWorkflowProp.current) {
			internalStore.getState().setWorkflow(workflow);
		}
		previousWorkflowProp.current = workflow;
	}, [externalStore, internalStore, workflow]);

	useEffect(() => {
		if (externalStore) return;
		if (form !== previousFormProp.current) {
			internalStore.getState().setForm(form ?? null);
		}
		previousFormProp.current = form;
	}, [externalStore, form, internalStore]);

	const undo = useCallback((): void => {
		safeUndo(store);
	}, [store]);
	const redo = useCallback((): void => {
		safeRedo(store);
	}, [store]);
	const pastSize = useStore(store.temporal, (t) => t.pastStates.length);
	const futureSize = useStore(store.temporal, (t) => t.futureStates.length);

	const currentWorkflow = store((s) => s.workflow);
	const rootClassName = ["ff-designer", className].filter(Boolean).join(" ");

	useEffect(() => {
		selectedNodeIdsRef.current = selectedNodeIds;
	}, [selectedNodeIds]);

	useEffect(() => {
		selectedTransitionIdsRef.current = selectedTransitionIds;
	}, [selectedTransitionIds]);

	useEffect(() => {
		currentWorkflowRef.current = currentWorkflow;
	}, [currentWorkflow]);

	useEffect(() => {
		tabRef.current = tab;
	}, [tab]);

	const addNode = useCallback(
		(type: NodePaletteType, position: CanvasPosition = { x: 80, y: 80 }): void => {
			store.getState().addNode({ type, position });
			setTab("canvas");
		},
		[store],
	);

	const clearSelection = useCallback((): void => {
		setSelectedNodeIds([]);
		setSelectedTransitionIds([]);
		store.getState().select({ kind: "none" });
	}, [store]);

	const removeSelected = useCallback((): void => {
		const stateIds = selectedNodeIdsRef.current;
		const transitionIds = selectedTransitionIdsRef.current;
		if (stateIds.length === 0 && transitionIds.length === 0) return;
		store.getState().removeElements({
			stateIds,
			transitionIds,
		});
		clearSelection();
	}, [clearSelection, store]);

	const focusIssue = useCallback(
		(issue: ValidationIssue): void => {
			const nodeId = issueTargetNodeId(issue, currentWorkflow);
			if (!nodeId) return;
			setSelectedNodeIds([nodeId]);
			setSelectedTransitionIds([]);
			store.getState().select({ kind: "state", id: nodeId });
			setFocusNodeId(nodeId);
			setTab("canvas");
		},
		[currentWorkflow, store],
	);

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent): void => {
			if (isEditableKeyTarget(event.target)) return;
			const key = event.key.toLowerCase();
			const commandKey = event.ctrlKey || event.metaKey;

			if (event.key === "Delete" || event.key === "Backspace") {
				if (
					selectedNodeIdsRef.current.length > 0 ||
					selectedTransitionIdsRef.current.length > 0
				) {
					event.preventDefault();
					removeSelected();
				}
				return;
			}

			if (commandKey && key === "z" && event.shiftKey) {
				event.preventDefault();
				redo();
				return;
			}
			if (commandKey && key === "z") {
				event.preventDefault();
				undo();
				return;
			}
			if (commandKey && key === "y") {
				event.preventDefault();
				redo();
				return;
			}
			if (commandKey && key === "a" && tabRef.current === "canvas") {
				const workflowForSelection = currentWorkflowRef.current;
				if (!workflowForSelection) return;
				event.preventDefault();
				setSelectedNodeIds(workflowForSelection.states.map((state) => state.id));
				setSelectedTransitionIds(
					workflowForSelection.transitions.map((transition) => transition.id),
				);
				store.getState().select({ kind: "none" });
				return;
			}
			if (event.key === "Escape") {
				event.preventDefault();
				clearSelection();
			}
		};

		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, [
		clearSelection,
		redo,
		removeSelected,
		store,
		undo,
	]);

	return (
		<div
			data-testid="ff-designer"
			aria-label="Flowforge designer"
			className={rootClassName}
			style={style}
		>
			<header data-testid="designer-toolbar" className="ff-designer__toolbar">
				<nav aria-label="Designer tabs" className="ff-designer__tabs">
					{(["canvas", "form", "validation", "simulation", "diff"] as DesignerTab[]).map(
						(t) => (
							<button
								key={t}
								type="button"
								className="ff-designer__tab"
								data-testid={`tab-${t}`}
								data-active={tab === t}
								aria-pressed={tab === t}
								onClick={() => setTab(t)}
							>
								{t}
							</button>
						),
					)}
				</nav>
				<button
					type="button"
					className="ff-designer__undo"
					data-testid="undo"
					onClick={undo}
					disabled={pastSize === 0}
				>
					Undo ({pastSize})
				</button>
				<button
					type="button"
					className="ff-designer__redo"
					data-testid="redo"
					onClick={redo}
					disabled={futureSize === 0}
				>
					Redo ({futureSize})
				</button>
			</header>

			<main data-testid="designer-main" className="ff-designer__main">
				{tab === "canvas" ? (
					<>
						<EditableCanvas
							store={store}
							withReactFlow={withReactFlow}
							selectedNodeIds={selectedNodeIds}
							selectedTransitionIds={selectedTransitionIds}
							focusNodeId={focusNodeId}
							onFocusHandled={() => setFocusNodeId(null)}
							onAddNode={addNode}
							onSelectedNodeIdsChange={setSelectedNodeIds}
							onSelectedTransitionIdsChange={setSelectedTransitionIds}
						/>
						<PropertyPanel store={store} />
					</>
				) : null}
				{tab === "form" ? (
					<>
						<FormBuilder store={store} />
						<PropertyPanel store={store} />
					</>
				) : null}
				{tab === "validation" ? (
					<ClickableValidationPanel store={store} onIssueFocus={focusIssue} />
				) : null}
				{tab === "simulation" ? <SimulationPanel store={store} /> : null}
				{tab === "diff" ? (
					compareTo ? (
						<DiffViewer before={compareTo} after={currentWorkflow} />
					) : (
						<p data-testid="diff-no-compare">
							Pass a `compareTo` workflow to see version diffs.
						</p>
					)
				) : null}
			</main>
		</div>
	);
};
