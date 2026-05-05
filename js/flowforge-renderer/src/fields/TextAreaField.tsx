import { useEffect, useRef } from "react";
import { FieldShell, type FieldComponentProps } from "./common.js";

export function TextAreaField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<textarea
				id={id}
				name={field.id}
				value={typeof value === "string" ? value : ""}
				placeholder={field.placeholder}
				disabled={disabled}
				readOnly={readOnly}
				aria-invalid={Boolean(error)}
				rows={4}
				onChange={(e) => onChange(e.target.value)}
				onBlur={onBlur}
				className="ff-textarea"
			/>
		</FieldShell>
	);
}

/**
 * RichTextField — minimal contenteditable wrapper. The renderer ships a safe
 * default that stores text content; hosts that need formatting can swap in
 * TipTap or similar via the `fieldComponents` prop on FormRenderer.
 */
export function RichTextField({ field, value, error, disabled, readOnly, onChange }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const ref = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		const node = ref.current;
		if (!node) return;
		const desired = typeof value === "string" ? value : "";
		if (node.textContent !== desired) {
			node.textContent = desired;
		}
	}, [value]);

	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<div
				id={id}
				ref={ref}
				role="textbox"
				aria-multiline="true"
				aria-invalid={Boolean(error)}
				aria-disabled={disabled || readOnly}
				contentEditable={!disabled && !readOnly}
				suppressContentEditableWarning
				className="ff-richtext"
				data-field-kind="rich_text"
				onInput={(e) => onChange((e.currentTarget as HTMLDivElement).textContent ?? "")}
			/>
		</FieldShell>
	);
}
