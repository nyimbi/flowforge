# flowforge-jtbd-utilities

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Workflow definitions covering electric, gas, and water utility operations, including meter reading, outage response, new service connections, billing disputes, safety incident investigations, regulatory filings, construction permitting, service relocations, renewable energy credit tracking, and demand response execution.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| read_meter | Record a meter reading |
| respond_to_outage | Respond to a service outage |
| connect_service | Connect a new service to the grid |
| resolve_billing_dispute | Resolve a customer billing dispute |
| investigate_safety_incident | Investigate a field safety incident |
| file_regulatory_report | File a mandatory regulatory report |
| obtain_permit | Obtain a construction or excavation permit |
| process_service_relocation | Process a service relocation request |
| track_renewable_credits | Track and retire renewable energy credits |
| execute_demand_response | Execute a demand response event |

## Usage

```python
from flowforge_jtbd_utilities import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-utilities/src/flowforge_jtbd_utilities/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain utilities
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
