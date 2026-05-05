# flowforge-rbac-spicedb changelog

## 0.1.0 — Unreleased

- Initial `SpiceDBRbac` resolver wrapping the `authzed-py` async client.
- `has_permission` delegates to `CheckPermission`; `register_permission`
  + `assert_seed` ride on a permission-catalogue relation maintained
  via `WriteRelationships`.
- `list_principals_with` uses `LookupSubjects`.
- `FakeSpiceDBClient` in `flowforge_rbac_spicedb.testing` lets CI run
  without a live SpiceDB.
