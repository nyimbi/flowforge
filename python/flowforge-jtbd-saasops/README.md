# flowforge-jtbd-saasops

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Workflow definitions covering SaaS platform operations, including tenant provisioning, incident management, customer offboarding, usage billing, compliance requests, feature flag rollouts, security reviews, DSARs, SLA breach handling, and contract renewals.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| onboard_tenant | Onboard a new tenant |
| manage_incident | Manage a platform incident |
| offboard_customer | Offboard a departing customer |
| process_usage_billing | Process monthly usage billing |
| handle_compliance_request | Handle a customer compliance request |
| roll_out_feature_flag | Roll out a feature flag to production |
| conduct_security_review | Conduct quarterly security review |
| export_customer_data | Export customer data on request (DSAR) |
| manage_SLA_breach | Manage an SLA breach event |
| renew_contract | Renew a customer contract |

## Usage

```python
from flowforge_jtbd_saasops import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-saasops/src/flowforge_jtbd_saasops/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain saasops
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
