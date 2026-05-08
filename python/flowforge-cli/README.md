# flowforge-cli

Typer-based command-line tool for the flowforge framework: scaffold projects, generate JTBD app skeletons, validate and simulate workflow definitions.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-cli
```

The package installs a `flowforge` entry point.

## What it does

`flowforge-cli` covers the §10.1 command surface for the flowforge framework. The implemented commands handle the full project lifecycle: scaffold a new project from a JTBD bundle, add bundles to an existing project, run the deterministic U19 JTBD generator that emits 12+ files per JTBD (SQLAlchemy models, Alembic migrations, FastAPI routers, domain services, React pages, pytest fixtures), validate workflow definition files against the schema and topology rules, simulate workflow execution, and regenerate the catalog index.

Two audit-2026 commands are also present: `flowforge pre-upgrade-check` audits the host for E-34 SK-01 readiness before a framework version bump, and `flowforge audit-2026 health` queries a Prometheus endpoint for the per-ticket SLI probes defined in the close-out criteria.

Commands that are stubs (`diff`, `replay`, `upgrade-deps`, `audit verify`, `ai-assist`) raise `NotImplementedError` at call time and are documented as such below.

## Quick start

```bash
# Scaffold a new project from a banking JTBD bundle
flowforge new my-app --jtbd flowforge-jtbd-banking

# Add another bundle to an existing project
flowforge add-jtbd flowforge-jtbd-hr

# Generate all app skeleton files for a bundle
flowforge jtbd-generate --jtbd flowforge-jtbd-banking --out ./generated

# Lint a JTBD bundle file
flowforge jtbd lint --def bundle.yaml

# Validate a workflow definition
flowforge validate --def workflows/account_open/definition.json

# Simulate a workflow
flowforge simulate --def workflows/account_open/definition.json

# Check SK-01 readiness before upgrading the framework
flowforge pre-upgrade-check signing

# Query Prometheus for audit-2026 release health
flowforge audit-2026 health --prom-url http://prometheus.local:9090
```

## CLI commands

| Command | Status | Summary |
|---|---|---|
| `flowforge new <project> --jtbd <bundle>` | Implemented | Scaffold a new project from a JTBD bundle using Jinja2 backend templates. |
| `flowforge add-jtbd <bundle>` | Implemented | Idempotently merge a JTBD bundle into an existing project. |
| `flowforge jtbd-generate --jtbd <bundle> --out <dir>` | Implemented | Run the U19 deterministic generator; emits 12+ files per JTBD. |
| `flowforge jtbd lint --def <path>` | Implemented | Lint a JTBD bundle via `flowforge_jtbd.lint.Linter`. |
| `flowforge jtbd fork <bundle>` | Implemented | Fork a bundle for per-tenant customisation. |
| `flowforge jtbd migrate` | Implemented | Run a JTBD bundle migration. |
| `flowforge validate [--def <path>]` | Implemented | Schema + topology + priorities + lookup-permission checks. |
| `flowforge simulate --def <path>` | Implemented | Plan/commit log shape per §10.4. |
| `flowforge regen-catalog [--root <path>]` | Implemented | Regenerate `workflows/catalog.json` projection. |
| `flowforge migrate-fork <upstream-def> --to <tenant>` | Implemented | Copy a workflow definition into a per-tenant fork. |
| `flowforge pre-upgrade-check [all\|signing]` | Implemented | F-7 mitigation: audit SK-01 env readiness; exits non-zero on failure. |
| `flowforge audit-2026 health` | Implemented | Query Prometheus for per-ticket SLI probes; exits non-zero on FAIL. |
| `flowforge generate-llmtxt` | Implemented | Emit an `llms.txt` index for the project. |
| `flowforge tutorial` | Implemented | Interactive guided tutorial. |
| `flowforge audit verify` | Skeleton | Raises `NotImplementedError`. |
| `flowforge diff <vidA> <vidB>` | Skeleton | Raises `NotImplementedError`. |
| `flowforge replay --event <uuid>` | Skeleton | Raises `NotImplementedError`. |
| `flowforge upgrade-deps` | Skeleton | Raises `NotImplementedError`. |
| `flowforge ai-assist <bundle>` | Skeleton | Raises `NotImplementedError`. |

## JTBD generator (U19)

`flowforge jtbd-generate --jtbd <bundle> --out <dir>` runs a deterministic, byte-identical transform from a validated JTBD bundle to a full app skeleton. Per JTBD it emits:

- `workflows/<id>/definition.json` — JSON DSL workflow definition
- `workflows/<id>/form_spec.json` — intake step form spec
- `backend/src/<pkg>/models/<id>.py` — SQLAlchemy 2.x model
- `backend/migrations/versions/<rev>_create_<table>.py` — Alembic migration
- `backend/src/<pkg>/adapters/<id>_adapter.py` — workflow adapter
- `backend/src/<pkg>/services/<id>_service.py` — domain service
- `backend/src/<pkg>/routers/<id>_router.py` — FastAPI router
- `backend/tests/<id>/test_simulation.py` — simulation pytest

Cross-bundle aggregations: `permissions.py`, `audit_taxonomy.py`, `notifications.py`, `migrations/env.py`, `alembic.ini`, `README.md`, `.env.example`. No LLM calls.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `FLOWFORGE_PROM_URL` | `http://prometheus.flowforge.local:9090` | Prometheus base URL for `audit-2026 health`. |

## Audit-2026 hardening

- **CL-01** (E-57): Stub generators are wired — `jtbd-generate` emits all 12+ files per the U19 spec rather than placeholder empty files.
- **CL-02** (E-57): `flowforge new` validates the target working directory before writing; a non-writable or already-populated directory surfaces a clear error rather than a partial scaffold.
- **CL-03** (E-57): Template files are loaded via `importlib.resources` rather than path-relative file reads, so the package works correctly when installed into a zipimport environment.
- **CL-04** (E-57): Generator exceptions are logged with full chained context before re-raise so the CLI output identifies which JTBD and which template caused the failure.
- **`flowforge pre-upgrade-check`**: New command implementing the F-7 mitigation for E-34 SK-01. Checks that `FLOWFORGE_SIGNING_SECRET` is set (or `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` for the bridge window). Exits non-zero on failure; safe to run as a CI/CD gate before framework version bumps.
- **`flowforge audit-2026 health`**: Per-fix release-health probes via Prometheus instant queries. Prints PASS/WARN/FAIL per audit ticket (E-32 through E-58). Supports `--json` for structured output and `--ticket <E-xx>` to restrict to one ticket. Exits non-zero if any required probe exceeds its threshold.

## Compatibility

- Python 3.11+
- `typer`
- `jinja2`
- `flowforge-jtbd` (for `jtbd lint` and `jtbd-generate` validation)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-jtbd`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-jtbd) — linter and canonical spec models consumed by this CLI
- [`flowforge-signing-kms`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-signing-kms) — `pre-upgrade-check signing` checks readiness for its SK-01 change
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
