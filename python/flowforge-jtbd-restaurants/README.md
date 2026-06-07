# flowforge-jtbd-restaurants

Workflow definitions covering restaurant and food-service operations, including supplier procurement, food safety incident response, staff scheduling, vendor payments, franchise audits, and menu governance.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| order_from_supplier | Order from a food supplier |
| manage_food_safety_incident | Manage a food safety incident |
| schedule_staff | Schedule restaurant staff |
| pay_vendor_invoice | Pay a vendor invoice |
| handle_customer_complaint | Handle a customer service complaint |
| audit_franchise | Conduct a franchise operations audit |
| prepare_health_inspection | Prepare for a health inspection |
| handle_allergen_incident | Handle an allergen incident |
| reduce_food_waste | Execute a food waste reduction review |
| approve_menu_change | Approve a menu change |

## Usage

```python
from flowforge_jtbd_restaurants import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-restaurants/src/flowforge_jtbd_restaurants/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain restaurants
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
