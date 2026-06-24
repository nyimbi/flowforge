# flowforge-jtbd-hr

**Strategic domain-content candidate** — HR industry Jobs-To-Be-Done bundle for the flowforge workflow framework.

Contains 30 fully-specified JTBD definitions covering the core operational workflows for HR organisations.

> **Authorship note**: JTBD definitions in this package are AI-authored and structured for review by HR domain SMEs before production use. Each JTBD carries citation anchors where regulatory or industry-standard sources apply.

## JTBDs (30)

| ID | Title | Primary Actor |
|----|-------|---------------|
| `onboard_employee` | Onboard a new employee | hr_admin |
| `process_resignation` | Process employee resignation and offboarding | hr_admin |
| `manage_performance_review` | Manage annual performance review cycle | hr_business_partner |
| `handle_leave_request` | Handle employee leave request (FMLA/ADA/PTO) | hr_admin |
| `process_promotion` | Process employee promotion | hr_business_partner |
| `manage_disciplinary_action` | Manage employee disciplinary action | hr_business_partner |
| `handle_harassment_complaint` | Handle workplace harassment complaint | employee_relations_specialist |
| `process_payroll_change` | Process payroll change request | payroll_specialist |
| `enroll_benefits` | Enroll employee in benefits | benefits_admin |
| `conduct_workforce_reduction` | Conduct workforce reduction (RIF) | hr_director |
| `manage_recruitment` | Manage full-cycle recruitment | recruiter |
| `process_i9_everify` | Complete I-9 and E-Verify for new hire | hr_coordinator |
| `manage_fmla_leave` | Manage FMLA leave | leave_administrator |
| `process_ada_accommodation` | Process ADA reasonable accommodation | hr_business_partner |
| `manage_compensation_review` | Manage annual compensation review cycle | compensation_analyst |
| `investigate_employee_complaint` | Investigate employee complaint | hr_business_partner |
| `manage_cobra_administration` | Administer COBRA continuation coverage | benefits_administrator |
| `process_separation_agreement` | Process separation agreement and release | hr_counsel |
| `manage_visa_sponsorship` | Manage employment visa sponsorship | immigration_coordinator |
| `manage_benefits_open_enrollment` | Manage annual benefits open enrollment | benefits_manager |
| `manage_union_grievance` | Manage union grievance | labor_relations_manager |
| `process_reduction_in_force_warn` | Issue WARN Act notice for mass layoff | hr_legal |
| `manage_eeo1_reporting` | Manage EEO-1 and AAP reporting | hr_compliance_analyst |
| `conduct_job_evaluation` | Conduct job evaluation and classification | compensation_analyst |
| `process_payroll_change_validation` | Validate and process payroll change request | payroll_specialist |
| `manage_executive_compensation` | Manage executive compensation program | head_of_total_rewards |
| `process_workers_comp_claim_hr` | Process workers compensation claim (HR) | hr_safety_specialist |
| `manage_talent_succession_planning` | Manage succession planning | talent_management_director |
| `manage_hr_system_implementation` | Manage HCM system implementation | hris_manager |
| `manage_performance_improvement_plan` | Manage performance improvement plan | hr_business_partner |

## Usage

```python
import json
from importlib.resources import files

bundle = json.loads(
    files("flowforge_jtbd_hr").joinpath("examples/bundle.json").read_text()
)

for jtbd in bundle["jtbds"]:
    print(jtbd["id"], "-", jtbd["title"])
```

## CLI

```bash
# Lint the bundle
uv run flowforge jtbd lint python/flowforge-jtbd-hr/src/flowforge_jtbd_hr/examples/bundle.json

# Generate scaffold for a specific JTBD
uv run flowforge jtbd-generate \
  --jtbd python/flowforge-jtbd-hr/src/flowforge_jtbd_hr/examples/bundle.json \
  --id <jtbd_id> \
  --out out/hr
```

## Status

`package = false` — registered in the uv workspace but not published to PyPI. Flip to `package = true` only after SME/content review passes gate E-48a/E-48b.
