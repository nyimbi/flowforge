# Adapter Packages Audit

Date: 2026-07-08

Scope:

- `python/flowforge-sqlalchemy`
- `python/flowforge-documents-s3`
- `python/flowforge-signing-kms`
- `python/flowforge-rbac-spicedb`

## Executive Summary

All four package test suites pass after the audit. Literal stub search found no `NotImplementedError`, bare `pass`, `TODO`, or `FIXME` markers in any target `src/` tree. A stricter `rg` pass for the same markers is also clean. All four packages received either an implementation/security fix or a stub-marker cleanup:

| Package | Result | Fix commit |
|---|---|---|
| `flowforge-sqlalchemy` | Added missing generic SQLAlchemy ORM `EntityAdapter` with create/update/lookup/delete and tests. | `314a85b` |
| `flowforge-documents-s3` | S3 blob API, `DocumentPort`, presigned URL helpers, doc-id validation, magic-byte validation, and optional SQLite index were already implemented. Removed a non-stub bare `pass` marker in the optional libmagic fallback. | `eabd599` |
| `flowforge-signing-kms` | Removed final reachable hardcoded HMAC fallback secret path. HMAC verification already used `hmac.compare_digest`; tests now ratchet that the fallback secret string is absent. Removed non-stub bare `pass` markers in KMS metrics fallback logging. | `c42cab8`, `5f21f89` |
| `flowforge-rbac-spicedb` | Added resolver-level `grant`, `revoke`, and `check_permission` alias using `WriteRelationships`; updated fake client to evaluate those relationships. | `ec252aa` |

## Exact Audit Commands

Tests:

```bash
UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/<pkg>/tests -q --tb=no 2>&1 | tail -3
```

Stub search:

```bash
grep -rn 'NotImplementedError\|raise NotImplementedError\|^\s*pass$\|TODO\|FIXME' python/<pkg>/src/ --include='*.py'
```

Broad security grep:

```bash
grep -rn 'eval\|exec\|sql\|INSERT\|DELETE\|SELECT' python/<pkg>/src/ --include='*.py' -n | head -20
```

## Source Files

### `flowforge-sqlalchemy`

- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/__init__.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/alembic_bundle/__init__.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/alembic_bundle/env.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/alembic_bundle/versions/r1_initial.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/alembic_bundle/versions/r2_workflow_tasks.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/base.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/entity_adapter.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/models.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/rls_pg.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/saga_queries.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/snapshot_store.py`
- `python/flowforge-sqlalchemy/src/flowforge_sqlalchemy/task_tracker.py`

### `flowforge-documents-s3`

- `python/flowforge-documents-s3/src/flowforge_documents_s3/__init__.py`
- `python/flowforge-documents-s3/src/flowforge_documents_s3/noop.py`
- `python/flowforge-documents-s3/src/flowforge_documents_s3/port.py`

### `flowforge-signing-kms`

- `python/flowforge-signing-kms/src/flowforge_signing_kms/__init__.py`
- `python/flowforge-signing-kms/src/flowforge_signing_kms/errors.py`
- `python/flowforge-signing-kms/src/flowforge_signing_kms/hmac_dev.py`
- `python/flowforge-signing-kms/src/flowforge_signing_kms/kms.py`

### `flowforge-rbac-spicedb`

- `python/flowforge-rbac-spicedb/src/flowforge_rbac_spicedb/__init__.py`
- `python/flowforge-rbac-spicedb/src/flowforge_rbac_spicedb/_wire.py`
- `python/flowforge-rbac-spicedb/src/flowforge_rbac_spicedb/resolver.py`
- `python/flowforge-rbac-spicedb/src/flowforge_rbac_spicedb/testing.py`

## Test Evidence

Post-fix exact command output:

```text
== flowforge-sqlalchemy tests ==
.....s......................................                             [100%]
43 passed, 1 skipped in 0.70s

== flowforge-documents-s3 tests ==
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
32 passed, 2 warnings in 2.22s

== flowforge-signing-kms tests ==
......................................................                   [100%]
54 passed in 1.12s

== flowforge-rbac-spicedb tests ==
........................                                                 [100%]
24 passed in 0.11s
```

## Stub Findings

Post-fix stub grep returned no matches for all four package `src/` trees. A stricter `rg` scan for `NotImplementedError`, `raise NotImplementedError`, bare `pass`, `TODO`, `FIXME`, and the old HMAC fallback secret string also returned no matches.

## Security Grep Findings

The broad grep found no `eval` or `exec` usage in the target package `src/` trees. Remaining hits were reviewed:

- `flowforge-sqlalchemy`: SQLAlchemy imports and parameterized `text("SELECT set_config(..., :param, true)")` RLS calls. No string interpolation into SQL was found.
- `flowforge-documents-s3`: stdlib `sqlite3` index store calls using `?` parameters, plus the noop docstring word `documents_complete`. No S3 credentials or hardcoded secrets found.
- `flowforge-signing-kms`: no hits from the requested broad grep after removing the fallback secret path. Additional verification found `hmac.compare_digest` in `HmacDevSigning.verify`.
- `flowforge-rbac-spicedb`: `OPERATION_DELETE` enum and grant/revoke relationship deletion handling. No dynamic execution or secrets found.

## Package Findings

### `flowforge-sqlalchemy`

Implemented before audit:

- Async SQLAlchemy 2.x models and session-backed stores.
- `PgRlsBinder` with PostgreSQL-only `set_config` calls and no-op behavior for SQLite/unknown sessions.
- `SqlAlchemySnapshotStore` with tenant-scoped get/put/create, optimistic `compare_and_put`, and transactional `fire_and_commit`.
- `SagaQueries` append/list/mark/list-pending helpers.

Gap fixed:

- The package did not provide the expected generic SQLAlchemy ORM entity adapter. Added `SqlAlchemyEntityAdapter`, exported it, documented it, and added tests covering create, update, lookup, delete, unknown field rejection, primary-key update rejection, and field configuration validation.

Residual notes:

- `get_roles` is not part of the current core `EntityAdapter` or SQLAlchemy storage contract.
- `PgRlsBinder` uses parameterized SQLAlchemy `text()` calls for GUC binding; no string-built SQL was found.

### `flowforge-documents-s3`

Implemented:

- `S3DocumentPortInMemory` satisfies `DocumentPort` and exposes `put`, `get`, `list`, `delete`, `presigned_get_url`, `presigned_put_url`, and `presigned_post`.
- S3 calls use boto3 through `asyncio.to_thread`, so callers get an async-friendly adapter despite boto3 being synchronous.
- `presigned_put_url` is disabled unless `allow_unvalidated_presigned_put=True`; `presigned_post` includes explicit content-type and optional size policy conditions.
- Doc IDs are validated against a safe character set.
- Uploads pass through magic-byte validation, including structural Office ZIP checks.
- `SQLiteDocumentIndex` persists metadata and subject attachments using parameterized sqlite queries.

Fix made:

- Removed a non-stub bare `pass` marker from the optional libmagic fallback path. The behavior is still explicit fallback to `application/octet-stream` when detection cannot run.

Security review:

- No stubs, hardcoded AWS credentials, or private keys were found.

Residual notes:

- Two test warnings remain in the package suite; they were pre-existing and not tied to a failing behavior in this audit.

### `flowforge-signing-kms`

Implemented:

- `HmacDevSigning` signs HMAC-SHA256 payloads.
- `HmacDevSigning.verify` uses `hmac.compare_digest`.
- `AwsKmsSigning` and `GcpKmsSigning` delegate to cloud KMS APIs via `asyncio.to_thread` and classify transient, unknown-key, and invalid-signature cases.

Security issue fixed:

- Removed the hardcoded legacy HMAC fallback secret path that was reachable through `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`.
- Updated tests so that setting `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` still raises without explicit secret material.
- Added a test ratchet that the old fallback secret string is absent from `hmac_dev.py`.
- Removed non-stub bare `pass` markers from AWS/GCP transient-error metrics fallback blocks and replaced them with debug logging.

Residual notes:

- `FLOWFORGE_ALLOW_INSECURE_DEFAULT` remains mentioned in package docs as ignored/fail-closed compatibility context, but it no longer creates signing material.

### `flowforge-rbac-spicedb`

Implemented before audit:

- `SpiceDBRbac.has_permission` calls `CheckPermission`.
- `SpiceDBRbac.list_principals_with` calls `LookupSubjects`.
- `register_permission` and `assert_seed` maintain a synthetic permission catalogue through `WriteRelationships` and `LookupSubjects`.
- Zedtoken read-after-write consistency is captured and forwarded on subsequent reads.

Gap fixed:

- Added resolver-level `grant(principal, permission, scope)` and `revoke(...)`, implemented with `WriteRelationships` `TOUCH` and `DELETE`.
- Added `check_permission(...)` as a compatibility alias for SpiceDB-style callers.
- Updated `FakeSpiceDBClient.CheckPermission` to evaluate relationships written through `WriteRelationships`, not just fake-only helper grants.

Residual notes:

- `get_roles` is not part of the current core `RbacResolver` protocol. This package resolves permissions and lists principals for a permission; role enumeration would require a schema-specific role relation contract that does not exist in the current port.

## Commits

- `314a85b fix(flowforge-sqlalchemy): implement stubs and fix security issues found in adapter audit`
- `c42cab8 fix(flowforge-signing-kms): implement stubs and fix security issues found in adapter audit`
- `ec252aa fix(flowforge-rbac-spicedb): implement stubs and fix security issues found in adapter audit`
- `eabd599 fix(flowforge-documents-s3): implement stubs and fix security issues found in adapter audit`
- `5f21f89 fix(signing-kms): security hardening - HMAC dev signing adapter`
