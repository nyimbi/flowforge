# v0.2.0 Signoff Checklist

Tracks engineering findings for the v0.2.0 release cycle.

| Finding | Description | Status | Test file | Notes |
|---------|-------------|--------|-----------|-------|
| E-74p1 | Instance.tokens snapshot field | implemented | tests/audit_2026/test_E_74p1_instance_tokens.py | TokenSet field on Instance dataclass; snapshot/restore + shallow-clone isolation; tokens excluded from canonical audit body (R-2 / invariant 7) |
| E-75 | per-fix metric emitters | implemented | tests/audit_2026/test_E_75_metrics_emitted.py | 11 counters across 9 source files; no_orphan_promql_metrics.sh ratchet added |
| E-76 | JWT principal extractor | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | JwtPrincipalExtractor + make_jwt_extractor; async __call__; lazy-init (F-6); flowforge_jwt_tokens_issued_total metric |
| E-73 (phase 4) | audit identity in registry events | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | publish/demote/mark_verified accept principal=; _audit_payload merges principal_* fields into metadata only; canonical body unchanged (invariant 7) |
| E-73 (phase 5) | token rotation / revocation | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | RevocationList with TTL auto-eviction; flowforge_jwt_revocation_propagation_seconds histogram; is_revoked() rejects revoked jtis |
| E-73 (phase 6) | RBAC integration tests | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | 11 tests: audit principal fields, canonical body invariant, token roundtrip, revocation, expiry, legacy admin compat, JWT roundtrip, tamper detection |
| E-77p | team-prompt registry format validation | implemented | tests/audit_2026/test_E_77p_team_prompts.py | team prompt schema lint; registry entries validated against TeamPromptSpec; format ratchet added |
| E-79 | parallel_fork dispatch in fire() | implemented | tests/audit_2026/test_E_79_fork_dispatch.py | fork dispatch behind layered feature flag (FLOWFORGE_FORKS_ENABLED + engine_features metadata); tokens rolled back on outbox failure (C-01 contract) |
| E-80 | per-token advance via token_id | implemented | tests/audit_2026/test_E_80_per_token_advance.py | fire(token_id=) routes to branch token; TokenAlreadyConsumedError + metric on unknown id; RegionStillForkedError blocks primary fire while tokens live |
| E-81 | join barrier collapse | implemented | tests/audit_2026/test_E_81_join_barrier.py | join collapses instance to terminal when all branch tokens drained; join_collapsed audit event emitted; partial drain leaves state at fork_point |
| E-82 | e2e fork flow + invariant 9 + soak flags + fork PromQL alerts | implemented | tests/audit_2026/test_E_82_e2e_fork.py | invariant 9 strengthened (lifecycle through fire()); IT-02 flow 3 upgraded to parallel_fork; soak.sh --workflow/--forks-enabled flags; fork-engine PromQL alert group added |
| R-01 | registry schema: required fields present | implemented | tests/audit_2026/test_R01_R07_registry_format.py | all registry entries carry id, version, schema_version, and created_at fields |
| R-02 | registry schema: canonical JSON determinism | implemented | tests/audit_2026/test_R01_R07_registry_format.py | RFC-8785 canonical serialisation; spec_hash() is stable across Python versions |
| R-03 | registry schema: extra fields forbidden on canonical models | implemented | tests/audit_2026/test_R01_R07_registry_format.py | extra='forbid' on all Pydantic v2 registry models; wire-tolerant lint models use extra='allow' separately |
| R-04 | registry schema: version field format | implemented | tests/audit_2026/test_R01_R07_registry_format.py | semver regex enforced via AfterValidator; pre-release and build-metadata variants tested |
| R-05 | registry schema: lockfile pin matches spec_hash | implemented | tests/audit_2026/test_R01_R07_registry_format.py | JtbdLockfile.verify() recomputes spec_hash and raises LockfileMismatch on drift |
| R-06 | registry schema: cross-domain id collision detection | implemented | tests/audit_2026/test_R01_R07_registry_format.py | registry load raises DuplicateRegistryId when two bundles share an id; scoped per-tenant |
| R-07 | registry schema: migration lint for promoted domain packages | implemented | tests/audit_2026/test_R01_R07_registry_format.py | packages flipped to package=true must pass E-48a (rebrand) or E-48b (SME review) gate before registry acceptance |
