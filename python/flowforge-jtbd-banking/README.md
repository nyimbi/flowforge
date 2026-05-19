# flowforge-jtbd-banking

Status: strategic domain content candidate

Package state: workspace-only (`[tool.uv] package = false`)

Support level: not publishable, not SME-reviewed, and not part of the
critical-system support matrix until named banking SME signoff, release review,
and `package = true` are completed.

Starter? No. This package carries domain-specific JTBD content for banking
workflows, but it is not a release artifact yet.

## Contents

This package includes banking JTBD content for account opening, KYC, beneficial
owner review, card issue, credit assessment, fraud dispute review, loan
application, loan origination, payment processing, and wire transfer
authorization.

The public entrypoint is `flowforge_jtbd_banking.load_bundle()`, which loads the
example bundle from `src/flowforge_jtbd_banking/examples/bundle.yaml`.

Do not use this package in release marketing, platform support matrices, or
regulated production implementation claims until it has explicit SME approval,
publishable packaging, and critical-system verification evidence.
