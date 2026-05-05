import { FieldShell, type FieldComponentProps } from "./common.js";

export function FileField({ field, value, error, disabled, readOnly, onChange }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const v = (field.validation ?? {}) as { accept?: string[]; max_size_bytes?: number };
	const accept = Array.isArray(v.accept) && v.accept.length > 0 ? v.accept.join(",") : undefined;
	const current =
		value && typeof value === "object" && "name" in value ? (value as { name?: string }).name : undefined;

	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<input
				id={id}
				name={field.id}
				type="file"
				accept={accept}
				disabled={disabled || readOnly}
				aria-invalid={Boolean(error)}
				onChange={(e) => {
					const file = e.target.files?.[0];
					if (!file) {
						onChange(null);
						return;
					}
					if (typeof v.max_size_bytes === "number" && file.size > v.max_size_bytes) {
						onChange({ error: "file_too_large", name: file.name, size: file.size });
						return;
					}
					onChange({
						name: file.name,
						size: file.size,
						type: file.type,
						lastModified: file.lastModified,
					});
				}}
				className="ff-file"
			/>
			{current ? (
				<p className="ff-file__current" data-current-name>
					{current}
				</p>
			) : null}
		</FieldShell>
	);
}
