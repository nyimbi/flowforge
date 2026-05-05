// Generated from form_spec.schema.json — do not edit by hand.
// Run `pnpm gen` to regenerate.

export interface FormSpec {
  id: string;
  version: string;
  title: string;
  /**
   * @minItems 1
   */
  fields: [
    {
      id: string;
      kind:
        | "text"
        | "number"
        | "money"
        | "date"
        | "datetime"
        | "enum"
        | "boolean"
        | "party_ref"
        | "document_ref"
        | "email"
        | "phone"
        | "address"
        | "textarea"
        | "signature"
        | "file"
        | "lookup";
      label?: string;
      required?: boolean;
      pii?: boolean;
      default?: unknown;
      options?: {
        v: string;
        label?: string;
      }[];
      validation?: {
        [k: string]: unknown;
      };
      source?: {
        [k: string]: unknown;
      };
    },
    ...{
      id: string;
      kind:
        | "text"
        | "number"
        | "money"
        | "date"
        | "datetime"
        | "enum"
        | "boolean"
        | "party_ref"
        | "document_ref"
        | "email"
        | "phone"
        | "address"
        | "textarea"
        | "signature"
        | "file"
        | "lookup";
      label?: string;
      required?: boolean;
      pii?: boolean;
      default?: unknown;
      options?: {
        v: string;
        label?: string;
      }[];
      validation?: {
        [k: string]: unknown;
      };
      source?: {
        [k: string]: unknown;
      };
    }[]
  ];
  layout?: {
    kind: "section";
    title?: string;
    field_ids: string[];
  }[];
}
