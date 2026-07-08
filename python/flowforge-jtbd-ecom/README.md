# flowforge-jtbd-ecom

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

E-commerce platform workflows covering order processing, returns, product catalog management, refunds, chargeback disputes, inventory replenishment, fraud review, delivery exception handling, marketplace seller onboarding, and subscription renewals.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| process_order | Process a customer order |
| handle_return | Handle a customer return |
| manage_catalog | Manage product catalog entry |
| process_refund | Process a customer refund |
| handle_chargeback | Handle a payment chargeback |
| replenish_inventory | Replenish inventory |
| review_fraud | Review a suspected fraudulent order |
| handle_delivery_exception | Handle a delivery exception |
| onboard_seller | Onboard a marketplace seller |
| renew_subscription | Process a subscription renewal |

## Usage

```python
from flowforge_jtbd_ecom import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-ecom/src/flowforge_jtbd_ecom/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain ecom
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
