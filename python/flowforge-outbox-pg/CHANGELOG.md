# Changelog

## Unreleased

- **(audit-2026 E-42, P1/P2)** Outbox hardening — closes findings OB-01..OB-04.
  - OB-01: `DrainWorker(table=...)` is whitelist-validated (`^[a-zA-Z_][a-zA-Z_0-9.]*$`); injection payloads like `"x; DROP TABLE foo"` raise `ValueError` at construction.
  - OB-02: `sqlite_compat=True` with `pool_size > 1` raises `RuntimeError`. SQLite is documented as test-only single-writer.
  - OB-03: New `reconnect_factory` constructor parameter. `run_loop` detects connection-loss exceptions (asyncpg / aiosqlite / OS-level), swaps in a fresh connection, and exposes the count via `worker.reconnects` for metrics scraping.
  - OB-04: `last_error` truncation moved from naive `[:2000]` (codepoints) to byte-budget `_truncate_utf8(s, 2000)` — multi-byte UTF-8 (CJK, emoji) survives without mid-codepoint cuts.

## 0.1.0 — 2026-05-05

Initial release (U06).

- `HandlerRegistry`: register/dispatch handlers per `(backend, kind)`, multi-backend support, decorator API, introspection
- `DrainWorker`: poll-and-drain with `FOR UPDATE SKIP LOCKED` on PostgreSQL, SQLite compat mode for tests, retry counter, DLQ after max retries or age threshold, `run_loop` background coroutine, `enqueue` helper, `setup` DDL bootstrap
- `OutboxStatus`: enum of row lifecycle states
- `OutboxRow`, `DrainResult` dataclasses
- Tests: 20 pytest cases covering all acceptance criteria (registry, worker, DLQ, retries, multi-backend, run_loop)
