# flowforge-jtbd-banking

**Tier-A** domain library — Banking industry Jobs-To-Be-Done bundle for the flowforge workflow framework.

Contains 30 fully-specified JTBD definitions covering the core operational workflows for Banking organisations.

> **Authorship note**: JTBD definitions in this package are AI-authored and structured for review by Banking domain SMEs before production use. Each JTBD carries citation anchors where regulatory or industry-standard sources apply.

## JTBDs (30)

| ID | Title | Primary Actor |
|----|-------|---------------|
| `originate_loan` | Originate a commercial or consumer loan | loan_officer |
| `process_wire_transfer` | Process and authorize wire transfer | operations_specialist |
| `onboard_business_customer` | Onboard a business banking customer (KYB/KYC) | kyc_analyst |
| `handle_dispute` | Handle customer payment dispute | dispute_analyst |
| `manage_overdraft` | Manage overdraft authorization and fee assessment | operations_specialist |
| `close_account` | Process account closure | operations_specialist |
| `handle_AML_alert` | Investigate AML transaction monitoring alert | aml_analyst |
| `originate_trade_finance` | Originate trade finance transaction (LC/BG) | trade_finance_specialist |
| `settle_treasury` | Settle treasury/investment security transaction | treasury_analyst |
| `file_SAR` | File Suspicious Activity Report (SAR) | bsa_officer |
| `process_mortgage_origination` | Originate residential mortgage loan | mortgage_loan_officer |
| `manage_credit_facility_review` | Conduct annual credit facility review | credit_analyst |
| `process_check_fraud_claim` | Process check fraud claim | fraud_operations_specialist |
| `onboard_retail_customer` | Onboard retail deposit customer | personal_banker |
| `manage_collateral_perfection` | Perfect and manage loan collateral | loan_operations_specialist |
| `process_ACH_exception` | Process ACH return and exception | ach_operations_specialist |
| `conduct_BSA_CDD_review` | Conduct BSA Customer Due Diligence review | bsa_analyst |
| `process_international_payment` | Process cross-border payment (SWIFT/SEPA) | international_payments_specialist |
| `manage_regulatory_exam_response` | Manage regulatory examination response | compliance_director |
| `process_letter_of_credit` | Issue and manage commercial letter of credit | trade_finance_specialist |
| `manage_interest_rate_risk` | Manage interest rate risk (IRRBB) | treasurer |
| `handle_deceased_customer_estate` | Handle deceased customer estate settlement | estate_services_specialist |
| `conduct_fair_lending_review` | Conduct fair lending self-assessment | fair_lending_analyst |
| `process_SBA_loan` | Process SBA-guaranteed loan | sba_loan_officer |
| `manage_dormant_account_escheatment` | Manage dormant account and unclaimed property | unclaimed_property_coordinator |
| `process_loan_modification` | Process loan modification or forbearance | loss_mitigation_specialist |
| `manage_operational_risk_event` | Manage operational risk loss event | operational_risk_manager |
| `conduct_stress_test_reporting` | Conduct regulatory stress test (DFAST/CCAR) | capital_planning_analyst |
| `manage_credit_card_issuance` | Issue and manage credit card account | card_operations_specialist |
| `manage_LIBOR_SOFR_transition` | Manage LIBOR-to-SOFR loan transition | loan_operations_manager |

## Usage

```python
import json
from importlib.resources import files

bundle = json.loads(
    files("flowforge_jtbd_banking").joinpath("examples/bundle.json").read_text()
)

for jtbd in bundle["jtbds"]:
    print(jtbd["id"], "-", jtbd["title"])
```

## CLI

```bash
# Lint the bundle
uv run flowforge jtbd lint python/flowforge-jtbd-banking/src/flowforge_jtbd_banking/examples/bundle.json

# Generate scaffold for a specific JTBD
uv run flowforge jtbd-generate \
  --jtbd python/flowforge-jtbd-banking/src/flowforge_jtbd_banking/examples/bundle.json \
  --id <jtbd_id> \
  --out out/banking
```

## Status

`package = false` — registered in the uv workspace but not published to PyPI. Flip to `package = true` after Tier-A SME sign-off (gate E-48a/E-48b).
