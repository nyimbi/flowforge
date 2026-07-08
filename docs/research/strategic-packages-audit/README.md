# Strategic Packages Audit

Date: 2026-07-08

Scope: six remaining strategic Python packages:

- `python/flowforge-outbox-pg`
- `python/flowforge-audit-pg`
- `python/flowforge-tenancy`
- `python/flowforge-rbac-static`
- `python/flowforge-money`
- `python/flowforge-notify-multichannel`

Checklist run for each package:

- `ls python/<pkg>/src/**/*.py`
- `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache uv run pytest python/<pkg>/tests -q --tb=no 2>&1 | tail -3`
- `grep -rn 'TODO\|FIXME\|NotImplementedError\|raise NotImplementedError\|^\s*pass$' python/<pkg>/src/ --include='*.py'`
- `find python/<pkg>/tests -name 'test_*.py' | wc -l`

## Findings

| Package | Source files | Test files | Final package test result | Stub scan | Findings and actions |
| --- | ---: | ---: | --- | --- | --- |
| `flowforge-outbox-pg` | 5 | 3 | `58 passed` | No matches | Drain worker, pool, registry, and health modules are implemented. No TODO/FIXME/NotImplemented/pass stubs found. No code change needed. |
| `flowforge-audit-pg` | 7 | 5 | `78 passed, 2 skipped` | No matches | Hash chain verification is implemented in `PgAuditSink.verify_chain()` and `verify_chain_in_memory()`. Existing tests cover payload tampering, previous-hash mismatch, tenant-interleaved chains, legacy rows, and chunked verification. No code change needed. |
| `flowforge-tenancy` | 5 | 1 | `22 passed` | No matches | Added request-scoped resolver patterns: `HeaderTenantResolver` for `X-Tenant-ID`, `JwtClaimTenantResolver` with explicit HMAC JWT verification by default, and `SubdomainTenantResolver` for host-based tenancy. Added regression tests for valid extraction and unsafe input rejection. |
| `flowforge-rbac-static` | 2 | 1 | `11 passed` | No matches | Static RBAC resolver has concrete behavior and tests. No TODO/FIXME/NotImplemented/pass stubs found. No code change needed. |
| `flowforge-money` | 3 | 2 | `45 passed` | No matches | Money formatting and static currency behavior are implemented and covered. No TODO/FIXME/NotImplemented/pass stubs found. No code change needed. |
| `flowforge-notify-multichannel` | 3 | 2 | `72 passed` | No matches | Email, SMS, push, webhook, Slack, and in-app transports are concrete. Improved router send semantics so failed `DeliveryResult`s and adapter exceptions are retried with bounded attempts, reported via `last_delivery_error`, and do not poison dedupe/throttle state. Added regression tests for retry success, retry exhaustion, exception retry, and fanout failure reporting. |

## Source Files Audited

`flowforge-outbox-pg`:

- `src/flowforge_outbox_pg/__init__.py`
- `src/flowforge_outbox_pg/health.py`
- `src/flowforge_outbox_pg/pool.py`
- `src/flowforge_outbox_pg/registry.py`
- `src/flowforge_outbox_pg/worker.py`

`flowforge-audit-pg`:

- `src/flowforge_audit_pg/__init__.py`
- `src/flowforge_audit_pg/_golden.py`
- `src/flowforge_audit_pg/analytics.py`
- `src/flowforge_audit_pg/hash_chain.py`
- `src/flowforge_audit_pg/migrations/__init__.py`
- `src/flowforge_audit_pg/migrations/audit_ordinal_backfill.py`
- `src/flowforge_audit_pg/sink.py`

`flowforge-tenancy`:

- `src/flowforge_tenancy/__init__.py`
- `src/flowforge_tenancy/multi.py`
- `src/flowforge_tenancy/none.py`
- `src/flowforge_tenancy/request.py`
- `src/flowforge_tenancy/single.py`

`flowforge-rbac-static`:

- `src/flowforge_rbac_static/__init__.py`
- `src/flowforge_rbac_static/resolver.py`

`flowforge-money`:

- `src/flowforge_money/__init__.py`
- `src/flowforge_money/format.py`
- `src/flowforge_money/static.py`

`flowforge-notify-multichannel`:

- `src/flowforge_notify_multichannel/__init__.py`
- `src/flowforge_notify_multichannel/router.py`
- `src/flowforge_notify_multichannel/transports.py`

## Security And Performance Notes

- Tenancy JWT claim resolution verifies HS256/HS384/HS512 signatures by default and requires an explicit secret unless the caller opts into unverified decoding.
- Tenant ids from headers, JWT claims, and subdomains are stripped and validated before use.
- Notification delivery retries are bounded by `max_delivery_attempts` and do not sleep by default, keeping tests and synchronous retry paths fast.
- Notification dedupe and throttle markers are committed only after successful delivery, so transient provider failures remain retryable.
- Audit chain verification was already chunked and tenant-aware; no memory-unbounded hash-chain walk was found.
