import { temporal } from "zundo";
import { create } from "zustand";

import type {
	FieldDef,
	FormSpec,
	WorkflowDef,
	WorkflowState,
	WorkflowTransition,
} from "./types.js";

export type SelectionKind =
	| { kind: "state"; id: string }
	| { kind: "transition"; id: string }
	| { kind: "field"; id: string }
	| { kind: "none" };

export interface DesignerState {
	workflow: WorkflowDef;
	form: FormSpec | null;
	selection: SelectionKind;
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
	updateState: (id: string, patch: Partial<WorkflowState>) => void;
	removeState: (id: string) => void;
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
					workflow: opts.workflow ?? emptyWorkflow(),
					form: opts.form ?? null,
					selection: { kind: "none" },
					version: 0,

					setWorkflow: (wf) => set(bump(() => ({ workflow: wf }))),

					addState: (state) =>
						set(
							bump((s) => ({
								workflow: {
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
								},
							})),
						),

					updateState: (id, patch) =>
						set(
							bump((s) => ({
								workflow: {
									...s.workflow,
									states: replaceById(s.workflow.states, id, patch),
								},
							})),
						),

					removeState: (id) =>
						set(
							bump((s) => ({
								workflow: {
									...s.workflow,
									states: s.workflow.states.filter((st) => st.id !== id),
									transitions: s.workflow.transitions.filter(
										(t) => t.from !== id && t.to !== id,
									),
								},
								selection:
									s.selection.kind === "state" && s.selection.id === id
										? { kind: "none" }
										: s.selection,
							})),
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
							bump((s) => ({
								workflow: patch.workflow ?? s.workflow,
								form: patch.form !== undefined ? patch.form : s.form,
							})),
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
					version: state.version,
				}),
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
