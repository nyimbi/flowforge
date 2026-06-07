# flowforge-jtbd-crm

Customer relationship management workflows covering lead qualification, opportunity management, account onboarding, contract renewal, escalation handling, complaint resolution, upsell/cross-sell, quarterly reviews, churn risk management, and partner deal registration.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| qualify_lead | Qualify a lead |
| manage_opportunity | Manage a sales opportunity |
| onboard_account | Onboard a new account |
| process_renewal | Process a contract renewal |
| handle_escalation | Handle a customer escalation |
| log_complaint | Log and resolve a customer complaint |
| process_upsell | Process an upsell or cross-sell |
| review_account | Conduct quarterly account review |
| manage_churn_risk | Manage a churn-risk account |
| register_partner_deal | Register a partner deal |

## Usage

```python
from flowforge_jtbd_crm import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-crm/src/flowforge_jtbd_crm/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain crm
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
