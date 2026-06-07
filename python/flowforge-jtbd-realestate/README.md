# flowforge-jtbd-realestate

Workflow definitions covering residential real estate transactions, from MLS listing through escrow closing, plus residential property management operations.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| list_property | List a property for sale |
| review_offer | Review and respond to a purchase offer |
| open_escrow | Open escrow |
| conduct_title_search | Conduct a title search and issue preliminary report |
| schedule_inspection | Schedule and complete a property inspection |
| manage_financing_contingency | Manage the financing contingency |
| coordinate_closing | Coordinate and execute the closing |
| process_lease_renewal | Process a lease renewal |
| handle_maintenance_request | Handle a tenant maintenance request |
| resolve_tenant_dispute | Resolve a tenant dispute |

## Usage

```python
from flowforge_jtbd_realestate import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-realestate/src/flowforge_jtbd_realestate/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain realestate
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
