# flowforge-jtbd-healthcare

Status: strategic domain content candidate

Package state: workspace-only (`[tool.uv] package = false`)

Support level: not publishable, not SME-reviewed, and not part of the
critical-system support matrix until named healthcare SME signoff, release
review, and `package = true` are completed.

Starter? No. This package carries domain-specific JTBD content for healthcare
workflows, but it is not a release artifact yet.

## Contents

This package includes healthcare JTBD content for discharge planning, lab result
review, patient admission, prescription renewal, and referral requests.

The public entrypoint is `flowforge_jtbd_healthcare.load_bundle()`, which loads
the example bundle from `src/flowforge_jtbd_healthcare/examples/bundle.yaml`.

Do not use this package in release marketing, platform support matrices, or
regulated production implementation claims until it has explicit SME approval,
publishable packaging, and critical-system verification evidence.
