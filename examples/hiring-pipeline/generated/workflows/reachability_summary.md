# Reachability summary

Bundle: `hiring_pipeline`

`z3-solver` is installed; per-JTBD reports live at `workflows/<id>/reachability.json`.

| JTBD | Title | Status | Total | Reachable | Unreachable | Unwritable vars | Artefact |
|------|-------|--------|-------|-----------|-------------|-----------------|----------|
| `complete_hire` | Complete hire and onboard | ok | 3 | 3 | 0 | 0 | `workflows/complete_hire/reachability.json` |
| `conduct_interview` | Conduct interview loop | warn | 3 | 3 | 0 | 1 | `workflows/conduct_interview/reachability.json` |
| `extend_offer` | Extend an offer | warn | 6 | 6 | 0 | 1 | `workflows/extend_offer/reachability.json` |
| `screen_candidate` | Screen a candidate | warn | 3 | 3 | 0 | 1 | `workflows/screen_candidate/reachability.json` |
| `source_candidate` | Source a candidate | ok | 3 | 3 | 0 | 0 | `workflows/source_candidate/reachability.json` |

