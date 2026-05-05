import { FieldShell, type FieldComponentProps } from "./common.js";

export function BooleanField({ field, value, error, disabled, readOnly, onChange }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<input
				id={id}
				name={field.id}
				type="checkbox"
				checked={value === true}
				disabled={disabled || readOnly}
				aria-invalid={Boolean(error)}
				onChange={(e) => onChange(e.target.checked)}
				className="ff-checkbox"
			/>
		</FieldShell>
	);
}
