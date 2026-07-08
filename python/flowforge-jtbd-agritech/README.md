# flowforge-jtbd-agritech

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Agricultural operations workflows covering crop cycle planning, harvest coordination, pest response, irrigation scheduling, input procurement, certification audits, subsidy claims, equipment repair, and sustainability reporting.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| plan_crop_cycle | Plan the seasonal crop cycle |
| report_yield | Report post-harvest yield |
| respond_to_pest | Respond to a pest or disease detection |
| schedule_irrigation | Schedule and execute an irrigation run |
| procure_inputs | Procure season inputs (seed, fertiliser, agrichemicals) |
| coordinate_harvest | Coordinate the harvest operation |
| prepare_certification_audit | Prepare for a third-party certification audit |
| claim_subsidy | Submit a government subsidy claim |
| repair_equipment | Manage a machinery repair or service event |
| file_sustainability_report | File the annual sustainability and carbon report |

## Usage

```python
from flowforge_jtbd_agritech import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-agritech/src/flowforge_jtbd_agritech/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain agritech
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
