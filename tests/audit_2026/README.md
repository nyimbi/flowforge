# framework/tests/audit_2026

Per-finding regression tests named `test_<FINDING_ID>_<short>` per
audit-fix-plan §4 / §5.1. Each finding (e.g. C-01, SK-01, J-08) gets
exactly one test file or test function in this directory. The owning
ticket fills these in as it lands.

CI entry: `make audit-2026-unit`.

## Conventions

- File name: `test_<ID>_<short>.py` — e.g. `test_C_01_outbox_failure_rolls_back_fire.py`.
- A `fixtures/` subdirectory holds canonical golden bytes (e.g. `canonical_golden.bin` for AU-03).
- Tests are async by default (project CLAUDE.md); no `@pytest.mark.asyncio`
  decorator needed.
- Tests exercise the *real* behaviour — no mocks except for LLM calls per
  project conventions.

## Mapping to tickets

See `framework/docs/audit-fix-plan.md` §4.
