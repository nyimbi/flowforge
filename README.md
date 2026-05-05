# flowforge

Portable workflow framework extracted from UMS. Source spec: `docs/workflow-framework-portability.md`. Build plan: `docs/workflow-framework-plan.md`.

This subtree is intentionally self-contained. Nothing under `framework/` imports from `backend/app/` or `frontend/src/` — UMS is a *consumer* of flowforge, not the other way around.

## Layout

```
framework/
├── python/                # 12 PyPI packages (uv workspace)
│   ├── flowforge-core/    # ports, DSL, engine, simulator
│   ├── flowforge-fastapi/
│   ├── flowforge-sqlalchemy/
│   ├── flowforge-tenancy/
│   ├── flowforge-audit-pg/
│   ├── flowforge-outbox-pg/
│   ├── flowforge-rbac-static/
│   ├── flowforge-rbac-spicedb/
│   ├── flowforge-documents-s3/
│   ├── flowforge-money/
│   ├── flowforge-signing-kms/
│   ├── flowforge-notify-multichannel/
│   └── flowforge-cli/
├── js/                    # 5 npm packages (pnpm workspace)
│   ├── flowforge-types/
│   ├── flowforge-renderer/
│   ├── flowforge-runtime-client/
│   ├── flowforge-step-adapters/
│   └── flowforge-designer/
├── examples/              # JTBD worked examples (claim, hiring, permit)
├── migration/             # UMS-as-host migration tooling
└── scripts/               # check_workspace.py, check_all.sh
```

## Status

In active build. Not yet published. Path-dependency only.

## License

Apache-2.0 (planned, dual-license commercial track per portability §11 R14).
