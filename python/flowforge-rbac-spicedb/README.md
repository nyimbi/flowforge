# flowforge-rbac-spicedb

SpiceDB-backed RBAC resolver for flowforge.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install "flowforge-rbac-spicedb[spicedb]"
```

The `spicedb` extra pulls in `authzed`. The package itself and its test suite do not require it — tests use `FakeSpiceDBClient` from `flowforge_rbac_spicedb.testing`.

## What it does

Wraps an `authzed-py` async client and delegates `has_permission` calls to SpiceDB's `CheckPermission` RPC. Subject is always `user:<principal.user_id>`; resource is `<scope.resource_kind or "tenant">:<scope.resource_id or scope.tenant_id>`. System principals (`Principal.is_system=True`) bypass the wire and return `True` without contacting SpiceDB.

The permission catalogue — which SpiceDB has no native concept of — is maintained as a synthetic `permission_catalog:<schema_prefix>` object with a `defined` relation per permission name. `register_permission` writes this relation via `WriteRelationships`; `assert_seed` reads it back via `LookupSubjects`.

The resolver captures the `written_at_token` Zedtoken from each `WriteRelationships` response and attaches it as `consistency.at_least_as_fresh` on subsequent reads. This gives read-after-write consistency for the same resolver instance without a global `fully_consistent` round-trip.

If you are self-contained — no existing SpiceDB, no relationship-based access, no multi-tenant permission delegation — use `flowforge-rbac-static` instead.

## Quick start

```python
from authzed.api.v1 import AsyncClient
from grpcutil import bearer_token_credentials

from flowforge import config
from flowforge_rbac_spicedb import SpiceDBRbac
from flowforge.ports import Principal, Scope

client = AsyncClient(
	"spicedb.internal:50051",
	bearer_token_credentials("your-preshared-key"),
)
rbac = SpiceDBRbac(
	client,
	schema_prefix="myapp",
	subject_object_type="user",
)
config.rbac = rbac

principal = Principal(user_id="alice")
scope = Scope(tenant_id="t-1")
allowed = await rbac.has_permission(principal, "claim.create", scope)
```

Testing without SpiceDB:

```python
from flowforge_rbac_spicedb import SpiceDBRbac
from flowforge_rbac_spicedb.testing import FakeSpiceDBClient

fake = FakeSpiceDBClient()
fake.grant("user:alice", "claim.create", "tenant:t-1")
rbac = SpiceDBRbac(fake)

principal = Principal(user_id="alice")
scope = Scope(tenant_id="t-1")
assert await rbac.has_permission(principal, "claim.create", scope)
```

`FakeSpiceDBClient` implements `CheckPermission`, `WriteRelationships`, and `LookupSubjects` entirely in-process; it never touches gRPC.

## Public API

- `SpiceDBRbac(client, *, schema_prefix, subject_object_type, default_resource_type, strict)` — main resolver
- `SpiceDBRbac.last_zedtoken()` — most-recently-observed write Zedtoken
- `SpiceDBRbac.reset_zedtoken()` — drop the cached token (use in read-only batch paths)
- `SpiceDBClientProtocol` — structural `Protocol` that both `authzed.api.v1.AsyncClient` and `FakeSpiceDBClient` satisfy
- `CatalogDriftError` — raised by `assert_seed` in strict mode

From `flowforge_rbac_spicedb.testing`:

- `FakeSpiceDBClient` — in-memory stub; `fake.grant(subject, permission, resource)` / `fake.revoke(...)`

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `schema_prefix` | `"flowforge"` | Logical namespace for the permission catalogue object |
| `subject_object_type` | `"user"` | SpiceDB object type for principals |
| `default_resource_type` | `"tenant"` | Fallback when `Scope.resource_kind` is `None` |
| `strict` | `False` | Raise `CatalogDriftError` from `assert_seed` instead of returning missing list |

## Audit-2026 hardening

- **RB-02** (E-55): Zedtoken propagation for read-after-write consistency — `register_permission` captures `written_at_token` from the `WriteRelationships` response and attaches it as `consistency.at_least_as_fresh` on subsequent `CheckPermission` and `LookupSubjects` calls; `FakeSpiceDBClient` exposes `last_consistency_token` so tests can assert the token is forwarded correctly

## Compatibility

- Python 3.11+
- `authzed` >= 0.13 (optional; install with `[spicedb]` extra)
- `grpcio` / `grpcutil` (required when using the real client)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge-core`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core)
- [`flowforge-rbac-static`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-rbac-static) — file-based alternative for self-contained deployments
- [`flowforge-tenancy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-tenancy)
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md)
