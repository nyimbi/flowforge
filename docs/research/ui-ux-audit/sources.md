# Sources Examined

No external web sources were used. This audit is based on local repository files, codebase-memory search, and local CLI help output.

## Required Files and Inventories

### FastAPI dashboard

- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py`
  - Full file read: 420 lines.
  - Key lines:
    - 19-26: dashboard docstring feature claims.
    - 42-48: rendering approach comment and Bootstrap/HTMX CDN constants.
    - 51-85: page shell, navbar, CDN includes.
    - 99-112: table helper.
    - 163-175: JSON health endpoint.
    - 181-222: overview route.
    - 228-281: instance list route.
    - 287-333: instance detail route.
    - 339-370: task queue route.
    - 376-415: audit log route.

### FastAPI package file listing

```text
python/flowforge-fastapi/src/flowforge_fastapi/__init__.py
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/__init__.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/__init__.cpython-313.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/auth.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/auth.cpython-313.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/dashboard.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/registry.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/registry.cpython-313.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/router_designer.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/router_designer.cpython-313.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/router_runtime.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/router_runtime.cpython-313.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/ws.cpython-311.pyc
python/flowforge-fastapi/src/flowforge_fastapi/__pycache__/ws.cpython-313.pyc
python/flowforge-fastapi/src/flowforge_fastapi/auth.py
python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py
python/flowforge-fastapi/src/flowforge_fastapi/py.typed
python/flowforge-fastapi/src/flowforge_fastapi/registry.py
python/flowforge-fastapi/src/flowforge_fastapi/router_designer.py
python/flowforge-fastapi/src/flowforge_fastapi/router_runtime.py
python/flowforge-fastapi/src/flowforge_fastapi/ws.py
```

### CLI app entrypoint

- `python/flowforge-cli/src/flowforge_cli/main.py`
  - Full file read: 98 lines.
  - Key lines:
    - 44-49: root Typer app.
    - 51-57: `audit` and `jtbd` subgroups.
    - 60-88: registered root and subgroup commands.

### CLI command module listing

```text
python/flowforge-cli/src/flowforge_cli/commands/__init__.py
python/flowforge-cli/src/flowforge_cli/commands/add_jtbd.py
python/flowforge-cli/src/flowforge_cli/commands/ai_assist.py
python/flowforge-cli/src/flowforge_cli/commands/audit_2026_health.py
python/flowforge-cli/src/flowforge_cli/commands/audit_verify.py
python/flowforge-cli/src/flowforge_cli/commands/bundle_diff.py
python/flowforge-cli/src/flowforge_cli/commands/diff.py
python/flowforge-cli/src/flowforge_cli/commands/generate_llmtxt.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_ai_draft.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_bundle_fork.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_compliance_lint.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_desktop.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_fork.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_generate.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_lint.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_lock.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_migrate.py
python/flowforge-cli/src/flowforge_cli/commands/jtbd_quality_score.py
python/flowforge-cli/src/flowforge_cli/commands/migrate_fork.py
python/flowforge-cli/src/flowforge_cli/commands/migration_safety.py
python/flowforge-cli/src/flowforge_cli/commands/new.py
python/flowforge-cli/src/flowforge_cli/commands/polish_copy.py
python/flowforge-cli/src/flowforge_cli/commands/pre_upgrade_check.py
python/flowforge-cli/src/flowforge_cli/commands/regen_catalog.py
python/flowforge-cli/src/flowforge_cli/commands/replay.py
python/flowforge-cli/src/flowforge_cli/commands/simulate.py
python/flowforge-cli/src/flowforge_cli/commands/tutorial.py
python/flowforge-cli/src/flowforge_cli/commands/upgrade_deps.py
python/flowforge-cli/src/flowforge_cli/commands/validate.py
```

## Requested CLI Help Commands

The direct requested commands were executed first:

```text
uv run flowforge --help 2>&1
uv run flowforge jtbd --help 2>&1
uv run flowforge audit --help 2>&1
```

All three initially failed in the sandbox with:

```text
error: failed to open file `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

They were rerun successfully with a writable cache:

```text
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge jtbd --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge audit --help 2>&1
```

### `flowforge --help`

Key observations:

- Help renders with Typer/Rich layout.
- Root help: `flowforge framework CLI - scaffold, validate, simulate workflows.`
- Root commands listed:
  - `new`
  - `add-jtbd`
  - `jtbd-generate`
  - `regen-catalog`
  - `validate`
  - `simulate`
  - `diff`
  - `replay`
  - `upgrade-deps`
  - `pre-upgrade-check`
  - `migration-safety`
  - `bundle-diff`
  - `migrate-fork`
  - `ai-assist`
  - `generate-llmtxt`
  - `polish-copy`
  - `tutorial`
  - `audit`
  - `jtbd`
  - `audit-2026`
- The `pre-upgrade-check` description includes internal release details and roadmap labels, making top-level help noisy.

### `flowforge jtbd --help`

Commands listed:

- `fork`
- `desktop`
- `lint`
- `lock`
- `bundle-fork`
- `migrate`
- `ai-draft`
- `quality-score`
- `compliance-lint`

Observation: group help says "fork, publish, lock" in the app setup, but no `publish` command is registered.

### `flowforge audit --help`

Commands listed:

- `verify`

Observation: `audit` is currently narrow. Operator workflows likely need `audit export`, filtering, range verification, and server-side audit health/status commands.

## Additional CLI Help Samples

The following representative help commands were also run with the writable uv cache:

```text
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge new --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge validate --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge simulate --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge jtbd lint --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge jtbd ai-draft --help 2>&1
env UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run flowforge tutorial --help 2>&1
```

Findings from these samples:

- Option descriptions are generally present.
- No command showed a dedicated examples section.
- `simulate --fault` includes a useful inline example.
- `jtbd lint` documents exit codes in the function docstring but the rendered help does not surface them as a first-class section.
- `tutorial` exposes `--pause/--no-pause` and `--dry-run`, which are good foundations for interactive/non-interactive use.

## Targeted Source Checks

### Real-time dashboard checks

Codebase-memory search for WebSocket/SSE/HTMX patterns in `python/flowforge-fastapi/src/flowforge_fastapi/` found:

- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py`
  - WebSocket fan-out hub exists.
  - `build_ws_router` exposes a WebSocket endpoint.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py`
  - `_HTMX` constant exists.
  - No dashboard `hx-*`, SSE, EventSource, or WebSocket usage was found.

### CLI prompt/progress/output checks

Codebase-memory searches across `python/flowforge-cli/src/flowforge_cli/commands/` found:

- `tutorial.py`
  - `input("  Press Enter to continue to the next step...")` at the pause point.
  - Step output and next-step suggestions.
- No broad use of `typer.prompt`, `typer.confirm`, Rich `Progress`, Rich `Status`, or progressbar abstractions was found in the command modules searched.
- Many commands use `typer.echo` directly.

### Line-numbered command snippets examined

- `python/flowforge-cli/src/flowforge_cli/commands/tutorial.py`
  - 166-171: step header output.
  - 191-206: subprocess command echo/run helper.
  - 262-290: tutorial options.
  - 417-436: pause prompt and completion next steps.
- `python/flowforge-cli/src/flowforge_cli/commands/validate.py`
  - 23-37: options.
  - 46-66: scan and summary behavior.
  - 83-100: success/error/warning status output.
- `python/flowforge-cli/src/flowforge_cli/commands/jtbd_lint.py`
  - 207-235: options.
  - 236-239: documented exit codes in docstring.
  - 244-291: default bundle detection, error output, JSON/text format, and exit behavior.

## Repository State

Before writing this audit, `git status --short` showed existing unrelated untracked paths:

```text
?? .claude/
?? docs/research/audit-2026-status/
```

Those paths were not modified by this audit.
