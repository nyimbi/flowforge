# flowforge-jtbd-edu

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Higher education administrative workflows covering student admissions, financial aid, grade appeals, course registration, academic misconduct investigations, disability accommodations, transcript requests, faculty hiring, research compliance review, and graduation audits.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| process_admissions | Process a student admission application |
| manage_financial_aid | Manage a financial aid award |
| handle_grade_appeal | Handle a student grade appeal |
| register_course | Register a student for a course |
| investigate_misconduct | Investigate academic misconduct |
| process_accommodation | Process a disability accommodation request |
| request_transcript | Process a transcript request |
| hire_faculty | Hire a faculty member |
| review_research_compliance | Review research compliance (IRB/IACUC) |
| audit_graduation | Audit a student for graduation |

## Usage

```python
from flowforge_jtbd_edu import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-edu/src/flowforge_jtbd_edu/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain edu
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
