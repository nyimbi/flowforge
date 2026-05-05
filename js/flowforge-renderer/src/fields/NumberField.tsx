import { FieldShell, type FieldComponentProps } from "./common.js";

function asNumber(v: unknown): string {
	if (typeof v === "number" && Number.isFinite(v)) return String(v);
	if (typeof v === "string") return v;
	return "";
}

export function NumberField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<input
				id={id}
				name={field.id}
				type="number"
				value={asNumber(value)}
				placeholder={field.placeholder}
				disabled={disabled}
				readOnly={readOnly}
				aria-invalid={Boolean(error)}
				onChange={(e) => {
					const raw = e.target.value;
					if (raw === "") onChange(null);
					else {
						const n = Number(raw);
						onChange(Number.isNaN(n) ? raw : n);
					}
				}}
				onBlur={onBlur}
				className="ff-input ff-input--number"
			/>
		</FieldShell>
	);
}

export function PercentageField(props: FieldComponentProps) {
	const id = `ff-${props.field.id}`;
	return (
		<FieldShell field={props.field} error={props.error} htmlFor={id}>
			<div className="ff-input-group">
				<input
					id={id}
					name={props.field.id}
					type="number"
					min={0}
					max={100}
					step="0.01"
					value={asNumber(props.value)}
					disabled={props.disabled}
					readOnly={props.readOnly}
					aria-invalid={Boolean(props.error)}
					onChange={(e) => {
						const raw = e.target.value;
						if (raw === "") props.onChange(null);
						else {
							const n = Number(raw);
							props.onChange(Number.isNaN(n) ? raw : n);
						}
					}}
					onBlur={props.onBlur}
					className="ff-input ff-input--percentage"
				/>
				<span className="ff-input-suffix" aria-hidden="true">
					%
				</span>
			</div>
		</FieldShell>
	);
}
