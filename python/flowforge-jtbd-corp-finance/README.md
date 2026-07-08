# flowforge-jtbd-corp-finance

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Corporate finance workflows covering capital expenditure approval, treasury forecasting, FX hedging, dividend declaration, debt covenant monitoring, M&A due diligence, board approvals, audit committee responses, investor relations, and transfer pricing.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| approve_capex | Approve a capital expenditure request |
| forecast_treasury | Produce monthly treasury forecast |
| execute_FX_hedge | Execute a foreign exchange hedge |
| declare_dividend | Declare and pay a shareholder dividend |
| monitor_debt_covenant | Monitor and certify debt covenant compliance |
| conduct_acquisition_DD | Conduct financial due diligence on an acquisition target |
| get_board_approval | Obtain board approval for a material transaction |
| respond_to_audit_committee | Respond to an audit committee finding |
| handle_investor_inquiry | Handle an investor or analyst inquiry |
| review_transfer_pricing | Conduct annual transfer pricing review |

## Usage

```python
from flowforge_jtbd_corp_finance import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-corp-finance/src/flowforge_jtbd_corp_finance/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain corp-finance
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
