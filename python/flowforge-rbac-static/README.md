# flowforge-rbac-static

Static RBAC resolver. Reads a role->permissions map from YAML or JSON
and answers `has_permission` checks against it. Useful for small apps,
demos, and the JTBD-generator's default project skeleton.

## Config shape

```yaml
roles:
  intake_clerk: [claim.create, claim.read]
  triage_officer: [claim.read, claim.update]
  claims_supervisor: [claim.read, claim.update, claim.approve, claim.escalate]
principals:
  alice: [intake_clerk]
  bob: [triage_officer, claims_supervisor]
permissions:
  - { name: claim.create, description: Create a new claim }
  - { name: claim.read, description: Read a claim }
  - { name: claim.update, description: Update a claim }
  - { name: claim.approve, description: Approve a claim }
  - { name: claim.escalate, description: Escalate a claim }
```

## Wiring

```python
from flowforge import config
from flowforge_rbac_static import StaticRbac

config.rbac = StaticRbac.from_yaml("./rbac.yaml")
```

`assert_seed(...)` returns missing names by default; pass `strict=True`
in the constructor to raise `CatalogDriftError` instead.
