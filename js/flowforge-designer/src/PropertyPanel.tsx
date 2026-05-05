import { useMemo, useState, type JSX } from "react";

import type { DesignerStore } from "./store.js";
import type {
	ChecklistItem,
	DelegationPolicy,
	EscalationPolicy,
	WorkflowState,
	WorkflowStateKind,
	WorkflowTransition,
} from "./types.js";

const STATE_KINDS: WorkflowStateKind[] = [
	"start",
	"task",
	"review",
	"decision",
	"wait",
	"end",
];

interface StateEditorProps {
	state: WorkflowState;
	onChange: (patch: Partial<WorkflowState>) => void;
}

const StateEditor = ({ state, onChange }: StateEditorProps): JSX.Element => {
	const [draftName, setDraftName] = useState(state.name);

	return (
		<div data-testid="state-editor">
			<label>
				<span>Name</span>
				<input
					data-testid="state-name-input"
					value={draftName}
					onChange={(e) => setDraftName(e.target.value)}
					onBlur={() => onChange({ name: draftName })}
				/>
			</label>
			<button
				type="button"
				data-testid="state-name-commit"
				onClick={() => onChange({ name: draftName })}
			>
				Commit name
			</button>
			<label>
				<span>Kind</span>
				<select
					data-testid="state-kind-select"
					value={state.kind}
					onChange={(e) =>
						onChange({ kind: e.target.value as WorkflowStateKind })
					}
				>
					{STATE_KINDS.map((k) => (
						<option key={k} value={k}>
							{k}
						</option>
					))}
				</select>
			</label>
			<label>
				<span>Description</span>
				<textarea
					data-testid="state-description"
					value={state.description ?? ""}
					onChange={(e) => onChange({ description: e.target.value })}
				/>
			</label>
			<label>
				<span>Assignee role</span>
				<input
					data-testid="state-assignee"
					value={state.assignee_role ?? ""}
					onChange={(e) => onChange({ assignee_role: e.target.value })}
				/>
			</label>
			<label>
				<span>Form id</span>
				<input
					data-testid="state-form-id"
					value={state.form_id ?? ""}
					onChange={(e) => onChange({ form_id: e.target.value })}
				/>
			</label>
			<ChecklistEditor
				items={state.checklist ?? []}
				onChange={(checklist) => onChange({ checklist })}
			/>
			<DocumentEditor
				docs={state.required_documents ?? []}
				onChange={(required_documents) => onChange({ required_documents })}
			/>
			<EscalationEditor
				policy={state.escalation}
				onChange={(escalation) => onChange({ escalation })}
			/>
			<DelegationEditor
				policy={state.delegation}
				onChange={(delegation) => onChange({ delegation })}
			/>
		</div>
	);
};

interface ChecklistEditorProps {
	items: ChecklistItem[];
	onChange: (items: ChecklistItem[]) => void;
}

const ChecklistEditor = ({ items, onChange }: ChecklistEditorProps): JSX.Element => {
	return (
		<fieldset data-testid="checklist-editor">
			<legend>Checklist</legend>
			{items.map((item, idx) => (
				<div key={item.id} data-testid={`checklist-row-${item.id}`}>
					<input
						aria-label={`checklist label ${idx}`}
						value={item.label}
						onChange={(e) => {
							const next = [...items];
							next[idx] = { ...item, label: e.target.value };
							onChange(next);
						}}
					/>
					<label>
						<input
							type="checkbox"
							checked={item.required}
							aria-label={`checklist required ${idx}`}
							onChange={(e) => {
								const next = [...items];
								next[idx] = { ...item, required: e.target.checked };
								onChange(next);
							}}
						/>
						required
					</label>
					<button
						type="button"
						aria-label={`remove checklist ${idx}`}
						onClick={() => onChange(items.filter((_, i) => i !== idx))}
					>
						x
					</button>
				</div>
			))}
			<button
				type="button"
				data-testid="checklist-add"
				onClick={() =>
					onChange([
						...items,
						{ id: `chk-${items.length + 1}`, label: "New item", required: false },
					])
				}
			>
				Add checklist item
			</button>
		</fieldset>
	);
};

interface DocumentEditorProps {
	docs: string[];
	onChange: (docs: string[]) => void;
}

const DocumentEditor = ({ docs, onChange }: DocumentEditorProps): JSX.Element => (
	<fieldset data-testid="document-editor">
		<legend>Required documents</legend>
		{docs.map((d, idx) => (
			<div key={`${d}-${idx}`}>
				<input
					aria-label={`required document ${idx}`}
					value={d}
					onChange={(e) => {
						const next = [...docs];
						next[idx] = e.target.value;
						onChange(next);
					}}
				/>
				<button
					type="button"
					aria-label={`remove document ${idx}`}
					onClick={() => onChange(docs.filter((_, i) => i !== idx))}
				>
					x
				</button>
			</div>
		))}
		<button
			type="button"
			data-testid="document-add"
			onClick={() => onChange([...docs, ""])}
		>
			Add document
		</button>
	</fieldset>
);

interface EscalationEditorProps {
	policy?: EscalationPolicy;
	onChange: (policy: EscalationPolicy | undefined) => void;
}

const EscalationEditor = ({ policy, onChange }: EscalationEditorProps): JSX.Element => {
	const enabled = policy !== undefined;
	return (
		<fieldset data-testid="escalation-editor">
			<legend>Escalation</legend>
			<label>
				<input
					type="checkbox"
					checked={enabled}
					data-testid="escalation-enabled"
					onChange={(e) =>
						onChange(e.target.checked ? { after: "PT24H", to: "" } : undefined)
					}
				/>
				Enable escalation
			</label>
			{policy ? (
				<>
					<label>
						<span>After (ISO 8601 duration)</span>
						<input
							data-testid="escalation-after"
							value={policy.after}
							onChange={(e) => onChange({ ...policy, after: e.target.value })}
						/>
					</label>
					<label>
						<span>Escalate to</span>
						<input
							data-testid="escalation-to"
							value={policy.to}
							onChange={(e) => onChange({ ...policy, to: e.target.value })}
						/>
					</label>
				</>
			) : null}
		</fieldset>
	);
};

interface DelegationEditorProps {
	policy?: DelegationPolicy;
	onChange: (policy: DelegationPolicy | undefined) => void;
}

const DelegationEditor = ({ policy, onChange }: DelegationEditorProps): JSX.Element => {
	const enabled = policy !== undefined;
	const rolesText = policy?.allowed_roles.join(",") ?? "";
	return (
		<fieldset data-testid="delegation-editor">
			<legend>Delegation</legend>
			<label>
				<input
					type="checkbox"
					checked={enabled}
					data-testid="delegation-enabled"
					onChange={(e) =>
						onChange(e.target.checked ? { allowed_roles: [] } : undefined)
					}
				/>
				Allow delegation
			</label>
			{policy ? (
				<>
					<label>
						<span>Allowed roles (comma-separated)</span>
						<input
							data-testid="delegation-roles"
							value={rolesText}
							onChange={(e) =>
								onChange({
									...policy,
									allowed_roles: e.target.value
										.split(",")
										.map((s) => s.trim())
										.filter(Boolean),
								})
							}
						/>
					</label>
					<label>
						<input
							type="checkbox"
							checked={policy.require_reason ?? false}
							data-testid="delegation-require-reason"
							onChange={(e) =>
								onChange({ ...policy, require_reason: e.target.checked })
							}
						/>
						Require reason
					</label>
				</>
			) : null}
		</fieldset>
	);
};

interface TransitionEditorProps {
	transition: WorkflowTransition;
	onChange: (patch: Partial<WorkflowTransition>) => void;
	stateIds: string[];
}

const TransitionEditor = ({
	transition,
	onChange,
	stateIds,
}: TransitionEditorProps): JSX.Element => {
	return (
		<div data-testid="transition-editor">
			<label>
				<span>Event</span>
				<input
					data-testid="transition-event"
					value={transition.event}
					onChange={(e) => onChange({ event: e.target.value })}
				/>
			</label>
			<label>
				<span>From</span>
				<select
					data-testid="transition-from"
					value={transition.from}
					onChange={(e) => onChange({ from: e.target.value })}
				>
					{stateIds.map((id) => (
						<option key={id} value={id}>
							{id}
						</option>
					))}
				</select>
			</label>
			<label>
				<span>To</span>
				<select
					data-testid="transition-to"
					value={transition.to}
					onChange={(e) => onChange({ to: e.target.value })}
				>
					{stateIds.map((id) => (
						<option key={id} value={id}>
							{id}
						</option>
					))}
				</select>
			</label>
			<label>
				<span>Required role</span>
				<input
					data-testid="transition-role"
					value={transition.required_role ?? ""}
					onChange={(e) => onChange({ required_role: e.target.value })}
				/>
			</label>
			<label>
				<span>Guard expression</span>
				<input
					data-testid="transition-guard"
					value={transition.guard?.expr ?? ""}
					onChange={(e) =>
						onChange({
							guard: e.target.value
								? { expr: e.target.value, description: transition.guard?.description }
								: undefined,
						})
					}
				/>
			</label>
		</div>
	);
};

export interface PropertyPanelProps {
	store: DesignerStore;
}

export const PropertyPanel = ({ store }: PropertyPanelProps): JSX.Element => {
	const selection = store((s) => s.selection);
	const workflow = store((s) => s.workflow);
	const form = store((s) => s.form);
	const updateState = store((s) => s.updateState);
	const updateTransition = store((s) => s.updateTransition);
	const updateField = store((s) => s.updateField);

	const stateIds = useMemo(() => workflow.states.map((s) => s.id), [workflow.states]);

	if (selection.kind === "none") {
		return (
			<aside data-testid="property-panel" aria-label="Property panel">
				<p>Select a state, transition, or field to edit its properties.</p>
			</aside>
		);
	}

	if (selection.kind === "state") {
		const state = workflow.states.find((s) => s.id === selection.id);
		if (!state) {
			return (
				<aside data-testid="property-panel">
					<p>State not found.</p>
				</aside>
			);
		}
		return (
			<aside data-testid="property-panel" aria-label="State properties">
				<h3>State: {state.id}</h3>
				<StateEditor
					state={state}
					onChange={(patch) => updateState(state.id, patch)}
				/>
			</aside>
		);
	}

	if (selection.kind === "transition") {
		const t = workflow.transitions.find((x) => x.id === selection.id);
		if (!t) {
			return (
				<aside data-testid="property-panel">
					<p>Transition not found.</p>
				</aside>
			);
		}
		return (
			<aside data-testid="property-panel" aria-label="Transition properties">
				<h3>Transition: {t.id}</h3>
				<TransitionEditor
					transition={t}
					onChange={(patch) => updateTransition(t.id, patch)}
					stateIds={stateIds}
				/>
			</aside>
		);
	}

	// field
	const field = form?.fields.find((f) => f.id === selection.id);
	if (!field) {
		return (
			<aside data-testid="property-panel">
				<p>Field not found.</p>
			</aside>
		);
	}

	return (
		<aside data-testid="property-panel" aria-label="Field properties">
			<h3>Field: {field.id}</h3>
			<label>
				<span>Label</span>
				<input
					data-testid="field-label"
					value={field.label}
					onChange={(e) => updateField(field.id, { label: e.target.value })}
				/>
			</label>
			<label>
				<span>Required</span>
				<input
					type="checkbox"
					data-testid="field-required"
					checked={field.required ?? false}
					onChange={(e) => updateField(field.id, { required: e.target.checked })}
				/>
			</label>
			<label>
				<span>Help</span>
				<input
					data-testid="field-help"
					value={field.help ?? ""}
					onChange={(e) => updateField(field.id, { help: e.target.value })}
				/>
			</label>
		</aside>
	);
};
