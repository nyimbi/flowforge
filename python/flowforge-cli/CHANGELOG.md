# flowforge-cli changelog

## 0.2.0

- **U19 — JTBD-to-app generator**: deterministic transform from a JTBD
  bundle to a full app skeleton. Per JTBD: alembic migration,
  SQLAlchemy 2.x model, workflow adapter, JSON DSL workflow_def, form
  spec, simulation pytest, Next.js step component + page. Cross-bundle
  aggregations: permissions catalog, audit topic taxonomy, notification
  rules, alembic env, README, .env.example. New `flowforge jtbd-generate`
  CLI subcommand wraps the same pipeline. Pure jinja2, no LLM.

## 0.1.0

- Initial release of the typer-based `flowforge` CLI.
- Implemented commands: `new`, `add-jtbd`, `validate`, `simulate`,
  `regen-catalog`, `migrate-fork`.
- Skeleton commands raising `NotImplementedError`: `diff`, `replay`,
  `upgrade-deps`, `audit verify`, `ai-assist`.
- Jinja2 backend project templates (deterministic, no network access).
- Test suite covers validate / simulate / new-scaffold / add-jtbd / regen-catalog
  / migrate-fork via `typer.testing.CliRunner`.
