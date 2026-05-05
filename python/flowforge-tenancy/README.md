# flowforge-tenancy

Tenancy resolvers for flowforge. Three impls covering the common cases:

| Impl | When to use |
|---|---|
| `SingleTenantGUC` | One tenant, Postgres-backed RLS via `set_config('app.tenant_id', ...)` |
| `MultiTenantGUC` | Multi-tenant SaaS; tenant id resolved per-request and rebound on the session |
| `NoTenancy` | Single-org apps with no isolation requirement; never touches the DB |

## Wiring

```python
from flowforge import config
from flowforge_tenancy import MultiTenantGUC

config.tenancy = MultiTenantGUC(resolver=lambda: get_request_tenant_id())
```

The `elevated_scope()` context manager toggles `app.elevated` on the
session for both GUC impls; `NoTenancy` no-ops it.
