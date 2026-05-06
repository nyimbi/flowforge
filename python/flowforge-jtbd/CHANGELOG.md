# flowforge-jtbd changelog

## 0.1.0 — Unreleased

- E-4: linter core.
  - Lint-facing spec models (`JtbdLintSpec`, `JtbdBundle`, `ActorRef`,
    `RoleDef`, `StageDecl`).
  - `LifecycleAnalyzer` — completeness analysis against required stages
    with delegation via `audit_handled_by`.
  - `DependencyGraph` — Tarjan SCC cycle detection + Kahn topological
    order.
  - `ActorConsistencyAnalyzer` — capacity-conflict warning, tier
    authority error.
  - `JtbdRule` / `JtbdRulePack` protocols + `RuleRegistry`.
  - `Linter` orchestrator + `LintReport` output format.
