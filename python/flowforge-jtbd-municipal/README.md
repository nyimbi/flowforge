# flowforge-jtbd-municipal

Municipal government workflows covering permitting, code enforcement, business licensing, public works, zoning, parks, and utility connections for city and county operations.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| process_building_permit | Process building permit application |
| handle_code_violation | Investigate and resolve municipal code violation |
| process_business_license | Issue or renew business license |
| manage_public_works_service_order | Manage public works service order |
| process_encroachment_permit | Process encroachment permit |
| manage_zoning_variance | Process zoning variance or conditional use permit |
| process_parks_facility_reservation | Process parks facility reservation |
| manage_city_contract | Manage city procurement and contract award |
| process_special_event_permit | Issue special event permit |
| manage_public_utility_connection | Manage utility connection and service order |

## Usage

```python
from flowforge_jtbd_municipal import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-municipal/src/flowforge_jtbd_municipal/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain municipal
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
