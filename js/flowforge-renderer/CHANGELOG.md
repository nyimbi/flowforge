# @flowforge/renderer changelog

## 0.1.0

- FormRenderer + 24 field components (text, textarea, rich_text, number, money,
  percentage, date, datetime, boolean, enum, multi_select, file, signature,
  party_picker, document_picker, address, phone, email, url, color, json,
  hidden, lookup, plus the legacy `_ref` aliases).
- Whitelisted expression evaluator for `visible_if`, `required_if`,
  `disabled_if`, and `computed.expr`.
- Pluggable async lookup hooks via the `lookups` registry.
- Ajv 2020-12 validator with field-keyed error messages and AJV format support.
- Vitest + react-testing-library coverage for renderer behavior, validator
  rules, and the expression evaluator.
