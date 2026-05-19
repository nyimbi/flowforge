# flowforge-jtbd-hr

Status: strategic domain content candidate

Package state: workspace-only (`[tool.uv] package = false`)

Support level: not publishable, not SME-reviewed, and not part of the
critical-system support matrix until named HR SME signoff, release review, and
`package = true` are completed.

Starter? No. This package carries domain-specific JTBD content for HR workflows,
but it is not a release artifact yet.

## Contents

This package includes HR JTBD content for benefits open enrollment, intermittent
leave requests, new-hire onboarding, performance review, and termination
offboarding.

The public entrypoint is `flowforge_jtbd_hr.load_bundle()`, which loads the
example bundle from `src/flowforge_jtbd_hr/examples/bundle.yaml`.

Do not use this package in release marketing, platform support matrices, or
regulated production implementation claims until it has explicit SME approval,
publishable packaging, and critical-system verification evidence.
