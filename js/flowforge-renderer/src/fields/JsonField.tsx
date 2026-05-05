import { useEffect, useState } from "react";
import { FieldShell, type FieldComponentProps } from "./common.js";

export function JsonField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const [text, setText] = useState<string>(() => {
		try {
			return value === undefined ? "" : JSON.stringify(value, null, 2);
		} catch {
			return "";
		}
	});
	const [parseError, setParseError] = useState<string | null>(null);

	useEffect(() => {
		try {
			const next = value === undefined ? "" : JSON.stringify(value, null, 2);
			setText(next);
		} catch {
			/* leave existing text */
		}
	}, [value]);

	const combinedError = error ?? parseError ?? undefined;

	return (
		<FieldShell field={field} error={combinedError} htmlFor={id}>
			<textarea
				id={id}
				name={field.id}
				value={text}
				placeholder={field.placeholder ?? "{}"}
				disabled={disabled}
				readOnly={readOnly}
				aria-invalid={Boolean(combinedError)}
				rows={6}
				spellCheck={false}
				onChange={(e) => {
					const raw = e.target.value;
					setText(raw);
					if (raw.trim() === "") {
						setParseError(null);
						onChange(null);
						return;
					}
					try {
						const parsed = JSON.parse(raw);
						setParseError(null);
						onChange(parsed);
					} catch (err) {
						setParseError(`Invalid JSON: ${(err as Error).message}`);
					}
				}}
				onBlur={onBlur}
				className="ff-textarea ff-textarea--mono"
			/>
		</FieldShell>
	);
}
