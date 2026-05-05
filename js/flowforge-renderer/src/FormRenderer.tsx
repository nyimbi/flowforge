/**
 * FormRenderer — the top-level component that consumes a FormSpec and renders
 * a working form. Responsibilities:
 *   • own the form state map (controlled or uncontrolled)
 *   • dispatch each field to the right component
 *   • evaluate visible_if / required_if / disabled_if conditions on every render
 *   • compute computed-fields whenever upstream values change
 *   • run ajv validation on submit (and on blur, if `validateOn === "blur"`)
 *   • wire async lookup hooks via the `lookups` registry
 */

import {
	type FormEvent,
	type ReactNode,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import type {
	FieldKind,
	FormErrors,
	FormField,
	FormValues,
	LookupRegistry,
	RendererFormSpec,
} from "./types.js";
import { evaluate, evaluateBoolean } from "./expr.js";
import { buildValidator } from "./validators/ajv.js";
import { FieldShell, type FieldComponentProps } from "./fields/common.js";
import {
	ColorField,
	EmailField,
	HiddenField,
	PhoneField,
	TextField,
	UrlField,
} from "./fields/TextField.js";
import { RichTextField, TextAreaField } from "./fields/TextAreaField.js";
import { NumberField, PercentageField } from "./fields/NumberField.js";
import { MoneyField } from "./fields/MoneyField.js";
import { DateField, DateTimeField } from "./fields/DateField.js";
import { BooleanField } from "./fields/BooleanField.js";
import { EnumField, MultiSelectField } from "./fields/EnumField.js";
import { DocumentPickerField, LookupField, PartyPickerField } from "./fields/LookupField.js";
import { FileField } from "./fields/FileField.js";
import { SignatureField } from "./fields/SignatureField.js";
import { AddressField } from "./fields/AddressField.js";
import { JsonField } from "./fields/JsonField.js";

export type FieldComponent = (props: FieldComponentProps) => ReactNode;

export type FieldComponentMap = Partial<Record<FieldKind | string, FieldComponent>>;

const DEFAULT_COMPONENTS: Record<FieldKind, FieldComponent> = {
	text: TextField,
	textarea: TextAreaField,
	number: NumberField,
	money: MoneyField,
	date: DateField,
	datetime: DateTimeField,
	boolean: BooleanField,
	enum: EnumField,
	multi_select: MultiSelectField,
	file: FileField,
	signature: SignatureField,
	rich_text: RichTextField,
	party_ref: PartyPickerField,
	party_picker: PartyPickerField,
	document_ref: DocumentPickerField,
	document_picker: DocumentPickerField,
	address: AddressField,
	phone: PhoneField,
	email: EmailField,
	url: UrlField,
	color: ColorField,
	percentage: PercentageField,
	json: JsonField,
	hidden: HiddenField,
	lookup: LookupField,
};

export interface FormRendererProps {
	spec: RendererFormSpec;
	/** Initial / controlled values keyed by field id. */
	values?: FormValues;
	defaultValues?: FormValues;
	onChange?: (values: FormValues) => void;
	onSubmit?: (values: FormValues) => void | Promise<void>;
	onValidate?: (errors: FormErrors) => void;
	disabled?: boolean;
	readOnly?: boolean;
	validateOn?: "submit" | "blur" | "change";
	lookups?: LookupRegistry;
	/** Per-kind override map, e.g. swap TextField for a TipTap-backed component. */
	fieldComponents?: FieldComponentMap;
	/** Optional submit button text; pass null to suppress the default submit row. */
	submitLabel?: string | null;
	className?: string;
	/** Test hook — exposes the rendered field set for assertions. */
	"data-testid"?: string;
}

function pickValue(field: FormField, values: FormValues): unknown {
	const v = values[field.id];
	if (v !== undefined) return v;
	return field.default;
}

function computeAll(spec: RendererFormSpec, values: FormValues): FormValues {
	let next = values;
	for (const f of spec.fields) {
		if (!f.computed) continue;
		try {
			const out = evaluate(f.computed.expr, next);
			if (next[f.id] !== out) {
				next = { ...next, [f.id]: out };
			}
		} catch {
			/* ignore expression errors; surface via validator instead */
		}
	}
	return next;
}

export function FormRenderer({
	spec,
	values: controlledValues,
	defaultValues,
	onChange,
	onSubmit,
	onValidate,
	disabled,
	readOnly,
	validateOn = "submit",
	lookups,
	fieldComponents,
	submitLabel = "Submit",
	className,
	"data-testid": testId,
}: FormRendererProps) {
	const isControlled = controlledValues !== undefined;
	const [internalValues, setInternalValues] = useState<FormValues>(() => {
		const seeded: FormValues = { ...(defaultValues ?? {}) };
		for (const f of spec.fields) {
			if (seeded[f.id] === undefined && f.default !== undefined) {
				seeded[f.id] = f.default;
			}
		}
		return computeAll(spec, seeded);
	});
	const [errors, setErrors] = useState<FormErrors>({});
	const [submitting, setSubmitting] = useState(false);
	const onChangeRef = useRef(onChange);
	onChangeRef.current = onChange;

	const baseValues = isControlled ? controlledValues! : internalValues;
	const values = useMemo(() => computeAll(spec, baseValues), [spec, baseValues]);

	const validator = useMemo(() => buildValidator(spec), [spec]);

	const setValue = useCallback(
		(id: string, next: unknown) => {
			const updated = { ...values, [id]: next };
			const computed = computeAll(spec, updated);
			if (!isControlled) setInternalValues(computed);
			onChangeRef.current?.(computed);
			if (validateOn === "change") {
				const errs = validator.validate(computed);
				setErrors(errs);
				onValidate?.(errs);
			}
		},
		[isControlled, onValidate, spec, validator, validateOn, values],
	);

	const handleBlur = useCallback(
		(_id: string) => {
			if (validateOn === "blur") {
				const errs = validator.validate(values);
				setErrors(errs);
				onValidate?.(errs);
			}
		},
		[onValidate, validator, validateOn, values],
	);

	useEffect(() => {
		// Re-run validation when spec changes so error state stays consistent.
		if (validateOn === "change" || validateOn === "blur") {
			const errs = validator.validate(values);
			setErrors(errs);
		}
	}, [validator, validateOn, values]);

	const handleSubmit = useCallback(
		async (e: FormEvent<HTMLFormElement>) => {
			e.preventDefault();
			const errs = validator.validate(values);
			// Required-if check augments static `required` flag.
			for (const f of spec.fields) {
				if (errs[f.id]) continue;
				const requiredIf = f.required_if !== undefined ? evaluateBoolean(f.required_if, values, false) : false;
				if (f.required || requiredIf) {
					const v = values[f.id];
					if (v === undefined || v === null || v === "") {
						errs[f.id] = "Required";
					}
				}
			}
			setErrors(errs);
			onValidate?.(errs);
			if (Object.keys(errs).length > 0) return;
			if (!onSubmit) return;
			setSubmitting(true);
			try {
				await onSubmit(values);
			} finally {
				setSubmitting(false);
			}
		},
		[onSubmit, onValidate, spec.fields, validator, values],
	);

	const components = useMemo<Record<string, FieldComponent>>(
		() => ({ ...DEFAULT_COMPONENTS, ...(fieldComponents ?? {}) }),
		[fieldComponents],
	);

	const renderField = (field: FormField) => {
		const visible = field.visible_if === undefined ? true : evaluateBoolean(field.visible_if, values, true);
		if (!visible) return null;

		const requiredIf =
			field.required_if !== undefined ? evaluateBoolean(field.required_if, values, false) : false;
		const disabledIf =
			field.disabled_if !== undefined ? evaluateBoolean(field.disabled_if, values, false) : false;
		const fieldRequired = Boolean(field.required) || requiredIf;
		const fieldDisabled = Boolean(disabled) || disabledIf;
		const isComputed = Boolean(field.computed);
		const fieldReadOnly = Boolean(readOnly) || isComputed;

		const Component = components[field.kind] ?? TextField;
		const lookupForField = makeLookupCallback(field, values, lookups);

		const augmented: FormField = { ...field, required: fieldRequired };

		return (
			<Component
				key={field.id}
				field={augmented}
				value={pickValue(field, values)}
				error={errors[field.id]}
				disabled={fieldDisabled}
				readOnly={fieldReadOnly}
				onChange={(next) => setValue(field.id, next)}
				onBlur={() => handleBlur(field.id)}
				lookup={lookupForField}
			/>
		);
	};

	const renderSection = (sectionIdx: number, title: string | undefined, fields: FormField[]) => (
		<fieldset key={`section-${sectionIdx}`} className="ff-section" data-section-index={sectionIdx}>
			{title ? <legend className="ff-section__title">{title}</legend> : null}
			{fields.map(renderField)}
		</fieldset>
	);

	const sections: ReactNode[] = useMemo(() => {
		const fieldById = new Map(spec.fields.map((f) => [f.id, f] as const));
		if (Array.isArray(spec.layout) && spec.layout.length > 0) {
			const used = new Set<string>();
			const rendered: ReactNode[] = spec.layout.map((sec, i) => {
				const fields = sec.field_ids.map((id) => fieldById.get(id)).filter((f): f is FormField => Boolean(f));
				for (const f of fields) used.add(f.id);
				return renderSection(i, sec.title, fields);
			});
			const leftover = spec.fields.filter((f) => !used.has(f.id));
			if (leftover.length > 0) rendered.push(renderSection(spec.layout.length, undefined, leftover));
			return rendered;
		}
		return [renderSection(0, undefined, spec.fields)];
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [spec, values, errors, disabled, readOnly]);

	const formError = errors._form;

	return (
		<form
			onSubmit={handleSubmit}
			className={["ff-form", className].filter(Boolean).join(" ")}
			data-testid={testId}
			data-form-id={spec.id}
			data-form-version={spec.version}
			noValidate
		>
			{spec.title ? (
				<header className="ff-form__header">
					<h2 className="ff-form__title">{spec.title}</h2>
				</header>
			) : null}
			{formError ? (
				<p className="ff-form__error" role="alert" data-form-error>
					{formError}
				</p>
			) : null}
			{sections}
			{submitLabel !== null ? (
				<div className="ff-form__actions">
					<button type="submit" className="ff-button ff-button--primary" disabled={submitting || disabled}>
						{submitting ? "Submitting…" : submitLabel}
					</button>
				</div>
			) : null}
		</form>
	);
}

function makeLookupCallback(
	field: FormField,
	values: FormValues,
	lookups: LookupRegistry | undefined,
): ((query?: string) => Promise<{ v: string; label?: string }[]>) | undefined {
	const source = field.source as { hook?: string } | undefined;
	if (!source?.hook || !lookups || !lookups[source.hook]) return undefined;
	const hook = lookups[source.hook]!;
	return (query?: string) => hook({ field, values, query });
}

// Re-export FieldShell so consumers building their own field components can
// reuse the label/error/help chrome.
export { FieldShell };
