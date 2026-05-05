import { FieldShell, type FieldComponentProps } from "./common.js";

interface AddressValue {
	line1?: string;
	line2?: string;
	city?: string;
	region?: string;
	postal_code?: string;
	country?: string;
}

function read(value: unknown): AddressValue {
	return value && typeof value === "object" ? (value as AddressValue) : {};
}

export function AddressField({ field, value, error, disabled, readOnly, onChange, onBlur }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const addr = read(value);
	const update = (key: keyof AddressValue) => (e: React.ChangeEvent<HTMLInputElement>) => {
		onChange({ ...addr, [key]: e.target.value });
	};

	return (
		<FieldShell field={field} error={error} htmlFor={`${id}-line1`}>
			<div className="ff-address">
				<input
					id={`${id}-line1`}
					name={`${field.id}.line1`}
					type="text"
					value={addr.line1 ?? ""}
					placeholder="Address line 1"
					disabled={disabled}
					readOnly={readOnly}
					onChange={update("line1")}
					onBlur={onBlur}
					className="ff-input"
				/>
				<input
					name={`${field.id}.line2`}
					type="text"
					value={addr.line2 ?? ""}
					placeholder="Address line 2"
					disabled={disabled}
					readOnly={readOnly}
					onChange={update("line2")}
					onBlur={onBlur}
					className="ff-input"
				/>
				<div className="ff-address__row">
					<input
						name={`${field.id}.city`}
						type="text"
						value={addr.city ?? ""}
						placeholder="City"
						disabled={disabled}
						readOnly={readOnly}
						onChange={update("city")}
						onBlur={onBlur}
						className="ff-input"
					/>
					<input
						name={`${field.id}.region`}
						type="text"
						value={addr.region ?? ""}
						placeholder="State / Region"
						disabled={disabled}
						readOnly={readOnly}
						onChange={update("region")}
						onBlur={onBlur}
						className="ff-input"
					/>
					<input
						name={`${field.id}.postal_code`}
						type="text"
						value={addr.postal_code ?? ""}
						placeholder="Postal code"
						disabled={disabled}
						readOnly={readOnly}
						onChange={update("postal_code")}
						onBlur={onBlur}
						className="ff-input"
					/>
				</div>
				<input
					name={`${field.id}.country`}
					type="text"
					value={addr.country ?? ""}
					placeholder="Country"
					disabled={disabled}
					readOnly={readOnly}
					onChange={update("country")}
					onBlur={onBlur}
					className="ff-input"
				/>
			</div>
		</FieldShell>
	);
}
