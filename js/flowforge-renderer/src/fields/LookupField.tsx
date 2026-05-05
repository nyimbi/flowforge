import { useEffect, useState } from "react";
import { FieldShell, type FieldComponentProps } from "./common.js";

/**
 * Async lookup field. The renderer wires the async resolver via the `lookup`
 * prop (resolved from the `lookups` registry on FormRenderer using
 * `field.source.hook`). When no hook is configured the field falls back to a
 * static option list.
 */
export function LookupField({ field, value, error, disabled, readOnly, onChange, onBlur, lookup }: FieldComponentProps) {
	const id = `ff-${field.id}`;
	const [query, setQuery] = useState("");
	const [options, setOptions] = useState<{ v: string; label?: string }[]>(field.options ?? []);
	const [loading, setLoading] = useState(false);

	useEffect(() => {
		if (!lookup) return;
		const ac = new AbortController();
		setLoading(true);
		lookup(query)
			.then((res) => {
				if (!ac.signal.aborted) setOptions(res);
			})
			.catch((err) => {
				if (ac.signal.aborted) return;
				if ((err as { name?: string }).name === "AbortError") return;
				// Surface failure by showing zero options; renderer error UI handles it.
				setOptions([]);
			})
			.finally(() => {
				if (!ac.signal.aborted) setLoading(false);
			});
		return () => ac.abort();
	}, [lookup, query]);

	return (
		<FieldShell field={field} error={error} htmlFor={id}>
			<div className="ff-lookup">
				<input
					id={`${id}-q`}
					type="search"
					value={query}
					placeholder={field.placeholder ?? "Search…"}
					onChange={(e) => setQuery(e.target.value)}
					disabled={disabled || readOnly}
					aria-busy={loading}
					className="ff-input"
				/>
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
					<option value="">— Select —</option>
					{options.map((opt) => (
						<option key={opt.v} value={opt.v}>
							{opt.label ?? opt.v}
						</option>
					))}
				</select>
				{loading ? (
					<span className="ff-lookup__status" aria-live="polite">
						Loading…
					</span>
				) : null}
			</div>
		</FieldShell>
	);
}

/** Party + Document picker share the lookup mechanic with curated styling hooks. */
export function PartyPickerField(props: FieldComponentProps) {
	return <LookupField {...props} />;
}

export function DocumentPickerField(props: FieldComponentProps) {
	return <LookupField {...props} />;
}
