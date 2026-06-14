# flowforge-jtbd-healthcare

**Tier-A** domain library — Healthcare industry Jobs-To-Be-Done bundle for the flowforge workflow framework.

Contains 30 fully-specified JTBD definitions covering the core operational workflows for Healthcare organisations.

> **Authorship note**: JTBD definitions in this package are AI-authored and structured for review by Healthcare domain SMEs before production use. Each JTBD carries citation anchors where regulatory or industry-standard sources apply.

## JTBDs (30)

| ID | Title | Primary Actor |
|----|-------|---------------|
| `admit_patient` | Admit a patient for inpatient care | admissions_coordinator |
| `schedule_appointment` | Schedule a patient appointment | admissions_coordinator |
| `process_prior_authorization` | Process prior authorization request | prior_auth_specialist |
| `submit_insurance_claim` | Submit and follow up on insurance claim | billing_specialist |
| `manage_referral` | Manage specialist referral | referral_coordinator |
| `handle_discharge` | Coordinate patient discharge | case_manager |
| `process_prescription` | Process and verify prescription | pharmacist |
| `enroll_clinical_trial` | Enroll patient in clinical trial | research_coordinator |
| `handle_incident_report` | Handle patient safety incident report | risk_manager |
| `request_medical_record` | Process medical record request | health_information_manager |
| `credential_provider` | Credential and privilege a clinical provider | medical_staff_coordinator |
| `process_denial_appeal` | Appeal insurance claim denial | billing_specialist |
| `manage_bed_capacity` | Manage inpatient bed capacity | bed_coordinator |
| `conduct_utilization_review` | Conduct concurrent utilization review | case_manager |
| `manage_medication_reconciliation` | Manage medication reconciliation at transitions of care | pharmacist |
| `manage_infection_control_outbreak` | Manage infectious disease outbreak response | infection_preventionist |
| `conduct_peer_review` | Conduct clinical peer review | peer_review_committee |
| `manage_value_based_care_performance` | Manage value-based care contract performance | quality_director |
| `process_organ_donation` | Process organ donation authorization | organ_donation_coordinator |
| `manage_telehealth_encounter` | Manage telehealth visit | care_coordinator |
| `handle_adverse_event_reporting` | Handle adverse event reporting (AHRQ PSO) | patient_safety_officer |
| `manage_population_health_gaps` | Manage population health care gaps | population_health_analyst |
| `process_home_health_authorization` | Process home health authorization and start of care | home_health_coordinator |
| `manage_dme_order` | Manage durable medical equipment order | dme_coordinator |
| `conduct_chart_audit` | Conduct clinical documentation improvement audit | cdi_specialist |
| `process_pharmacy_benefit_prior_auth` | Process pharmacy benefit prior authorization | prior_auth_pharmacist |
| `manage_outpatient_surgery_scheduling` | Manage outpatient surgery scheduling and pre-op | surgical_scheduler |
| `handle_patient_grievance` | Handle patient grievance | patient_relations_specialist |
| `process_340b_purchase` | Process 340B drug program purchase | 340b_program_coordinator |
| `process_advance_directive` | Process advance directive and POLST | social_worker |

## Usage

```python
import json
from importlib.resources import files

bundle = json.loads(
    files("flowforge_jtbd_healthcare.examples").joinpath("bundle.json").read_text()
)

for jtbd in bundle["jtbds"]:
    print(jtbd["id"], "-", jtbd["title"])
```

## CLI

```bash
# Lint the bundle
uv run flowforge jtbd lint python/flowforge-jtbd-healthcare/src/flowforge_jtbd_healthcare/examples/bundle.json

# Generate scaffold for a specific JTBD
uv run flowforge jtbd-generate \
  --jtbd python/flowforge-jtbd-healthcare/src/flowforge_jtbd_healthcare/examples/bundle.json \
  --id <jtbd_id> \
  --out out/healthcare
```

## Status

`package = false` — registered in the uv workspace but not published to PyPI. Flip to `package = true` after Tier-A SME sign-off (gate E-48a/E-48b).
