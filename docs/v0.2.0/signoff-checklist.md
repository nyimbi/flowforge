# v0.2.0 Signoff Checklist

Tracks engineering findings for the v0.2.0 release cycle.

| Finding | Description | Status | Test file | Notes |
|---------|-------------|--------|-----------|-------|
| E-75 | per-fix metric emitters | implemented | tests/audit_2026/test_E_75_metrics_emitted.py | 11 counters across 9 source files; no_orphan_promql_metrics.sh ratchet added |
| E-76 | JWT principal extractor | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | JwtPrincipalExtractor + make_jwt_extractor; async __call__; lazy-init (F-6); flowforge_jwt_tokens_issued_total metric |
| E-73 (phase 4) | audit identity in registry events | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | publish/demote/mark_verified accept principal=; _audit_payload merges principal_* fields into metadata only; canonical body unchanged (invariant 7) |
| E-73 (phase 5) | token rotation / revocation | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | RevocationList with TTL auto-eviction; flowforge_jwt_revocation_propagation_seconds histogram; is_revoked() rejects revoked jtis |
| E-73 (phase 6) | RBAC integration tests | implemented | tests/integration/python/tests/test_E_73_rbac_full.py | 11 tests: audit principal fields, canonical body invariant, token roundtrip, revocation, expiry, legacy admin compat, JWT roundtrip, tamper detection |
