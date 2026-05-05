import { FieldShell, type FieldComponentProps } from "./common.js";

export function EnumField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const options = field.options ?? [];
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<select
				id={id}
				name={field.id}
				value={typeof value === "string" ? value : ""}
				disabled={disabled || readOnly}
				aria-invalid={Boolean(error)}
				onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
				onBlur={onBlur}
				className="ff-select"
			>
				<option value="">{field.placeholder ?? "— Select —"}</option>
				{options.map((opt) => (
					<option key={opt.v} value={opt.v}>
						{opt.label ?? opt.v}
					</option>
				))}
			</select>
		</FieldShell>
	);
}

export function MultiSelectField({ field, value, error, disabled, readOnly, onChange }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const options = field.options ?? [];
	const selected: string[] = Array.isArray(value) ? (value.filter((v) => typeof v === "string") as string[]) : [];

	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<div id={id} role="group" aria-invalid={Boolean(error)} className="ff-multi-select">
				{options.map((opt) => {
					const checked = selected.includes(opt.v);
					return (
						<label key={opt.v} className="ff-multi-select__opt">
							<input
								type="checkbox"
								name={`${field.id}[]`}
								value={opt.v}
								checked={checked}
								disabled={disabled || readOnly}
								onChange={(e) => {
									const next = new Set(selected);
									if (e.target.checked) next.add(opt.v);
									else next.delete(opt.v);
									onChange(Array.from(next));
								}}
							/>
							<span>{opt.label ?? opt.v}</span>
						</label>
					);
				})}
			</div>
		</FieldShell>
	);
}
