# Changelog

## 0.1.0 — 2026-05-05

Initial release (U06).

- `HandlerRegistry`: register/dispatch handlers per `(backend, kind)`, multi-backend support, decorator API, introspection
- `DrainWorker`: poll-and-drain with `FOR UPDATE SKIP LOCKED` on PostgreSQL, SQLite compat mode for tests, retry counter, DLQ after max retries or age threshold, `run_loop` background coroutine, `enqueue` helper, `setup` DDL bootstrap
- `OutboxStatus`: enum of row lifecycle states
- `OutboxRow`, `DrainResult` dataclasses
- Tests: 20 pytest cases covering all acceptance criteria (registry, worker, DLQ, retries, multi-backend, run_loop)
