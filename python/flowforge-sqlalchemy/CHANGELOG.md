# flowforge-sqlalchemy changelog

## 0.1.0 — 2026-05-05

Initial release (U03).

### Added

- Declarative `Base` + dialect-portable `JsonB` / `UuidStr` types in
  `flowforge_sqlalchemy.base`.
- ORM models for the ten engine-managed tables: `workflow_definitions`,
  `workflow_definition_versions`, `workflow_instances`,
  `workflow_instance_tokens`, `workflow_events`, `workflow_saga_steps`,
  `workflow_instance_quarantine`, `business_calendars`,
  `pending_signals`, `workflow_instance_snapshots`.
- `SqlAlchemySnapshotStore` implementing
  `flowforge.engine.snapshots.SnapshotStore`.
- `SagaQueries` — async read/write helpers over `workflow_saga_steps`
  including LIFO compensation iteration.
- `PgRlsBinder` — `flowforge.ports.rls.RlsBinder` for PostgreSQL with
  `set_config()`-based GUC binding and an `elevated()` context manager.
- Alembic bundle `r1_initial` with up/downgrade plus dialect-aware
  column types.
- Tests: models round-trip on async SQLite, Alembic upgrade/downgrade
  on SQLite (RLS skipped), Postgres-via-env-var optional, RLS binder
  against a stub session.

## Unreleased

- Package skeleton scaffolded; implementation pending in dedicated unit.
