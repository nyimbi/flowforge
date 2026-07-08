# flowforge-jtbd-gov

**Status: strategic domain content candidate. Package state: workspace-only; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48b review flips `package = true`.**

**Strategic domain-content candidate** — Gov industry Jobs-To-Be-Done bundle for the flowforge workflow framework.

Contains 30 fully-specified JTBD definitions covering the core operational workflows for Gov organisations.

> **Authorship note**: JTBD definitions in this package are AI-authored and structured for review by Gov domain SMEs before production use. Each JTBD carries citation anchors where regulatory or industry-standard sources apply.

## JTBDs (30)

| ID | Title | Primary Actor |
|----|-------|---------------|
| `process_permit` | Process building or land-use permit application | permit_technician |
| `renew_license` | Renew a professional or business license | licensing_officer |
| `manage_public_comment` | Manage public comment period | public_information_officer |
| `process_benefits_claim` | Process public benefits claim | benefits_examiner |
| `handle_FOIA_request` | Handle Freedom of Information Act request | foia_officer |
| `manage_procurement_bid` | Manage competitive procurement bid | procurement_officer |
| `process_tax_appeal` | Process property tax assessment appeal | appeals_officer |
| `handle_code_violation` | Handle municipal code violation | code_inspector |
| `manage_public_hearing` | Manage public hearing | hearing_officer |
| `process_grant_application` | Process grant application | grants_manager |
| `process_business_registration` | Register a new business entity | business_registration_clerk |
| `manage_environmental_permit` | Issue and manage environmental permit | environmental_permit_officer |
| `process_court_filing` | Process court filing and docket management | court_clerk |
| `manage_public_safety_incident` | Manage public safety incident (emergency response) | emergency_management_coordinator |
| `administer_public_assistance_program` | Administer public assistance program enrollment | benefits_eligibility_worker |
| `manage_property_tax_assessment` | Manage property tax assessment cycle | county_assessor |
| `process_planning_zone_change` | Process zoning change or variance application | planning_officer |
| `manage_federal_grant_compliance` | Manage federal grant compliance and reporting | grants_compliance_officer |
| `issue_professional_license` | Issue professional license | licensing_board_examiner |
| `manage_procurement_contract` | Manage procurement contract administration | contracting_officer |
| `process_election_voter_registration` | Process voter registration | elections_clerk |
| `manage_public_works_project` | Manage public works capital project | public_works_project_manager |
| `handle_administrative_appeal` | Handle administrative appeal hearing | administrative_law_judge |
| `conduct_government_audit` | Conduct government performance audit | government_auditor |
| `manage_cybersecurity_incident_gov` | Manage government cybersecurity incident (FISMA/CISA) | government_ciso |
| `process_public_contracting_dispute` | Process procurement protest or contract dispute | contracting_officer |
| `manage_social_services_case` | Manage social services case | social_services_case_worker |
| `process_tax_lien_collection` | Process tax lien and delinquent collection | tax_collector |
| `manage_regulatory_rulemaking` | Manage regulatory rulemaking (APA notice-and-comment) | regulatory_policy_officer |
| `process_foia_request` | Process Freedom of Information Act request | foia_coordinator |

## Usage

```python
import json
from importlib.resources import files

bundle = json.loads(
    files("flowforge_jtbd_gov").joinpath("examples/bundle.json").read_text()
)

for jtbd in bundle["jtbds"]:
    print(jtbd["id"], "-", jtbd["title"])
```

## CLI

```bash
# Lint the bundle
uv run flowforge jtbd lint python/flowforge-jtbd-gov/src/flowforge_jtbd_gov/examples/bundle.json

# Generate scaffold for a specific JTBD
uv run flowforge jtbd-generate \
  --jtbd python/flowforge-jtbd-gov/src/flowforge_jtbd_gov/examples/bundle.json \
  --id <jtbd_id> \
  --out out/gov
```

## Status

`package = false` — registered in the uv workspace but not published to PyPI. Flip to `package = true` only after SME/content review passes gate E-48a/E-48b.
