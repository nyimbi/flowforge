# flowforge-jtbd-construction

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Construction project lifecycle workflows covering bid submission, subcontractor onboarding, change orders, regulatory inspections, materials procurement, safety incident reporting, lien waivers, punch list closeout, warranty claims, and final project close-out.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| submit_bid | Submit a construction bid |
| onboard_subcontractor | Onboard a new subcontractor |
| process_change_order | Process a contract change order |
| schedule_inspection | Schedule and pass a regulatory inspection |
| procure_materials | Procure bulk construction materials |
| report_safety_incident | Report and investigate a safety incident |
| release_lien_waiver | Issue and collect lien waivers |
| manage_punch_list | Manage the project punch list to substantial completion |
| handle_warranty_claim | Handle a post-completion warranty claim |
| close_out_project | Complete project close-out |

## Usage

```python
from flowforge_jtbd_construction import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-construction/src/flowforge_jtbd_construction/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain construction
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
