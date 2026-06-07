# flowforge-jtbd-retail

Workflow definitions covering brick-and-mortar and omnichannel retail operations, including trade-ins, clienteling, loyalty enrolment, returns, stock replenishment, price adjustments, staff training, vendor markdowns, shrinkage investigations, and store audits.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| process_buyback | Process a trade-in / buyback |
| manage_clienteling_session | Manage a clienteling session |
| enroll_loyalty | Enrol a customer in the loyalty programme |
| process_return | Process a customer return |
| replenish_stock | Replenish store stock |
| apply_price_adjustment | Apply a price adjustment |
| deliver_staff_training | Deliver staff compliance training |
| negotiate_vendor_markdown | Negotiate a vendor markdown |
| investigate_shrinkage | Investigate inventory shrinkage |
| conduct_store_audit | Conduct a store operations audit |

## Usage

```python
from flowforge_jtbd_retail import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-retail/src/flowforge_jtbd_retail/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain retail
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
