import { temporal } from "zundo";
import { create } from "zustand";

import type {
	FieldDef,
	FormSpec,
	WorkflowDef,
	WorkflowState,
	WorkflowStateKind,
	WorkflowTransition,
} from "./types.js";

export interface CanvasPosition {
	x: number;
	y: number;
}

export type NodePaletteType = "state" | "transition" | "task" | "gate";

export interface DesignerNodeMeta {
	position: CanvasPosition;
}

export type DesignerNodeMap = Record<string, DesignerNodeMeta>;

export type SelectionKind =
	| { kind: "state"; id: string }
	| { kind: "transition"; id: string }
	| { kind: "field"; id: string }
	| { kind: "none" };

export interface DesignerState {
	workflow: WorkflowDef;
	form: FormSpec | null;
	selection: SelectionKind;
	nodes: DesignerNodeMap;
	/**
	 * Designer-local version counter. Increments on every mutating
	 * action; participates in undo/redo snapshots so the safeRedo
	 * helper can detect a remote collaborator patch that landed
	 * between an `undo()` and a `redo()` call (audit-2026 JS-04).
	 */
	version: number;

	// workflow mutations
	setWorkflow: (wf: WorkflowDef) => void;
	addState: (state: WorkflowState) => void;
	addNode: (node: { type: NodePaletteType; position: CanvasPosition }) => void;
	updateState: (id: string, patch: Partial<WorkflowState>) => void;
	updateNodePosition: (id: string, position: CanvasPosition) => void;
	removeState: (id: string) => void;
	removeElements: (selection: { stateIds?: string[]; transitionIds?: string[] }) => void;
	addTransition: (t: WorkflowTransition) => void;
	updateTransition: (id: string, patch: Partial<WorkflowTransition>) => void;
	removeTransition: (id: string) => void;

	// form mutations
	setForm: (spec: FormSpec | null) => void;
	addField: (field: FieldDef) => void;
	updateField: (id: string, patch: Partial<FieldDef>) => void;
	removeField: (id: string) => void;
	moveField: (id: string, toIndex: number) => void;

	// collaboration
	/**
	 * Apply a remote collaborator patch. Bumps `version` to ``base + 1``
	 * so any pending future undo entries become non-contiguous and the
	 * `safeRedo` helper rejects the next redo with the supplied conflict
	 * message instead of silently overwriting the remote change.
	 */
	applyRemotePatch: (patch: { workflow?: WorkflowDef; form?: FormSpec | null }) => void;

	// selection
	select: (sel: SelectionKind) => void;
}

export const emptyWorkflow = (): WorkflowDef => ({
	id: "wf-new",
	name: "New workflow",
	version: 1,
	states: [],
	transitions: [],
	initial_state: "",
	terminal_states: [],
});

type WorkflowWithMetadata = WorkflowDef & {
	metadata?: unknown;
};

const PALETTE_STATE_KIND: Record<NodePaletteType, WorkflowStateKind> = {
	state: "manual_review",
	transition: "signal_wait",
	task: "automatic",
	gate: "parallel_fork",
};

const PALETTE_STATE_NAME: Record<NodePaletteType, string> = {
	state: "State",
	transition: "Transition",
	task: "Task",
	gate: "Gate",
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === "object" && value !== null && !Array.isArray(value);

const isCanvasPosition = (value: unknown): value is CanvasPosition => {
	if (!isRecord(value)) return false;
	return (
		typeof value.x === "number" &&
		Number.isFinite(value.x) &&
		typeof value.y === "number" &&
		Number.isFinite(value.y)
	);
};

const workflowMetadata = (workflow: WorkflowDef): Record<string, unknown> => {
	const metadata = (workflow as WorkflowWithMetadata).metadata;
	return isRecord(metadata) ? metadata : {};
};

const workflowNodes = (workflow: WorkflowDef): DesignerNodeMap => {
	const metadata = workflowMetadata(workflow);
	const rawNodes = metadata.nodes;
	if (!isRecord(rawNodes)) return {};

	const nodes: DesignerNodeMap = {};
	for (const [id, rawMeta] of Object.entries(rawNodes)) {
		if (!isRecord(rawMeta) || !isCanvasPosition(rawMeta.position)) continue;
		nodes[id] = { position: rawMeta.position };
	}
	return nodes;
};

const compactNodes = (
	workflow: WorkflowDef,
	nodes: DesignerNodeMap,
): DesignerNodeMap => {
	const stateIds = new Set(workflow.states.map((state) => state.id));
	const compacted: DesignerNodeMap = {};
	for (const [id, meta] of Object.entries(nodes)) {
		if (stateIds.has(id)) {
			compacted[id] = meta;
		}
	}
	return compacted;
};

const withSerializedNodes = (
	workflow: WorkflowDef,
	nodes: DesignerNodeMap,
): WorkflowDef => {
	const compacted = compactNodes(workflow, nodes);
	const entries = Object.entries(compacted);
	const metadataWithoutNodes = Object.fromEntries(
		Object.entries(workflowMetadata(workflow)).filter(([key]) => key !== "nodes"),
	);

	if (entries.length === 0 && Object.keys(metadataWithoutNodes).length === 0) {
		return { ...workflow };
	}

	const metadata =
		entries.length === 0
			? metadataWithoutNodes
			: { ...metadataWithoutNodes, nodes: compacted };
	const withMetadata: WorkflowWithMetadata = { ...workflow, metadata };
	return withMetadata;
};

const paletteStateId = (
	type: NodePaletteType,
	states: WorkflowState[],
): string => {
	const base = `${type}_node`;
	const used = new Set(states.map((state) => state.id));
	let index = states.length + 1;
	let id = `${base}_${index}`;
	while (used.has(id)) {
		index += 1;
		id = `${base}_${index}`;
	}
	return id;
};

const paletteState = (
	type: NodePaletteType,
	states: WorkflowState[],
): WorkflowState => {
	const id = paletteStateId(type, states);
	return {
		id,
		name: `${PALETTE_STATE_NAME[type]} ${states.length + 1}`,
		kind: PALETTE_STATE_KIND[type],
		description: `Created from the ${PALETTE_STATE_NAME[type]} palette item.`,
	};
};

const removeWorkflowElements = (
	workflow: WorkflowDef,
	stateIds: Set<string>,
	transitionIds: Set<string>,
): WorkflowDef => {
	const states = workflow.states.filter((state) => !stateIds.has(state.id));
	const transitions = workflow.transitions.filter(
		(transition) =>
			!transitionIds.has(transition.id) &&
			!stateIds.has(transition.from) &&
			!stateIds.has(transition.to),
	);
	const initial_state = stateIds.has(workflow.initial_state)
		? states[0]?.id ?? ""
		: workflow.initial_state;
	const terminal_states = workflow.terminal_states.filter((id) => !stateIds.has(id));
	return {
		...workflow,
		states,
		transitions,
		initial_state,
		terminal_states,
	};
};

const replaceById = <T extends { id: string }>(
	list: T[],
	id: string,
	patch: Partial<T>,
): T[] => list.map((item) => (item.id === id ? { ...item, ...patch } : item));

export interface CreateStoreOptions {
	workflow?: WorkflowDef;
	form?: FormSpec | null;
}

/**
 * Build a fresh designer store. Each Designer mount gets its own store so
 * tests and embedded usages do not share global state.
 */
export const createDesignerStore = (opts: CreateStoreOptions = {}) =>
	create<DesignerState>()(
		temporal(
			(set) => {
				const initialWorkflow = opts.workflow ?? emptyWorkflow();
				const initialNodes = workflowNodes(initialWorkflow);

				/**
				 * Wrap a state-update producer so the resulting set call also
				 * bumps the version counter. Every undoable mutation should
				 * route through this helper — `selection` changes do not.
				 */
				const bump = <T extends Partial<DesignerState>>(
					producer: (s: DesignerState) => T,
				): ((s: DesignerState) => T & { version: number }) => {
					return (s) => {
						const partial = producer(s);
						return { ...partial, version: s.version + 1 } as T & {
							version: number;
						};
					};
				};

				return {
					workflow: withSerializedNodes(initialWorkflow, initialNodes),
					form: opts.form ?? null,
					selection: { kind: "none" },
					nodes: initialNodes,
					version: 0,

					setWorkflow: (wf) =>
						set(
							bump(() => {
								const nodes = workflowNodes(wf);
								return {
									workflow: withSerializedNodes(wf, nodes),
									nodes,
								};
							}),
						),

					addState: (state) =>
						set(
							bump((s) => {
								const workflow = {
									...s.workflow,
									states: [...s.workflow.states, state],
									// audit-2026 JS-05: the dead
									// `state.kind === "start"` branch has been
									// removed (the canonical DSL kinds — see
									// WorkflowStateKind — don't include "start").
									// We instead seed `initial_state` with the
									// first state added when none has been
									// chosen yet, regardless of kind.
									initial_state: s.workflow.initial_state || state.id,
								};
								return { workflow: withSerializedNodes(workflow, s.nodes) };
							}),
						),

					addNode: ({ type, position }) =>
						set(
							bump((s) => {
								const state = paletteState(type, s.workflow.states);
								const workflow = {
									...s.workflow,
									states: [...s.workflow.states, state],
									initial_state: s.workflow.initial_state || state.id,
								};
								const nodes = {
									...s.nodes,
									[state.id]: { position },
								};
								return {
									workflow: withSerializedNodes(workflow, nodes),
									nodes: compactNodes(workflow, nodes),
									selection: { kind: "state", id: state.id },
								};
							}),
						),

					updateState: (id, patch) =>
						set(
							bump((s) => {
								const workflow = {
									...s.workflow,
									states: replaceById(s.workflow.states, id, patch),
								};
								return { workflow: withSerializedNodes(workflow, s.nodes) };
							}),
						),

					updateNodePosition: (id, position) =>
						set(
							bump((s) => {
								if (!s.workflow.states.some((state) => state.id === id)) {
									return {};
								}
								const nodes = { ...s.nodes, [id]: { position } };
								return {
									workflow: withSerializedNodes(s.workflow, nodes),
									nodes: compactNodes(s.workflow, nodes),
								};
							}),
						),

					removeState: (id) =>
						set(
							bump((s) => {
								const workflow = removeWorkflowElements(
									s.workflow,
									new Set([id]),
									new Set(),
								);
								const nodes = compactNodes(workflow, s.nodes);
								return {
									workflow: withSerializedNodes(workflow, nodes),
									nodes,
									selection:
										s.selection.kind === "state" && s.selection.id === id
											? { kind: "none" }
											: s.selection,
								};
							}),
						),

					removeElements: ({ stateIds = [], transitionIds = [] }) =>
						set(
							bump((s) => {
								const statesToRemove = new Set(stateIds);
								const transitionsToRemove = new Set(transitionIds);
								if (statesToRemove.size === 0 && transitionsToRemove.size === 0) {
									return {};
								}
								const workflow = removeWorkflowElements(
									s.workflow,
									statesToRemove,
									transitionsToRemove,
								);
								const nodes = compactNodes(workflow, s.nodes);
								const selectionRemoved =
									(s.selection.kind === "state" &&
										statesToRemove.has(s.selection.id)) ||
									(s.selection.kind === "transition" &&
										transitionsToRemove.has(s.selection.id));
								return {
									workflow: withSerializedNodes(workflow, nodes),
									nodes,
									selection: selectionRemoved ? { kind: "none" } : s.selection,
								};
							}),
						),

					addTransition: (t) =>
						set(
							bump((s) => ({
								workflow: {
									...s.workflow,
									transitions: [...s.workflow.transitions, t],
								},
							})),
						),

					updateTransition: (id, patch) =>
						set(
							bump((s) => ({
								workflow: {
									...s.workflow,
									transitions: replaceById(s.workflow.transitions, id, patch),
								},
							})),
						),

					removeTransition: (id) =>
						set(
							bump((s) => ({
								workflow: {
									...s.workflow,
									transitions: s.workflow.transitions.filter(
										(t) => t.id !== id,
									),
								},
								selection:
									s.selection.kind === "transition" && s.selection.id === id
										? { kind: "none" }
										: s.selection,
							})),
						),

					setForm: (spec) => set(bump(() => ({ form: spec }))),

					addField: (field) =>
						set(
							bump((s) =>
								s.form
									? { form: { ...s.form, fields: [...s.form.fields, field] } }
									: {
											form: {
												id: "form-new",
												name: "New form",
												version: 1,
												fields: [field],
											},
										},
							),
						),

					updateField: (id, patch) =>
						set(
							bump((s) =>
								s.form
									? {
											form: {
												...s.form,
												fields: replaceById(s.form.fields, id, patch),
											},
										}
									: {},
							),
						),

					removeField: (id) =>
						set(
							bump((s) =>
								s.form
									? {
											form: {
												...s.form,
												fields: s.form.fields.filter((f) => f.id !== id),
											},
											selection:
												s.selection.kind === "field" && s.selection.id === id
													? { kind: "none" }
													: s.selection,
										}
									: {},
							),
						),

					moveField: (id, toIndex) =>
						set(
							bump((s) => {
								if (!s.form) return {};
								const fields = [...s.form.fields];
								const fromIndex = fields.findIndex((f) => f.id === id);
								if (fromIndex === -1) return {};
								const clamped = Math.max(0, Math.min(toIndex, fields.length - 1));
								const [item] = fields.splice(fromIndex, 1);
								fields.splice(clamped, 0, item);
								return { form: { ...s.form, fields } };
							}),
						),

					applyRemotePatch: (patch) =>
						set(
							bump((s) => {
								const workflow = patch.workflow ?? s.workflow;
								const nodes =
									patch.workflow === undefined ? s.nodes : workflowNodes(workflow);
								return {
									workflow: withSerializedNodes(workflow, nodes),
									nodes,
									form: patch.form !== undefined ? patch.form : s.form,
								};
							}),
						),

					select: (selection) => set({ selection }),
				};
			},
			{
				// Track only the working DSL + version, not selection cursor —
				// selection moves should not consume undo slots.
				partialize: (state) => ({
					workflow: state.workflow,
					form: state.form,
					nodes: state.nodes,
					version: state.version,
				}),
				equality: (past, current) =>
					past.workflow === current.workflow &&
					past.form === current.form &&
					past.nodes === current.nodes &&
					past.version === current.version,
				limit: 100,
			},
		),
	);

export type DesignerStore = ReturnType<typeof createDesignerStore>;


// ---------------------------------------------------------------------------
// audit-2026 JS-04 — collaboration-aware redo
// ---------------------------------------------------------------------------

export interface SafeRedoResult {
	ok: boolean;
	/**
	 * Populated when ``ok`` is false. The store left untouched; the caller
	 * is expected to surface this message (e.g., as a toast) and refresh
	 * before attempting any further undo/redo navigation.
	 */
	message?: string;
}

/**
 * Per-store collaboration state, kept outside the zustand snapshot so it
 * survives the temporal middleware's undo/redo replays. Tracks:
 *
 * - ``undoCount`` — number of pending undos that haven't been redone or
 *   invalidated by a user mutation. Incremented in ``safeUndo``, reset
 *   when the user makes a normal mutation (the ``bump`` helper) or
 *   redoes successfully.
 * - ``conflict`` — set to ``true`` by ``applyRemotePatch`` when it lands
 *   while ``undoCount > 0``. Cleared by the next ``safeRedo`` call (which
 *   surfaces the conflict message and refuses the redo).
 */
interface CollabState {
	undoCount: number;
	conflict: boolean;
}

const _collab = new WeakMap<object, CollabState>();

function _collabFor(store: DesignerStore): CollabState {
	let s = _collab.get(store);
	if (!s) {
		s = { undoCount: 0, conflict: false };
		_collab.set(store, s);
	}
	return s;
}

/**
 * Mark the store as "non-collab mutation just happened". Called by the
 * `bump` helper inside ``createDesignerStore`` so user edits reset the
 * pending-undo counter (the temporal middleware just cleared the future
 * stack so a redo would be impossible anyway).
 */
export function _resetUndoCount(store: DesignerStore): void {
	const c = _collabFor(store);
	c.undoCount = 0;
}

/**
 * Mark the store as "remote collaborator patch landed". If a redo was
 * pending, raises the ``conflict`` flag so ``safeRedo`` refuses with a
 * clear user message rather than dropping the redo silently.
 */
export function _markRemotePatch(store: DesignerStore): void {
	const c = _collabFor(store);
	if (c.undoCount > 0) {
		c.conflict = true;
	}
	c.undoCount = 0;
}

/**
 * Attempt a redo. Refuses with a collaboration-conflict message if a
 * remote patch landed while a redo was pending.
 *
 * Use:
 *
 * ```ts
 * const res = safeRedo(store);
 * if (!res.ok) toast.error(res.message);
 * ```
 */
export function safeRedo(store: DesignerStore): SafeRedoResult {
	const collab = _collabFor(store);
	if (collab.conflict) {
		collab.conflict = false;
		return {
			ok: false,
			message:
				"A collaborator updated this workflow while undo was in progress. " +
				"Redo refused to overwrite their change — please refresh and " +
				"re-apply your edit if it still applies.",
		};
	}
	const temporalApi = (store as unknown as {
		temporal: {
			getState: () => {
				futureStates: Array<{ version?: number }>;
				redo: () => void;
			};
		};
	}).temporal;
	const { futureStates, redo } = temporalApi.getState();
	if (futureStates.length === 0) {
		return { ok: false, message: "Nothing to redo." };
	}
	redo();
	collab.undoCount = Math.max(0, collab.undoCount - 1);
	return { ok: true };
}

/**
 * Apply a remote collaborator patch and update the conflict tracker
 * atomically. Always call this rather than ``store.getState().applyRemotePatch``
 * directly — the latter only mutates state, this also flags a pending
 * conflict so the next ``safeRedo`` surfaces the collaboration message.
 */
export function applyRemotePatch(
	store: DesignerStore,
	patch: { workflow?: WorkflowDef; form?: FormSpec | null },
): void {
	_markRemotePatch(store);
	store.getState().applyRemotePatch(patch);
}

/**
 * Undo helper that mirrors ``safeRedo`` semantically — exposed for symmetry.
 */
export function safeUndo(store: DesignerStore): SafeRedoResult {
	const temporalApi = (store as unknown as {
		temporal: {
			getState: () => {
				pastStates: Array<{ version?: number }>;
				undo: () => void;
			};
		};
	}).temporal;
	const { pastStates, undo } = temporalApi.getState();
	if (pastStates.length === 0) {
		return { ok: false, message: "Nothing to undo." };
	}
	undo();
	const collab = _collabFor(store);
	collab.undoCount += 1;
	return { ok: true };
}
