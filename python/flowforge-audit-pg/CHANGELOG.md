# flowforge-audit-pg changelog

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
