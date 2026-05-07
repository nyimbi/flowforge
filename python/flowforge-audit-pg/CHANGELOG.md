# flowforge-audit-pg changelog

## Unreleased

### [SECURITY] E-37 — audit-chain hardening (audit 2026)

- **AU-01 (P1)** — concurrent record race: `record()` now serialises the
  read-head + write pair per tenant. PG path takes
  `pg_advisory_xact_lock(hashtext(tenant_norm))` inside the insert tx;
  SQLite (test) path uses an in-process `asyncio.Lock` keyed by tenant.
  An `ordinal BIGINT` column was added with `UNIQUE(tenant_id, ordinal)`
  as schema-level defence in depth — duplicate ordinals are rejected by
  the database even if a future regression slipped past the lock.
- **AU-02 (P1)** — `verify_chain()` streams rows in `VERIFY_CHUNK_SIZE`
  (default 10K) batches via keyset pagination on `(occurred_at, event_id)`.
  Peak memory is bounded by chunk size, not total row count. Tunable
  via `flowforge_audit_pg.sink.VERIFY_CHUNK_SIZE` in tests.
- **AU-03 (P1, escalated SOX/HIPAA)** — canonical bytes regression
  protection: a committed golden fixture
  (`framework/tests/audit_2026/fixtures/canonical_golden.bin`) records
  the canonical-JSON bytes and `row_sha256` for a fixed input vector.
  The new `flowforge_audit_pg._golden` module (loader/regenerator) signs
  the bundle with an envelope sha256; load refuses on mismatch.
  Regenerate after a deliberate format change with
  `python -m flowforge_audit_pg._golden write <path>` and route through
  security review.

Regression tests:
- `framework/tests/audit_2026/test_E_37_audit_chain_hardening.py` (6 tests)
- `framework/tests/conformance/test_arch_invariants.py::test_invariant_7_audit_chain_monotonic`
- `framework/python/flowforge-audit-pg/tests/test_sink.py` (existing 15
  tests, now run under both auto and STRICT asyncio modes)

## 0.1.0 — 2025-05-05

- Initial implementation (U05).
- `PgAuditSink` implementing `flowforge.ports.audit.AuditSink` protocol.
- `hash_chain` module: `canonical_json`, `compute_row_sha`, `redact_payload`, `verify_chain_in_memory`, `AuditRow`.
- `create_tables()` DDL helper: creates `ff_audit_events` and installs DELETE-blocking PG trigger.
- SQLite fallback via `aiosqlite` for tests and local dev.
- `verify_chain(since=...)` supports filtering by event_id or ISO datetime.
- `redact(paths, reason)` tombstones payload paths with `__REDACTED__` marker.
- pytest suite: 20+ tests covering hash chain correctness, tampering detection, redaction, multi-tenant chain isolation, and PG-specific trigger.

## Unreleased (prior placeholder)

- Package skeleton scaffolded; implementation pending in dedicated unit.
