import { FieldShell, type FieldComponentProps } from "./common.js";

/**
 * Lightweight signature field: a typed-name attestation. Hosts can swap in a
 * canvas-based capture via `fieldComponents` override; this default fits SaaS
 * forms without a canvas dependency.
 */
export function SignatureField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<input
				id={id}
				name={field.id}
				type="text"
				value={typeof value === "string" ? value : ""}
				placeholder={field.placeholder ?? "Type full name to sign"}
				disabled={disabled}
				readOnly={readOnly}
				aria-invalid={Boolean(error)}
				autoComplete="off"
				onChange={(e) => onChange(e.target.value)}
				onBlur={onBlur}
				className="ff-input ff-input--signature"
				data-field-kind="signature"
			/>
		</FieldShell>
	);
}
