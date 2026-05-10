# Reachability summary

Bundle: `building_permit`

`z3-solver` is installed; per-JTBD reports live at `workflows/<id>/reachability.json`.

| JTBD | Title | Status | Total | Reachable | Unreachable | Unwritable vars | Artefact |
|------|-------|--------|-------|-----------|-------------|-----------------|----------|
| `field_inspection` | Conduct Field Inspection | ok | 5 | 5 | 0 | 0 | `workflows/field_inspection/reachability.json` |
| `permit_decision` | Approve or Deny Building Permit | ok | 3 | 3 | 0 | 0 | `workflows/permit_decision/reachability.json` |
| `permit_intake` | Submit a Building Permit Application | ok | 2 | 2 | 0 | 0 | `workflows/permit_intake/reachability.json` |
| `permit_issuance` | Issue the Building Permit Certificate | ok | 2 | 2 | 0 | 0 | `workflows/permit_issuance/reachability.json` |
| `plan_review` | Review Building Plans for Code Compliance | warn | 4 | 4 | 0 | 1 | `workflows/plan_review/reachability.json` |

