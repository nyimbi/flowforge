import { useMemo, useState, type JSX } from "react";

import type { DesignerStore } from "./store.js";
import type {
	ConditionalRule,
	FieldDef,
	FieldKind,
	FieldOption,
} from "./types.js";

const FIELD_PALETTE: { kind: FieldKind; label: string }[] = [
	{ kind: "text", label: "Text" },
	{ kind: "textarea", label: "Textarea" },
	{ kind: "number", label: "Number" },
	{ kind: "money", label: "Money" },
	{ kind: "boolean", label: "Boolean" },
	{ kind: "date", label: "Date" },
	{ kind: "enum", label: "Enum" },
	{ kind: "lookup", label: "Lookup" },
	{ kind: "file", label: "File" },
	{ kind: "email", label: "Email" },
];

const RULE_OPS: ConditionalRule["op"][] = [
	"eq",
	"neq",
	"gt",
	"lt",
	"in",
	"not_in",
	"is_null",
	"not_null",
];

const RULE_ACTIONS: ConditionalRule["action"][] = [
	"show",
	"hide",
	"require",
	"optional",
];

const renderPreview = (field: FieldDef): JSX.Element => {
	switch (field.kind) {
		case "textarea":
			return <textarea aria-label={field.label} placeholder={field.placeholder} />;
		case "boolean":
			return <input type="checkbox" aria-label={field.label} />;
		case "date":
			return <input type="date" aria-label={field.label} />;
		case "number":
		case "money":
			return <input type="number" aria-label={field.label} />;
		case "email":
			return <input type="email" aria-label={field.label} />;
		case "enum":
			return (
				<select aria-label={field.label}>
					{(field.options ?? []).map((o) => (
						<option key={o.value} value={o.value}>
							{o.label}
						</option>
					))}
				</select>
			);
		case "file":
			return <input type="file" aria-label={field.label} />;
		case "lookup":
			return <input type="search" aria-label={field.label} placeholder="Search…" />;
		default:
			return <input type="text" aria-label={field.label} placeholder={field.placeholder} />;
	}
};

interface OptionEditorProps {
	options: FieldOption[];
	onChange: (options: FieldOption[]) => void;
}

const OptionEditor = ({ options, onChange }: OptionEditorProps): JSX.Element => (
	<fieldset>
		<legend>Options</legend>
		{options.map((opt, idx) => (
			<div key={`${opt.value}-${idx}`}>
				<input
					aria-label={`option value ${idx}`}
					value={opt.value}
					onChange={(e) => {
						const next = [...options];
						next[idx] = { ...opt, value: e.target.value };
						onChange(next);
					}}
				/>
				<input
					aria-label={`option label ${idx}`}
					value={opt.label}
					onChange={(e) => {
						const next = [...options];
						next[idx] = { ...opt, label: e.target.value };
						onChange(next);
					}}
				/>
				<button
					type="button"
					aria-label={`remove option ${idx}`}
					onClick={() => onChange(options.filter((_, i) => i !== idx))}
				>
					x
				</button>
			</div>
		))}
		<button
			type="button"
			data-testid="option-add"
			onClick={() => onChange([...options, { value: "", label: "" }])}
		>
			Add option
		</button>
	</fieldset>
);

interface RulesEditorProps {
	rules: ConditionalRule[];
	siblingFieldIds: string[];
	onChange: (rules: ConditionalRule[]) => void;
}

const RulesEditor = ({
	rules,
	siblingFieldIds,
	onChange,
}: RulesEditorProps): JSX.Element => (
	<fieldset data-testid="rules-editor">
		<legend>Conditional rules</legend>
		{rules.map((rule, idx) => (
			<div key={idx} data-testid={`rule-row-${idx}`}>
				<select
					aria-label={`rule when_field ${idx}`}
					value={rule.when_field}
					onChange={(e) => {
						const next = [...rules];
						next[idx] = { ...rule, when_field: e.target.value };
						onChange(next);
					}}
				>
					<option value="">(field)</option>
					{siblingFieldIds.map((id) => (
						<option key={id} value={id}>
							{id}
						</option>
					))}
				</select>
				<select
					aria-label={`rule op ${idx}`}
					value={rule.op}
					onChange={(e) => {
						const next = [...rules];
						next[idx] = { ...rule, op: e.target.value as ConditionalRule["op"] };
						onChange(next);
					}}
				>
					{RULE_OPS.map((op) => (
						<option key={op} value={op}>
							{op}
						</option>
					))}
				</select>
				<input
					aria-label={`rule value ${idx}`}
					value={rule.value === undefined ? "" : String(rule.value)}
					onChange={(e) => {
						const next = [...rules];
						next[idx] = { ...rule, value: e.target.value };
						onChange(next);
					}}
				/>
				<select
					aria-label={`rule action ${idx}`}
					value={rule.action}
					onChange={(e) => {
						const next = [...rules];
						next[idx] = {
							...rule,
							action: e.target.value as ConditionalRule["action"],
						};
						onChange(next);
					}}
				>
					{RULE_ACTIONS.map((a) => (
						<option key={a} value={a}>
							{a}
						</option>
					))}
				</select>
				<button
					type="button"
					aria-label={`remove rule ${idx}`}
					onClick={() => onChange(rules.filter((_, i) => i !== idx))}
				>
					x
				</button>
			</div>
		))}
		<button
			type="button"
			data-testid="rule-add"
			onClick={() =>
				onChange([
					...rules,
					{ when_field: siblingFieldIds[0] ?? "", op: "eq", value: "", action: "show" },
				])
			}
		>
			Add rule
		</button>
	</fieldset>
);

export interface FormBuilderProps {
	store: DesignerStore;
}

export const FormBuilder = ({ store }: FormBuilderProps): JSX.Element => {
	const form = store((s) => s.form);
	const addField = store((s) => s.addField);
	const updateField = store((s) => s.updateField);
	const removeField = store((s) => s.removeField);
	const moveField = store((s) => s.moveField);
	const select = store((s) => s.select);
	const selection = store((s) => s.selection);

	const [draggingId, setDraggingId] = useState<string | null>(null);

	const fields = form?.fields ?? [];
	const selectedField = useMemo(
		() => (selection.kind === "field" ? fields.find((f) => f.id === selection.id) : undefined),
		[selection, fields],
	);

	const handlePaletteAdd = (kind: FieldKind): void => {
		const id = `field_${fields.length + 1}`;
		addField({
			id,
			label: `New ${kind}`,
			kind,
			required: false,
			...(kind === "enum" ? { options: [] } : {}),
		});
		select({ kind: "field", id });
	};

	const handleDragStart = (id: string): void => setDraggingId(id);
	const handleDragOver = (e: React.DragEvent): void => {
		e.preventDefault();
	};
	const handleDrop = (targetId: string): void => {
		if (!draggingId || draggingId === targetId) {
			setDraggingId(null);
			return;
		}
		const targetIndex = fields.findIndex((f) => f.id === targetId);
		if (targetIndex === -1) {
			setDraggingId(null);
			return;
		}
		moveField(draggingId, targetIndex);
		setDraggingId(null);
	};

	return (
		<section data-testid="form-builder" aria-label="Form builder">
			<div data-testid="field-palette" aria-label="Field palette">
				<h4>Field palette</h4>
				{FIELD_PALETTE.map((item) => (
					<button
						type="button"
						key={item.kind}
						data-testid={`palette-${item.kind}`}
						onClick={() => handlePaletteAdd(item.kind)}
					>
						+ {item.label}
					</button>
				))}
			</div>

			<div data-testid="form-canvas" aria-label="Form canvas">
				<h4>Form: {form?.name ?? "(none)"}</h4>
				{fields.length === 0 ? (
					<p data-testid="form-empty">Drop fields here.</p>
				) : null}
				<ol>
					{fields.map((f) => (
						<li
							key={f.id}
							data-testid={`form-field-${f.id}`}
							draggable
							onDragStart={() => handleDragStart(f.id)}
							onDragOver={handleDragOver}
							onDrop={() => handleDrop(f.id)}
							onClick={() => select({ kind: "field", id: f.id })}
						>
							<strong>{f.label}</strong> <em>({f.kind})</em>
							{f.required ? " *" : null}
							<button
								type="button"
								aria-label={`remove field ${f.id}`}
								onClick={(e) => {
									e.stopPropagation();
									removeField(f.id);
								}}
							>
								x
							</button>
						</li>
					))}
				</ol>
			</div>

			<div data-testid="form-preview" aria-label="Form preview">
				<h4>Preview</h4>
				{fields.map((f) => (
					<div key={f.id} data-testid={`preview-${f.id}`}>
						<label>
							{f.label}
							{f.required ? " *" : null}
						</label>
						{renderPreview(f)}
						{f.help ? <small>{f.help}</small> : null}
					</div>
				))}
			</div>

			{selectedField ? (
				<div data-testid="form-property-panel" aria-label="Field property panel">
					<h4>Field properties</h4>
					<label>
						<span>Id</span>
						<input
							data-testid="form-field-id"
							value={selectedField.id}
							onChange={(e) => updateField(selectedField.id, { id: e.target.value })}
						/>
					</label>
					<label>
						<span>Label</span>
						<input
							data-testid="form-field-label"
							value={selectedField.label}
							onChange={(e) =>
								updateField(selectedField.id, { label: e.target.value })
							}
						/>
					</label>
					<label>
						<span>Kind</span>
						<select
							data-testid="form-field-kind"
							value={selectedField.kind}
							onChange={(e) =>
								updateField(selectedField.id, { kind: e.target.value as FieldKind })
							}
						>
							{FIELD_PALETTE.map((p) => (
								<option key={p.kind} value={p.kind}>
									{p.label}
								</option>
							))}
						</select>
					</label>
					<label>
						<input
							type="checkbox"
							data-testid="form-field-required"
							checked={selectedField.required ?? false}
							onChange={(e) =>
								updateField(selectedField.id, { required: e.target.checked })
							}
						/>
						Required
					</label>
					<label>
						<input
							type="checkbox"
							data-testid="form-field-pii"
							checked={selectedField.pii ?? false}
							onChange={(e) =>
								updateField(selectedField.id, { pii: e.target.checked })
							}
						/>
						Contains PII
					</label>
					<label>
						<span>Help</span>
						<input
							data-testid="form-field-help"
							value={selectedField.help ?? ""}
							onChange={(e) =>
								updateField(selectedField.id, { help: e.target.value })
							}
						/>
					</label>
					{selectedField.kind === "enum" ? (
						<OptionEditor
							options={selectedField.options ?? []}
							onChange={(options) =>
								updateField(selectedField.id, { options })
							}
						/>
					) : null}
					<RulesEditor
						rules={selectedField.rules ?? []}
						siblingFieldIds={fields
							.filter((f) => f.id !== selectedField.id)
							.map((f) => f.id)}
						onChange={(rules) => updateField(selectedField.id, { rules })}
					/>
				</div>
			) : null}
		</section>
	);
};
