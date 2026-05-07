# E-73: jtbd-hub full per-user RBAC

**Status**: design + scaffold landed; full implementation pending
**Origin**: split from E-58 Hub residual per architect review V-1. Plan
§11 documented as the only architecturally-approved deferral.
**Not an audit finding.** Existing single-shared-admin-token mechanism +
rotation (E-58 JH-04) is documented and tested; full RBAC is a feature.

---

## 1. Current state (post-E-58)

- `framework/python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py:115-138`:
  `create_app(admin_token=...)` accepts a comma-separated list of admin
  tokens with constant-time `hmac.compare_digest` per check. Single
  shared role (admin / non-admin) — no per-user identity.
- All admin actions audit-logged (E-58 JH-04 split — rotation +
  audit-log delivered). Per-user accountability requires identity beyond
  "valid admin token holder".
- `rbac.py` (NEW scaffold) carries the planned API shapes; not yet
  imported by `app.py`.

## 2. Target behaviour

Replace the shared-admin-token model with:

- **Identity**: each request authenticates as a `Principal` (user_id +
  roles). Tokens are per-user JWTs (or opaque, looked up in a session
  store).
- **Roles**: `hub_admin`, `package_publisher`, `package_consumer`,
  optionally `auditor`.
- **Authorisation**: every admin route declares required role(s);
  middleware enforces.
- **Audit**: every admin action records the principal user_id, not just
  "admin token used".
- **Token lifecycle**: rotation, revocation, expiry. Lean on the
  existing `flowforge-signing-kms` infrastructure (E-34 / SK-01..SK-04).

## 3. Compatibility

- Continue accepting the `admin_token=` kwarg for one minor (deprecation
  bridge). Any host using shared-token gets mapped to a synthetic
  `Principal(user_id="legacy_admin", roles=("hub_admin",))`.
- Audit events emit `principal_kind: "legacy_admin" | "user"` so
  operators can monitor migration.

## 4. Implementation phases

### Phase 1: Principal + Role types

- `rbac.py`: `Principal`, `Role`, `Permission` dataclasses.
- `Permission` enum: `package.publish`, `package.unpublish`,
  `admin.read`, `admin.write`, `audit.read`.
- `Role` -> `frozenset[Permission]` static map.

### Phase 2: PrincipalExtractor protocol

- `rbac.py`: `PrincipalExtractor(Protocol)` with
  `__call__(request) -> Principal | None`. Default impl reads JWT from
  `Authorization: Bearer ...`, verifies with KMS signer.
- `app.py`: `create_app(principal_extractor=...)` replaces
  `admin_token=...` (kwarg kept for one minor with the synthetic
  legacy_admin Principal).

### Phase 3: Route guards

- `@require(Permission.package_publish)` decorator on routes.
- `RequireMiddleware` for static path -> permission map (alternative).
- 401 vs 403 distinction: missing token -> 401, valid token without
  required permission -> 403.

### Phase 4: Audit integration

- Existing `_emit_audit_event` (E-37b) gains a `principal` field on
  `PackageRegistry` audit events.
- Audit log records `principal_user_id`, `principal_roles`,
  `principal_kind`.

### Phase 5: Token rotation + revocation

- Use `flowforge-signing-kms` `verify(key_id, ...)` (E-34 SK-02
  rotation-safe).
- Add a revocation list backing store (simple set of revoked
  user_id+jti pairs; cache locally with TTL).

### Phase 6: Tests

- `test_E_73_rbac_principal_extraction`: JWT + KMS roundtrip.
- `test_E_73_rbac_per_route_authorisation`: 401 vs 403 distinction.
- `test_E_73_rbac_audit_principal_recorded`: audit event carries
  per-user identity.
- `test_E_73_rbac_legacy_admin_token_compat`: deprecation bridge works
  for one minor.
- Property test: `Permission.is_subset(Role.permissions)` is reflexive
  + transitive.

## 5. Acceptance

- Every existing admin route has a declared `Permission` requirement.
- Audit events carry per-user identity (no anonymous "admin token
  used" entries).
- Legacy `admin_token=` kwarg still works (with `DeprecationWarning`)
  for one minor; emits `principal_kind: "legacy_admin"`.
- `flowforge-signing-kms` is the sole verifier — no embedded JWT
  library. Token format is the project's existing signed envelope.

## 6. Risks

- **R-1 (UMS integration)**: UMS host may have its own admin
  conventions. F-2 mitigation: build with `flowforge-jtbd-hub` UMS
  smoke set (existing 46/46 tests) green throughout, plus a new
  `test_e73_rbac_ums_admin_compat` integration test.
- **R-2 (token rotation race)**: rotation between request issue and
  request verify can transiently 401 valid tokens. Mitigation: KMS
  multi-key verifier (E-34 SK-02 already supports this).
- **R-3 (audit chain shape)**: adding `principal_*` fields to audit
  rows changes canonical_json bytes. Per E-37 schema_change_notes,
  bumping canonical body needs operator-driven backfill (analogous to
  AU-01 ordinal). Mitigation: principal fields go in event payload
  metadata, not the canonical body itself.

## 7. References

- Plan §1.4 reclassification table (JH-04 split rationale).
- Plan §11 "intentionally-deferred items" (E-73 named).
- `framework/docs/audit-2026/backlog.md`.
- `framework/docs/audit-2026/signoff-checklist.md` E-58 row (rotation +
  audit-log evidence; full RBAC explicitly out-of-scope).
