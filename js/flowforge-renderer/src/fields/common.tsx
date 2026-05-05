/**
 * Shared props every field component receives + the FieldShell wrapper that
 * renders label, error, help text, and the PII badge.
 */

import type { ReactNode } from "react";
import type { FormField } from "../types.js";

export interface FieldComponentProps {
	field: FormField;
	value: unknown;
	error?: string;
	disabled?: boolean;
	readOnly?: boolean;
	onChange: (next: unknown) => void;
	onBlur?: () => void;
	/** Async lookup callback exposed by FormRenderer for fields that need it. */
	lookup?: (query?: string) => Promise<{ v: string; label?: string }[]>;
}

export interface FieldShellProps {
	field: FormField;
	error?: string;
	htmlFor: string;
	children: ReactNode;
}

export function FieldShell({ field, error, htmlFor, children }: FieldShellProps) {
	return (
		<div
			data-flowforge-field={field.id}
			data-field-kind={field.kind}
			data-field-error={error ? "true" : "false"}
			className="ff-field"
		>
			{field.label !== undefined && (
				<>
					<label htmlFor={htmlFor} className="ff-field__label">
						{field.label}
					</label>
					{field.required ? (
						<span className="ff-field__required" aria-hidden="true">
							{" *"}
						</span>
					) : null}
					{field.pii ? (
						<span className="ff-field__pii" aria-label="contains personal data">
							PII
						</span>
					) : null}
				</>
			)}
			{children}
			{field.help ? <p className="ff-field__help">{field.help}</p> : null}
			{error ? (
				<p className="ff-field__error" role="alert">
					{error}
				</p>
			) : null}
		</div>
	);
}

export function inputId(formId: string, fieldId: string): string {
	return `ff-${formId}-${fieldId}`;
}
