# flowforge-rbac-static changelog

## 0.1.0 — Unreleased

- Initial `StaticRbac` resolver with YAML + JSON loaders.
- `assert_seed` returns missing names; strict mode raises `CatalogDriftError`.
- Idempotent `register_permission`; `list_principals_with` enumerates grants.
