# flowforge-jtbd-compliance

Enterprise compliance workflows covering KYC/CDD, AML alert investigation, SAR filing, internal audit, policy review, sanctions screening, compliance training, GDPR/CCPA data subject requests, regulatory examinations, and enterprise risk assessment.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| conduct_kyc_verification | Conduct KYC customer due diligence |
| investigate_aml_alert | Investigate AML transaction monitoring alert |
| file_suspicious_activity_report | File Suspicious Activity Report (SAR) |
| conduct_internal_audit | Conduct internal audit engagement |
| manage_policy_review_cycle | Manage compliance policy review and attestation |
| manage_sanctions_screening | Manage OFAC/sanctions screening and match review |
| manage_compliance_training | Manage mandatory compliance training campaign |
| manage_data_privacy_request | Manage data subject access or deletion request (GDPR/CCPA) |
| manage_regulatory_examination | Manage regulatory examination response |
| manage_risk_assessment | Conduct enterprise compliance risk assessment |

## Usage

```python
from flowforge_jtbd_compliance import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
uv run flowforge jtbd lint python/flowforge-jtbd-compliance/src/flowforge_jtbd_compliance/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain compliance
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
