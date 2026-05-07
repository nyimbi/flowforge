# Audit 2026 — Intentionally-deferred backlog

Per audit-fix-plan.md §11 and CR-12, this section is **EMPTY by spec** ("zero deferrals, including P3 cosmetic").

If items surface during execution that warrant deferral, they MUST:
- Be added here with explicit rationale.
- Be re-approved by architect agent before deferral.
- Get a successor ticket E-73+ assigned.
- Trigger a CHANGELOG entry indicating audit-2026 incomplete.

---

## Documented architectural deferrals (planning-time)

### JH-04 full RBAC implementation

**Status**: Split — basic improvement (rotation + audit log) delivered in E-58 (P2). Full per-user RBAC deferred.

**Rationale**: Net-new feature, not a defect fix. Existing single-token mechanism is documented + rotation supported via E-58. Replacing with full RBAC is a feature-track item, not an audit-fix item.

**Successor ticket**: E-73 (post-1.0).

**Re-approval**: Architect signoff at S0 (per architect review §3 V-1, §4.3).

---

*No other deferrals. Update this file via PR with architect signoff if any item is added during execution.*
