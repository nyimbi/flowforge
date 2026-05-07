# flowforge

Portable workflow framework extracted from UMS. Source spec: `docs/workflow-framework-portability.md`. Build plan: `docs/workflow-framework-plan.md`.

This subtree is intentionally self-contained. Nothing under `framework/` imports from `backend/app/` or `frontend/src/` — UMS is a *consumer* of flowforge, not the other way around.

## Security & release notes

- **0.1.0 release** (audit-2026): closes 77 audit findings, includes one
  SECURITY-BREAKING change. Read [`docs/audit-2026/SECURITY-NOTE.md`][sec]
  before upgrading and run [`flowforge pre-upgrade-check`][cli] against
  every host. Upgrade checklist at [`docs/release/v0.1.0-upgrade.md`][upgrade].
- Per-fix signoff trail: [`docs/audit-2026/signoff-checklist.md`][signoff].
- Close-out report: [`docs/audit-2026/close-out.md`][closeout].
- Backlog of architecturally-deferred items: [`docs/audit-2026/backlog.md`][backlog].

[sec]: docs/audit-2026/SECURITY-NOTE.md
[cli]: python/flowforge-cli/src/flowforge_cli/commands/pre_upgrade_check.py
[upgrade]: docs/release/v0.1.0-upgrade.md
[signoff]: docs/audit-2026/signoff-checklist.md
[closeout]: docs/audit-2026/close-out.md
[backlog]: docs/audit-2026/backlog.md

## Layout

```
framework/
├── python/                  # 45 packages (uv workspace, 15 strategic + 30 domain libs)
│   │
│   │ # 15 strategic (ship today, package=true)
│   ├── flowforge-core/      # ports, DSL, engine, simulator
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
│   ├── flowforge-cli/
│   ├── flowforge-jtbd/      # JTBD core: spec, lockfile, storage, lint, AI
│   ├── flowforge-jtbd-hub/  # registry / mirroring / signing
│   │
│   │ # 30 domain JTBD libraries (package=false, two-step rebrand per E-46 / F-5)
│   ├── flowforge-jtbd-accounting/
│   ├── flowforge-jtbd-agritech/
│   ├── flowforge-jtbd-banking/         # S2b real-content (sme-banking)
│   ├── flowforge-jtbd-compliance/
│   ├── flowforge-jtbd-construction/
│   ├── flowforge-jtbd-corp-finance/
│   ├── flowforge-jtbd-crm/
│   ├── flowforge-jtbd-ecom/
│   ├── flowforge-jtbd-edu/
│   ├── flowforge-jtbd-gaming/
│   ├── flowforge-jtbd-gov/             # S2b real-content (sme-gov)
│   ├── flowforge-jtbd-healthcare/      # S2b real-content (sme-healthcare)
│   ├── flowforge-jtbd-hr/              # S2b real-content (sme-hr)
│   ├── flowforge-jtbd-insurance/       # S2b real-content (sme-insurance)
│   ├── flowforge-jtbd-legal/
│   ├── flowforge-jtbd-logistics/
│   ├── flowforge-jtbd-media/
│   ├── flowforge-jtbd-mfg/
│   ├── flowforge-jtbd-municipal/
│   ├── flowforge-jtbd-nonprofit/
│   ├── flowforge-jtbd-platformeng/
│   ├── flowforge-jtbd-pm/
│   ├── flowforge-jtbd-procurement/
│   ├── flowforge-jtbd-realestate/
│   ├── flowforge-jtbd-restaurants/
│   ├── flowforge-jtbd-retail/
│   ├── flowforge-jtbd-saasops/
│   ├── flowforge-jtbd-telco/
│   ├── flowforge-jtbd-travel/
│   └── flowforge-jtbd-utilities/
├── js/                      # 5 npm packages (pnpm workspace)
│   ├── flowforge-types/
│   ├── flowforge-renderer/
│   ├── flowforge-runtime-client/
│   ├── flowforge-step-adapters/
│   └── flowforge-designer/
├── examples/                # JTBD worked examples (claim, hiring, permit)
├── migration/               # UMS-as-host migration tooling
├── tests/                   # cross-package suites
│   ├── audit_2026/          # audit-fix-plan acceptance regressions
│   ├── conformance/         # arch §17 invariants 1–8
│   ├── property/            # hypothesis property tests
│   ├── chaos/               # crash-mid-fire, mid-outbox, mid-compensation
│   ├── cross_runtime/       # TS↔Python evaluator parity fixture
│   └── integration/         # e2e and per-package
└── scripts/                 # check_workspace.py, check_all.sh
```

### Workspace registration policy (E-46 / F-5)

The 30 domain JTBD libraries are registered in `[tool.uv.workspace]` with
`[tool.uv] package = false` per pkg, so `uv build` discovers them but
doesn't produce wheels for them yet. They flip to `package = true` per
package as they pass:

- **E-48a** — rebrand to `flowforge-jtbd-*-starter` with scaffold-only
  classifier (25 non-strategic verticals).
- **E-48b** — real JTBD content reviewed by named domain SMEs (5
  strategic verticals: insurance, healthcare, banking, gov, hr).

## Status

In active build. Not yet published. Path-dependency only.

## License

Apache-2.0 (planned, dual-license commercial track per portability §11 R14).
