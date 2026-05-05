import { FieldShell, type FieldComponentProps } from "./common.js";

export function TextField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<input
				id={id}
				name={field.id}
				type="text"
				value={typeof value === "string" ? value : ""}
				placeholder={field.placeholder}
				disabled={disabled}
				readOnly={readOnly}
				aria-invalid={Boolean(error)}
				onChange={(e) => onChange(e.target.value)}
				onBlur={onBlur}
				className="ff-input"
			/>
		</FieldShell>
	);
}

export function EmailField(props: FieldComponentProps) {
	const id = `ff-${props.field.id}`;
	return (
		<FieldShell field={props.field} error={props.error} htmlFor={id}>
			<input
				id={id}
				name={props.field.id}
				type="email"
				value={typeof props.value === "string" ? props.value : ""}
				placeholder={props.field.placeholder}
				disabled={props.disabled}
				readOnly={props.readOnly}
				aria-invalid={Boolean(props.error)}
				onChange={(e) => props.onChange(e.target.value)}
				onBlur={props.onBlur}
				className="ff-input"
			/>
		</FieldShell>
	);
}

export function UrlField(props: FieldComponentProps) {
	const id = `ff-${props.field.id}`;
	return (
		<FieldShell field={props.field} error={props.error} htmlFor={id}>
			<input
				id={id}
				name={props.field.id}
				type="url"
				value={typeof props.value === "string" ? props.value : ""}
				placeholder={props.field.placeholder}
				disabled={props.disabled}
				readOnly={props.readOnly}
				aria-invalid={Boolean(props.error)}
				onChange={(e) => props.onChange(e.target.value)}
				onBlur={props.onBlur}
				className="ff-input"
			/>
		</FieldShell>
	);
}

export function PhoneField(props: FieldComponentProps) {
	const id = `ff-${props.field.id}`;
	return (
		<FieldShell field={props.field} error={props.error} htmlFor={id}>
			<input
				id={id}
				name={props.field.id}
				type="tel"
				value={typeof props.value === "string" ? props.value : ""}
				placeholder={props.field.placeholder ?? "+1 555 1234567"}
				disabled={props.disabled}
				readOnly={props.readOnly}
				aria-invalid={Boolean(props.error)}
				onChange={(e) => props.onChange(e.target.value)}
				onBlur={props.onBlur}
				className="ff-input"
			/>
		</FieldShell>
	);
}

export function ColorField(props: FieldComponentProps) {
	const id = `ff-${props.field.id}`;
	return (
		<FieldShell field={props.field} error={props.error} htmlFor={id}>
			<input
				id={id}
				name={props.field.id}
				type="color"
				value={typeof props.value === "string" ? props.value : "#000000"}
				disabled={props.disabled}
				readOnly={props.readOnly}
				aria-invalid={Boolean(props.error)}
				onChange={(e) => props.onChange(e.target.value)}
				onBlur={props.onBlur}
				className="ff-input ff-input--color"
			/>
		</FieldShell>
	);
}

export function HiddenField({ field, value, onChange }: FieldComponentProps) {
	return (
		<input
			type="hidden"
			name={field.id}
			value={typeof value === "string" ? value : ""}
			onChange={(e) => onChange(e.target.value)}
			data-flowforge-field={field.id}
			data-field-kind="hidden"
		/>
	);
}
