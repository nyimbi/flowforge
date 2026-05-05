# flowforge-cli

Typer-based CLI front end for the flowforge framework. Implements the §10.1
command surface: `new`, `add-jtbd`, `regen-catalog`, `validate`, `simulate`,
`migrate-fork`, plus skeleton stubs for `diff`, `replay`, `upgrade-deps`,
`audit verify`, and `ai-assist`.

## Install

```
uv pip install -e framework/python/flowforge-cli
```

The package installs a `flowforge` entry point. Each command lives in its own
module under `flowforge_cli.commands.*` and is registered onto the root Typer
app in `flowforge_cli.main`.

## Implemented commands

| Command | Status |
|---|---|
| `flowforge new <project> --jtbd <bundle>` | Implemented (Jinja2 backend skeleton scaffold) |
| `flowforge add-jtbd <bundle>` | Implemented (idempotent JTBD merge into project) |
| `flowforge validate [--def <path>]` | Implemented (schema + topology + priorities + lookup-permission) |
| `flowforge simulate --def <path> [--context ...] [--events ...]` | Implemented (plan/commit log shape per §10.4) |
| `flowforge regen-catalog [--root <path>]` | Implemented (workflows/catalog.json projection) |
| `flowforge migrate-fork <upstream-def> --to <tenant>` | Implemented (per-tenant fork copy) |
| `flowforge diff <vidA> <vidB>` | Skeleton (raises NotImplementedError) |
| `flowforge replay --event <uuid>` | Skeleton (raises NotImplementedError) |
| `flowforge upgrade-deps` | Skeleton (raises NotImplementedError) |
| `flowforge audit verify` | Skeleton (raises NotImplementedError) |
| `flowforge ai-assist <bundle>` | Skeleton (raises NotImplementedError) |

## Testing

```
uv run --package flowforge-cli pytest framework/python/flowforge-cli/tests -q
```

Tests use `typer.testing.CliRunner` for command-level coverage.

## See also

* `docs/workflow-framework-portability.md` §10 (CLI design, sample outputs)
* `framework/python/flowforge-core/src/flowforge/dsl/schema/*.json`
