import { FieldShell, type FieldComponentProps } from "./common.js";

export function DateField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<input
				id={id}
				name={field.id}
				type="date"
				value={typeof value === "string" ? value : ""}
				disabled={disabled}
				readOnly={readOnly}
				aria-invalid={Boolean(error)}
				onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
				onBlur={onBlur}
				className="ff-input"
			/>
		</FieldShell>
	);
}

export function DateTimeField(props: FieldComponentProps) {
	const id = `ff-${props.field.id}`;
	return (
		<FieldShell field={props.field} error={props.error} htmlFor={id}>
			<input
				id={id}
				name={props.field.id}
				type="datetime-local"
				value={typeof props.value === "string" ? props.value : ""}
				disabled={props.disabled}
				readOnly={props.readOnly}
				aria-invalid={Boolean(props.error)}
				onChange={(e) => props.onChange(e.target.value === "" ? null : e.target.value)}
				onBlur={props.onBlur}
				className="ff-input"
			/>
		</FieldShell>
	);
}
