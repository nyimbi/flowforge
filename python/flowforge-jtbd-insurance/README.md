# flowforge-jtbd-insurance

**Strategic domain-content candidate** — Insurance industry Jobs-To-Be-Done bundle for the flowforge workflow framework.

Contains 30 fully-specified JTBD definitions covering the core operational workflows for Insurance organisations.

> **Authorship note**: JTBD definitions in this package are AI-authored and structured for review by Insurance domain SMEs before production use. Each JTBD carries citation anchors where regulatory or industry-standard sources apply.

## JTBDs (30)

| ID | Title | Primary Actor |
|----|-------|---------------|
| `process_claim` | Process an insurance claim end-to-end | claims_adjuster |
| `underwrite_policy` | Underwrite a new insurance policy | underwriter |
| `handle_reinsurance` | Place facultative reinsurance cession | reinsurance_analyst |
| `manage_renewal` | Manage policy renewal underwriting | underwriter |
| `detect_fraud` | Investigate suspected claim fraud | siu_investigator |
| `process_subrogation` | Pursue subrogation recovery | subrogation_specialist |
| `handle_litigation` | Manage claim litigation | litigation_manager |
| `file_regulatory_report` | File regulatory compliance report | compliance_officer |
| `process_premium_payment` | Process premium payment and reconcile | finance_controller |
| `audit_claims_reserve` | Audit and certify claims reserve adequacy | actuarial_analyst |
| `issue_policy` | Issue a new policy | policy_issuance_specialist |
| `manage_endorsement` | Process mid-term policy endorsement | underwriter |
| `cancel_policy` | Cancel or non-renew a policy | underwriter |
| `conduct_actuarial_reserve_review` | Conduct quarterly actuarial reserve review | actuary |
| `manage_broker_appointment` | Manage producer/broker appointment | distribution_manager |
| `handle_salvage_recovery` | Handle salvage and recovery | salvage_coordinator |
| `process_catastrophe_event` | Process CAT event response | cat_manager |
| `file_rate_filing` | File rate revision with state DOI | pricing_actuary |
| `manage_captive_program` | Manage captive insurance program | risk_manager |
| `conduct_siu_investigation` | Conduct SIU investigation | siu_investigator |
| `manage_excess_surplus_placement` | Place E&S market coverage | wholesale_broker |
| `process_life_claim` | Process life insurance death claim | life_claims_examiner |
| `issue_certificate_of_insurance` | Issue Certificate of Insurance | account_manager |
| `manage_treaty_reinsurance_settlement` | Settle treaty reinsurance bordereau | reinsurance_accountant |
| `handle_workers_comp_claim` | Handle workers compensation claim | wc_adjuster |
| `conduct_premium_audit` | Conduct annual premium audit | premium_auditor |
| `manage_cyber_incident_response` | Manage cyber insurance incident response | cyber_claims_manager |
| `process_medical_malpractice_claim` | Process medical malpractice claim | malpractice_adjuster |
| `manage_loss_control_survey` | Conduct loss control survey | loss_control_consultant |
| `manage_subrogation_recovery_litigation` | Manage subrogation recovery litigation | subrogation_attorney |

## Usage

```python
import json
from importlib.resources import files

bundle = json.loads(
    files("flowforge_jtbd_insurance").joinpath("examples/bundle.json").read_text()
)

for jtbd in bundle["jtbds"]:
    print(jtbd["id"], "-", jtbd["title"])
```

## CLI

```bash
# Lint the bundle
uv run flowforge jtbd lint python/flowforge-jtbd-insurance/src/flowforge_jtbd_insurance/examples/bundle.json

# Generate scaffold for a specific JTBD
uv run flowforge jtbd-generate \
  --jtbd python/flowforge-jtbd-insurance/src/flowforge_jtbd_insurance/examples/bundle.json \
  --id <jtbd_id> \
  --out out/insurance
```

## Status

`package = false` — registered in the uv workspace but not published to PyPI. Flip to `package = true` only after SME/content review passes gate E-48a/E-48b.
