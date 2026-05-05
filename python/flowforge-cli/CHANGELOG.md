# flowforge-cli changelog

## 0.1.0

- Initial release of the typer-based `flowforge` CLI.
- Implemented commands: `new`, `add-jtbd`, `validate`, `simulate`,
  `regen-catalog`, `migrate-fork`.
- Skeleton commands raising `NotImplementedError`: `diff`, `replay`,
  `upgrade-deps`, `audit verify`, `ai-assist`.
- Jinja2 backend project templates (deterministic, no network access).
- Test suite covers validate / simulate / new-scaffold / add-jtbd / regen-catalog
  / migrate-fork via `typer.testing.CliRunner`.
