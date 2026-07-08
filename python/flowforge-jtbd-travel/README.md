# flowforge-jtbd-travel

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Workflow definitions covering travel and hospitality operations, including booking processing, cancellations, itinerary changes, loyalty redemptions, overbooking management, refund claims, group bookings, special assistance, visa documentation, and travel insurance claims.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| process_booking | Process a travel booking |
| handle_cancellation | Handle a booking cancellation |
| manage_itinerary_change | Manage an itinerary change |
| redeem_loyalty | Redeem loyalty points |
| manage_overbooking | Manage an overbooking situation |
| process_refund_claim | Process a refund claim |
| create_group_booking | Create a group booking |
| arrange_special_assistance | Arrange special assistance for a traveller |
| collect_visa_docs | Collect visa and travel document requirements |
| process_insurance_claim | Process a travel insurance claim |

## Usage

```python
from flowforge_jtbd_travel import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-travel/src/flowforge_jtbd_travel/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain travel
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
