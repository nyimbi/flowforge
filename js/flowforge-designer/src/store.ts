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
			(set) => ({
				workflow: opts.workflow ?? emptyWorkflow(),
				form: opts.form ?? null,
				selection: { kind: "none" },

				setWorkflow: (wf) => set({ workflow: wf }),

				addState: (state) =>
					set((s) => ({
						workflow: {
							...s.workflow,
							states: [...s.workflow.states, state],
							initial_state:
								s.workflow.initial_state || state.kind === "start"
									? s.workflow.initial_state || state.id
									: s.workflow.initial_state,
						},
					})),

				updateState: (id, patch) =>
					set((s) => ({
						workflow: {
							...s.workflow,
							states: replaceById(s.workflow.states, id, patch),
						},
					})),

				removeState: (id) =>
					set((s) => ({
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

				addTransition: (t) =>
					set((s) => ({
						workflow: {
							...s.workflow,
							transitions: [...s.workflow.transitions, t],
						},
					})),

				updateTransition: (id, patch) =>
					set((s) => ({
						workflow: {
							...s.workflow,
							transitions: replaceById(s.workflow.transitions, id, patch),
						},
					})),

				removeTransition: (id) =>
					set((s) => ({
						workflow: {
							...s.workflow,
							transitions: s.workflow.transitions.filter((t) => t.id !== id),
						},
						selection:
							s.selection.kind === "transition" && s.selection.id === id
								? { kind: "none" }
								: s.selection,
					})),

				setForm: (spec) => set({ form: spec }),

				addField: (field) =>
					set((s) =>
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

				updateField: (id, patch) =>
					set((s) =>
						s.form
							? {
									form: {
										...s.form,
										fields: replaceById(s.form.fields, id, patch),
									},
								}
							: {},
					),

				removeField: (id) =>
					set((s) =>
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

				moveField: (id, toIndex) =>
					set((s) => {
						if (!s.form) return {};
						const fields = [...s.form.fields];
						const fromIndex = fields.findIndex((f) => f.id === id);
						if (fromIndex === -1) return {};
						const clamped = Math.max(0, Math.min(toIndex, fields.length - 1));
						const [item] = fields.splice(fromIndex, 1);
						fields.splice(clamped, 0, item);
						return { form: { ...s.form, fields } };
					}),

				select: (selection) => set({ selection }),
			}),
			{
				// Track only the working DSL, not selection cursor — selection moves
				// should not consume undo slots.
				partialize: (state) => ({
					workflow: state.workflow,
					form: state.form,
				}),
				limit: 100,
			},
		),
	);

export type DesignerStore = ReturnType<typeof createDesignerStore>;
