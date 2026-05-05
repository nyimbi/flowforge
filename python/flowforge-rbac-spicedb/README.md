# flowforge-rbac-spicedb

SpiceDB-backed RBAC resolver. Wraps the `authzed-py` async client and
delegates permission checks to SpiceDB's `CheckPermission` RPC, while
catalogue seeding rides on `WriteRelationships`.

Use this when your application already centralises authorisation in
SpiceDB and you want flowforge to stay thin — `flowforge-rbac-static`
is the lighter-weight alternative for self-contained projects.

## Install

```bash
uv pip install flowforge-rbac-spicedb[spicedb]
```

The `spicedb` extra pulls in `authzed`. Tests in this package do **not**
require it — they use a `FakeSpiceDBClient` stub from
`flowforge_rbac_spicedb.testing`.

## Wiring

```python
from authzed.api.v1 import Client
from grpcutil import bearer_token_credentials

from flowforge import config
from flowforge_rbac_spicedb import SpiceDBRbac

client = Client("spicedb.internal:50051", bearer_token_credentials("…"))
config.rbac = SpiceDBRbac(
    client,
    schema_prefix="flowforge",
    permission_subject_type="user",
)
```

## Mapping conventions

flowforge addresses `Scope`s via `<resource_kind>:<resource_id>`. When
`Scope.resource_id` is `None`, the resolver falls back to the
tenant-scoped synthetic object `tenant:<tenant_id>`. The subject is
always `user:<principal.user_id>`.

System principals (`Principal.is_system=True`) bypass the wire entirely
and return `True` without contacting SpiceDB — same shortcut as
`flowforge-rbac-static`.

## Testing without SpiceDB

```python
from flowforge_rbac_spicedb import SpiceDBRbac
from flowforge_rbac_spicedb.testing import FakeSpiceDBClient

fake = FakeSpiceDBClient()
fake.grant("user:alice", "claim.create", "tenant:t-1")
rbac = SpiceDBRbac(fake)
```

`FakeSpiceDBClient` implements the same async `CheckPermission`,
`WriteRelationships`, and `LookupSubjects` surface as the real client,
keeps state in-process, and never touches gRPC.
