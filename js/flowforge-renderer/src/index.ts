/**
 * @flowforge/renderer — public surface.
 */

export { FormRenderer, FieldShell } from "./FormRenderer.js";
export type { FormRendererProps, FieldComponent, FieldComponentMap } from "./FormRenderer.js";

export type {
	FieldKind,
	FieldOption,
	FieldValidation,
	FieldSource,
	ComputedSpec,
	FormField,
	LayoutSection,
	RendererFormSpec,
	FormValues,
	FormErrors,
	LookupHook,
	LookupRegistry,
} from "./types.js";

export { evaluate, evaluateBoolean } from "./expr.js";
export { buildValidator } from "./validators/ajv.js";
export type { ValidatorBundle } from "./validators/ajv.js";

// Individual field components — exported so hosts can compose custom forms.
export { TextField, EmailField, UrlField, PhoneField, ColorField, HiddenField } from "./fields/TextField.js";
export { TextAreaField, RichTextField } from "./fields/TextAreaField.js";
export { NumberField, PercentageField } from "./fields/NumberField.js";
export { MoneyField } from "./fields/MoneyField.js";
export { DateField, DateTimeField } from "./fields/DateField.js";
export { BooleanField } from "./fields/BooleanField.js";
export { EnumField, MultiSelectField } from "./fields/EnumField.js";
export { LookupField, PartyPickerField, DocumentPickerField } from "./fields/LookupField.js";
export { FileField } from "./fields/FileField.js";
export { SignatureField } from "./fields/SignatureField.js";
export { AddressField } from "./fields/AddressField.js";
export { JsonField } from "./fields/JsonField.js";
