# flowforge-jtbd-telco

Workflow definitions covering telecommunications carrier operations, including subscriber provisioning, churn retention, number porting, network outage response, billing disputes, roaming activation, device returns, regulatory submissions, wholesale settlement, and MVNO onboarding.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| provision_service | Provision a new subscriber service |
| manage_churn_risk | Manage a high-churn-risk subscriber |
| port_phone_number | Port a phone number to or from network |
| respond_to_outage | Respond to a network outage |
| resolve_billing_dispute | Resolve a subscriber billing dispute |
| activate_roaming | Activate international roaming for a subscriber |
| process_device_return | Process a device return and refund |
| prepare_regulatory_audit | Prepare for a regulatory audit submission |
| settle_wholesale_account | Settle a wholesale interconnect account |
| onboard_MVNO | Onboard a new MVNO partner |

## Usage

```python
from flowforge_jtbd_telco import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-telco/src/flowforge_jtbd_telco/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain telco
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
