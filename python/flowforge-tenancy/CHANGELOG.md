# flowforge-tenancy changelog

## 0.1.0 — Unreleased

### [SECURITY] E-36 — tenancy SQL hardening (audit 2026)

- **T-01 (P0)**: `_set_config()` no longer string-interpolates the GUC name
  into SQL. Both name and value are bound as parameters via the constant
  template `SELECT set_config(:k, :v, true)`. The GUC name is additionally
  validated against `^[a-zA-Z_][a-zA-Z_0-9.]*$`; mismatches raise
  `ValueError` before the session is touched.
- **T-02 (P2)**: `_elevated` is now a per-instance `ContextVar` instead of
  a mutable per-instance attribute. Concurrent `elevated_scope()` calls in
  separate async tasks no longer leak elevation across tasks. Same fix
  applied to `MultiTenantGUC`.
- **T-03 (P3)**: `bind_session()` now asserts `session.in_transaction()`.
  Without an enclosing transaction the `set_config(..., true)` GUCs would
  not scope to the request and could leak; we now refuse to bind.

Regression tests: `tests/test_resolvers.py::test_T_01..T_03_*`,
`framework/tests/audit_2026/test_E_36_tenancy_hardening.py`,
`framework/tests/conformance/test_arch_invariants.py::test_invariant_1_tenant_isolation`.

Security ratchet: `scripts/ci/ratchets/no_string_interp_sql.sh`.

### Initial scaffolding

- Initial impls: `SingleTenantGUC`, `MultiTenantGUC`, `NoTenancy`.
- `elevated_scope()` context manager mirrors UMS `app.elevated` GUC pattern.
