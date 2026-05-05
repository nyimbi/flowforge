import { FieldShell, type FieldComponentProps } from "./common.js";

export function MoneyField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const v = (field.validation ?? {}) as { currency?: string };
	const currency = v.currency ?? "USD";

	let displayValue = "";
	if (typeof value === "number") displayValue = String(value);
	else if (typeof value === "string") displayValue = value;
	else if (value && typeof value === "object" && "amount" in value) {
		const amount = (value as { amount?: unknown }).amount;
		if (typeof amount === "number") displayValue = String(amount);
		else if (typeof amount === "string") displayValue = amount;
	}

	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<div className="ff-input-group">
				<span className="ff-input-prefix" aria-hidden="true">
					{currency}
				</span>
				<input
					id={id}
					name={field.id}
					type="number"
					step="0.01"
					value={displayValue}
					placeholder={field.placeholder ?? "0.00"}
					disabled={disabled}
					readOnly={readOnly}
					aria-invalid={Boolean(error)}
					onChange={(e) => {
						const raw = e.target.value;
						if (raw === "") onChange(null);
						else {
							const n = Number(raw);
							onChange(Number.isNaN(n) ? raw : { amount: n, currency });
						}
					}}
					onBlur={onBlur}
					className="ff-input ff-input--money"
				/>
			</div>
		</FieldShell>
	);
}
