# flowforge-jtbd-gaming

**Starter scaffold** — workspace-only package scaffold; not publishable, not SME-reviewed, and not part of the critical-system support matrix. Keep `package = false` until E-48a review flips `package = true`.

Online gaming platform workflows covering player abuse investigation, ban appeals, tournament registration, virtual item disputes, payment refunds, community content moderation, compromised account recovery, virtual currency auditing, loot box regulation compliance, and cheating/hacking investigations.

**Tier**: B (AI-authored, citation-anchored)
**JTBDs**: 10

## Included JTBDs

| ID | Title |
|---|---|
| investigate_report | Investigate a player abuse report |
| process_ban_appeal | Process a ban appeal |
| register_tournament | Register and validate a tournament |
| resolve_item_dispute | Resolve a virtual item dispute |
| process_refund | Process a payment refund |
| moderate_community | Moderate community content |
| recover_account | Recover a compromised player account |
| audit_virtual_currency | Audit virtual currency issuance |
| comply_loot_box_regulation | Comply with loot box regulation |
| investigate_cheating | Investigate cheating / hacking |

## Usage

```python
from flowforge_jtbd_gaming import load_bundle

bundle = load_bundle()
# bundle["jtbds"] — list of JTBD dicts
# bundle["project"] — domain metadata
```

## CLI

```bash
# Lint the bundle
flowforge jtbd lint python/flowforge-jtbd-gaming/src/flowforge_jtbd_gaming/examples/bundle.json

# Run the tutorial with this domain
flowforge tutorial --domain gaming
```

## Citation accuracy

This package is AI-authored. All regulatory citations are anchored to the R-01 registry snapshot at authoring time. Validate citations against current law before production use. Named SME review is pending.
