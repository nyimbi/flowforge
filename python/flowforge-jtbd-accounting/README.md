# flowforge-jtbd-accounting

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Core accounting workflows covering the full financial reporting cycle from journal entry posting through period close, AP/AR, fixed assets, consolidation, and FX revaluation.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| post_journal_entry | Post general ledger journal entry |
| process_AP_invoice | Process accounts payable invoice |
| process_AR_invoice | Issue and collect accounts receivable invoice |
| submit_expense_report | Submit and approve employee expense report |
| close_period | Execute monthly / quarterly period close |
| reconcile_bank | Reconcile bank account |
| record_fixed_asset | Record acquisition of fixed asset |
| calculate_depreciation | Calculate and post periodic depreciation |
| eliminate_intercompany | Eliminate intercompany transactions in consolidation |
| revalue_FX | Revalue foreign currency monetary items |

## Usage

```python
from flowforge_jtbd_accounting import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-accounting/src/flowforge_jtbd_accounting/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain accounting
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
