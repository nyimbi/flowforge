# Security Hardening Guide for flowforge Deployments

**Version:** 0.5.x documentation baseline
**Audience:** Platform engineers, DevSecOps, security architects  
**Scope:** Production deployment of flowforge-core and its adapter packages

---

## Table of Contents

1. [Authentication Hardening](#1-authentication-hardening)
2. [Database Hardening](#2-database-hardening)
3. [Network Hardening](#3-network-hardening)
4. [Secrets Management](#4-secrets-management)
5. [Observability and Incident Response](#5-observability-and-incident-response)
6. [Dependency Security](#6-dependency-security)
7. [Compliance-Specific Settings](#7-compliance-specific-settings)
8. [Security Ratchets (CI Enforcement)](#8-security-ratchets-ci-enforcement)

---

## 1. Authentication Hardening

### 1.1 Configure a Real `PrincipalExtractor`

The `principal_extractor` parameter on every flowforge FastAPI router is required in production. The framework ships `StaticPrincipalExtractor` for tests and demos only — it returns the same principal for every request without any verification.

**Never deploy this in production:**

```python
# WRONG — StaticPrincipalExtractor bypasses all authentication
from flowforge_fastapi.auth import StaticPrincipalExtractor, StaticTenantResolver
from flowforge_fastapi import build_runtime_router

router = build_runtime_router(
    principal_extractor=StaticPrincipalExtractor(),  # development only
    tenant_resolver=StaticTenantResolver(),          # development only
)
```

**Correct production wiring using `JwtPrincipalExtractor`:**

```python
import os

from flowforge_signing_kms import AwsKmsSigning
from flowforge_jtbd_hub.jwt_extractor import make_jwt_extractor
from flowforge_fastapi import build_runtime_router

# KMS-backed signing — key ARN comes from environment
signing = AwsKmsSigning(
    key_id=os.environ["KMS_SIGNING_KEY_ARN"],
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    algorithm="HMAC_SHA_256",
)

# JWT extractor wraps signing; KMS transient errors → 503 (BLK-01)
extractor = make_jwt_extractor(signing)

router = build_runtime_router(
    principal_extractor=extractor,
    tenant_resolver=tenant_resolver,  # resolve from trusted auth/session context
)
```

The `make_jwt_extractor` factory produces a `JwtPrincipalExtractor` that:
- Validates token structure and expiry using `pyjwt`
- Verifies the HMAC/KMS signature via the `SigningPort`
- Raises HTTP 503 (not 401) when the signing backend is unavailable, preventing silent auth bypass (BLK-01 fix)

### 1.2 Extractor Fault Behaviour (BLK-01)

The BLK-01 finding identified that an infrastructure fault in the principal extractor (e.g., a KMS network timeout) previously caused a silent downgrade — the request was processed as unauthenticated. The fix in `flowforge_jtbd_hub/app.py` wraps the extractor call and returns HTTP 503 on any unexpected exception:

```python
# Internal to app.py — shown for verification purposes
try:
    principal = await extractor(request)
except HTTPException:
    raise  # 401/403 are legitimate auth failures
except Exception:
    # Infrastructure error — surface as 503, not auth bypass
    raise HTTPException(status_code=503, detail="authentication service unavailable")
```

**Verify this is active in your deployment** by simulating a KMS timeout and confirming a 503 response.

### 1.3 `FLOWFORGE_SIGNING_SECRET` Must Come from KMS

The `HmacDevSigning` class is the local-development signing backend. Instantiating it without a secret now raises `RuntimeError` (SK-01 fix). The insecure opt-in path (`FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`) emits a loud `WARNING` log and increments the `flowforge_signing_secret_default_used_total` Prometheus counter.

**Production requirement:** Use `AwsKmsSigning` or `GcpKmsSigning`. Never set `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` in production.

```python
# AWS KMS — recommended for production
from flowforge_signing_kms import AwsKmsSigning

signing = AwsKmsSigning(
    key_id="alias/flowforge-signing",   # alias or ARN from env
    region_name="us-east-1",
    algorithm="HMAC_SHA_256",
)

# GCP Cloud KMS alternative
from flowforge_signing_kms import GcpKmsSigning

signing = GcpKmsSigning(
    key_version_name=(
        "projects/my-project/locations/global/"
        "keyRings/flowforge/cryptoKeys/signing/cryptoKeyVersions/1"
    ),
    use_mac=True,
)
```

### 1.4 `CookiePrincipalExtractor` Configuration

If you use the cookie-based session (e.g., server-side session for a web app rather than a stateless JWT), configure `CookiePrincipalExtractor` with a 24-hour TTL and the `Secure` attribute:

```python
from flowforge_fastapi.auth import CookiePrincipalExtractor, issue_csrf_token

# Session extractor — secret must come from KMS-derived material or env var
extractor = CookiePrincipalExtractor(
    secret=os.environ["SESSION_COOKIE_SECRET"],   # min 32 random bytes, base64-encoded
    cookie_name="flowforge_session",
    ttl_seconds=60 * 60 * 24,  # 24 hours
)

# On first login response
@app.post("/login")
async def login(response: Response, ...):
    principal = await authenticate(request)  # your auth logic
    cookie_value = extractor.issue(principal)
    response.set_cookie(
        key="flowforge_session",
        value=cookie_value,
        httponly=True,
        secure=True,          # required in production
        samesite="lax",
        max_age=86400,
    )
    # Also issue CSRF token on the same response
    issue_csrf_token(response, secure=True)
    return {"ok": True}
```

The E-41 / FA-06 fix adds `iat` (issued-at) and `exp` (expiration) fields to the cookie payload. Expired cookies are rejected with 401.

### 1.5 Admin Token Rotation Procedure

When rotating the session cookie secret or JWT signing key:

1. Generate the new key material (via KMS or `secrets.token_bytes(32)`).
2. For `HmacDevSigning` (development only): use the key-map form to support both old and new keys during the rotation window:

```python
signing = HmacDevSigning(
    keys={
        "key-2025-01": os.environ["SIGNING_SECRET_OLD"],
        "key-2026-01": os.environ["SIGNING_SECRET_NEW"],
    },
    current_key_id="key-2026-01",   # sign with new key
)
# Old tokens signed with key-2025-01 verify fine (SK-02)
```

3. For `AwsKmsSigning`: enable automatic KMS key rotation (annual) and use aliases rather than ARNs. KMS handles the cryptographic rotation transparently.
4. After confirming all sessions using the old key have expired (TTL elapsed), remove the old key from the key map.
5. Record the rotation in the audit log:

```python
await config.audit.record(AuditEvent(
    tenant_id="system",
    actor_user_id="ops-engineer@example.com",
    kind="admin.signing_key.rotated",
    subject_kind="signing_key",
    subject_id="key-2026-01",
    payload={"previous_key_id": "key-2025-01", "rotation_reason": "scheduled"},
))
```

---

## 2. Database Hardening

### 2.1 Enable Postgres RLS via `PgRlsBinder`

Row-Level Security is the primary mechanism for tenant isolation. flowforge provides two GUC-based binders in `flowforge-tenancy`:

- `SingleTenantGUC` — for single-tenant deployments; sets `app.tenant_id` to a fixed value.
- `MultiTenantGUC` — resolves `tenant_id` per-request from the authenticated principal.

**Wiring `MultiTenantGUC`:**

```python
from flowforge_tenancy import MultiTenantGUC
from flowforge import config

rls_binder = MultiTenantGUC()

config.configure(
    tenancy=my_tenancy_resolver,
    rls=rls_binder,
    # ... other ports
)
```

The binder issues `SELECT set_config('app.tenant_id', :tenant_id, true)` within every transaction. The `true` argument (transaction-scoped) is critical — it ensures the GUC does not persist to the next request on the same connection from a pool.

**RLS policy template** (from `flowforge-jtbd`'s generated migrations):

```sql
ALTER TABLE workflow_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_instances FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON workflow_instances
    USING (tenant_id = current_setting('app.tenant_id'))
    WITH CHECK (tenant_id = current_setting('app.tenant_id'));
```

Verify RLS is enforced on all tenant-scoped tables:

```sql
SELECT tablename, rowsecurity, forcerowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

### 2.2 Use `validate_production_config()` at Startup

Call this function before accepting requests. It raises `ProductionConfigError` if any required port is absent:

```python
from flowforge.config import validate_production_config

# Minimum for SOC 2: add "signing" to the default set
validate_production_config(
    required_ports=(
        "tenancy",
        "rbac",
        "audit",
        "outbox",
        "rls",
        "signing",   # required for SOC 2 / tamper-evidence
    )
)
```

The default set is `("tenancy", "rbac", "audit", "outbox", "rls")`. Do not omit any of these in production. The function raises on the first missing port — integrate it into your ASGI lifespan:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from flowforge.config import validate_production_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_config(
        required_ports=("tenancy", "rbac", "audit", "outbox", "rls", "signing")
    )
    yield

app = FastAPI(lifespan=lifespan)
```

### 2.3 Audit Log Tamper-Proofing: Hash Chain Verification

Every row written by `PgAuditSink` carries:
- `prev_sha256` — the `row_sha256` of the previous row for this tenant (or `NULL` for the first row)
- `row_sha256 = sha256(prev_sha256_or_empty + canonical_json(row_fields))`

The canonical JSON encoding uses sorted keys, no whitespace, ISO-8601 datetimes, and UUIDs as strings (deterministic, RFC-8785-aligned).

**Run verification on a schedule** (daily cron or pre-audit):

```python
import asyncio, sys
from sqlalchemy.ext.asyncio import create_async_engine
from flowforge_audit_pg import PgAuditSink

async def verify_chain():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sink = PgAuditSink(engine)
    verdict = await sink.verify_chain()
    if not verdict.ok:
        print(f"CHAIN BROKEN at event_id={verdict.first_bad_event_id}", file=sys.stderr)
        sys.exit(1)
    print(f"Chain OK: {verdict.rows_checked} rows verified")

asyncio.run(verify_chain())
```

A non-zero `flowforge_audit_chain_breaks_total` counter in Prometheus signals tampering. Alert on it immediately.

**The DELETE-blocking trigger** prevents row deletion at the database level:

```sql
-- Verify the trigger exists
SELECT tgname, tgenabled
FROM pg_trigger
WHERE tgname = 'ff_audit_no_delete_tg';
```

If the trigger is missing (e.g., after a restore), reinstall it by calling `create_tables()` again — it is idempotent.

### 2.4 GDPR Redaction Without Breaking the Chain

The `PgAuditSink.redact()` method writes tombstone markers (`__REDACTED__`) to `payload` fields without modifying `prev_sha256` or `row_sha256`. This means:
- The hash chain remains intact (verifiable).
- Future verification detects that payload was modified (expected — the chain validates `row_sha256` which was computed at write time, before redaction).

**Procedure:**

```python
# Redact PII fields across all audit rows
count = await sink.redact(
    paths=["payload.email", "payload.phone", "payload.ssn"],
    reason="GDPR erasure request — subject_id=user-abc123, ticket=GDPR-2026-0042",
)
print(f"Redacted {count} rows")
```

Document all redactions in your GDPR log. The `__redaction_reason__` field is written to each affected row's payload.

### 2.5 Connection String Secrets

Never hardcode database connection strings. Use environment variables exclusively:

```python
# Correct
engine = create_async_engine(os.environ["DATABASE_URL"])

# Wrong — never do this
engine = create_async_engine("postgresql+asyncpg://app:password@localhost/flowforge")
```

Use your platform's secret management (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault) to inject `DATABASE_URL` at runtime. Rotate database passwords on the same schedule as other credentials (quarterly minimum for SOC 2).

---

## 3. Network Hardening

### 3.1 TLS Everywhere

All inter-service communication must use TLS. flowforge's notification adapters enforce this at construction time where applicable:

**SMTP (EmailAdapter):**

```python
from flowforge_notify_multichannel import EmailAdapter

# TLS required — set SMTP_TLS=true and use port 587 or 465
adapter = EmailAdapter(
    host=os.environ["SMTP_HOST"],       # never "localhost" in production
    port=int(os.environ.get("SMTP_PORT", "587")),
    username=os.environ["SMTP_USERNAME"],
    password=os.environ["SMTP_PASSWORD"],
    from_addr=os.environ["SMTP_FROM"],  # must not be noreply@example.com
    use_tls=True,                       # STARTTLS
)
```

The `EmailAdapter` raises `ValueError` at construction if `SMTP_HOST` is `"localhost"` (the default) and no explicit `host=` is passed. This prevents accidental use of a local relay in production (H-03 fix).

**AWS SES (SESEmailAdapter):**

```python
from flowforge_notify_multichannel import SESEmailAdapter

adapter = SESEmailAdapter(
    region=os.environ["SES_REGION"],              # e.g. "us-east-1"
    from_addr=os.environ["SES_FROM_ADDRESS"],     # must not be noreply@example.com
    # Use a VPC endpoint for SES to avoid public internet
)
```

`SESEmailAdapter` raises `ValueError` at construction if `SES_FROM_ADDRESS` is the placeholder `noreply@example.com` and no explicit `from_addr=` is passed (H-04 fix).

### 3.2 Webhook Signature Verification

All inbound webhooks must be verified. flowforge's `WebhookAdapter` requires an HMAC secret:

```python
from flowforge_notify_multichannel import WebhookAdapter

adapter = WebhookAdapter(
    secret=os.environ["WEBHOOK_HMAC_SECRET"],    # raises ValueError if empty
    allowed_hosts=frozenset([
        "hooks.stripe.com",
        "api.github.com",
    ]),
)
```

**Never leave `allowed_hosts` empty** without also passing `allow_any_public_host=True`. An empty `allowed_hosts` with `allow_any_public_host=False` (the default) blocks all outbound webhook calls. An explicit allowlist is the most secure configuration.

For inbound signature verification on Stripe and GitHub webhooks, use the framework's verifiers:

```python
# Stripe webhook verification
from flowforge_notify_multichannel.transports import WebhookVerifier

verifier = WebhookVerifier(
    secret=os.environ["STRIPE_WEBHOOK_SECRET"],
    header_name="Stripe-Signature",
)

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    if not await verifier.verify(payload, sig):
        raise HTTPException(status_code=400, detail="invalid signature")
    # ... process event

# GitHub webhook verification
verifier = WebhookVerifier(
    secret=os.environ["GITHUB_WEBHOOK_SECRET"],
    header_name="X-Hub-Signature-256",
)
```

Both verifiers use `hmac.compare_digest` internally (NM-01 compliance).

### 3.3 CSRF Protection

The `csrf_protect` FastAPI dependency enforces the double-submit-cookie pattern. Wire it on all mutating endpoints:

```python
from fastapi import Depends
from flowforge_fastapi.auth import csrf_protect, issue_csrf_token

@app.get("/bootstrap")
async def bootstrap(response: Response):
    # Issue CSRF token on first idempotent request
    token = issue_csrf_token(response, secure=True)   # default
    return {"csrf_ready": True}

@app.post("/api/workflows/{instance_id}/fire", dependencies=[Depends(csrf_protect)])
async def fire_event(instance_id: str, ...):
    # csrf_protect rejects if X-CSRF-Token != cookie value
    ...
```

`issue_csrf_token()` defaults to `secure=True`. Passing `secure=False` without `dev_mode=True` raises `ConfigError` immediately — this prevents insecure CSRF cookies from reaching TLS-terminated hosts. The `flowforge_fastapi_csrf_config_error_total` counter increments on each attempt; alert if it is non-zero in production.

**The `dev_mode=True` escape hatch is for development only:**

```python
# Development only — never in production
issue_csrf_token(response, secure=False, dev_mode=True)
```

---

## 4. Secrets Management

### 4.1 Never Hardcode Secrets

The following environment variables raise `ValueError` or `RuntimeError` if they contain placeholder values:

| Env Var | Adapter | What Happens if Placeholder |
|---|---|---|
| `FLOWFORGE_SIGNING_SECRET` | `HmacDevSigning` | `RuntimeError` at construction (SK-01) |
| `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` | `HmacDevSigning` | Emits loud `WARNING`; increments `flowforge_signing_secret_default_used_total` |
| `SMTP_FROM=noreply@example.com` | `EmailAdapter` | `ValueError` at construction (H-03) |
| `SES_FROM_ADDRESS=noreply@example.com` | `SESEmailAdapter` | `ValueError` at construction (H-04) |
| `SMTP_HOST=localhost` | `EmailAdapter` | `ValueError` at construction (H-03) |
| `WEBHOOK_HMAC_SECRET` (empty) | `WebhookAdapter` | `ValueError` at construction |

The `no_default_secret` ratchet (`scripts/ci/ratchets/no_default_secret.sh`) enforces that the literal string `flowforge-dev-secret-not-for-production` never appears in committed code outside of `baseline.txt`.

### 4.2 KMS vs. HMAC-Dev: Which to Use

| Signing Backend | Use When | Notes |
|---|---|---|
| `HmacDevSigning` | Local development, unit tests | Raises `RuntimeError` without `FLOWFORGE_SIGNING_SECRET`. Logs `WARNING` if insecure-default opt-in is active. |
| `AwsKmsSigning` | Production on AWS | Key ARN or alias from env. Async via `asyncio.to_thread` (SK-04). Supports HMAC_SHA_256 and RSA_PKCS1 algorithms. |
| `GcpKmsSigning` | Production on GCP | Full key version name from env. Async via `asyncio.to_thread` (SK-04). Supports MAC and asymmetric RSA. |

**The `HmacDevSigning` logs a `WARNING` at startup** if the insecure default is active. This warning will appear in your production log aggregator if misconfigured — treat it as a P0 alert.

### 4.3 Secret Rotation

**KMS key rotation (AWS):**

```bash
# Enable automatic annual rotation on the KMS key
aws kms enable-key-rotation \
  --key-id alias/flowforge-signing

# Verify rotation is enabled
aws kms get-key-rotation-status \
  --key-id alias/flowforge-signing
```

AWS KMS handles the cryptographic rotation transparently. Old tokens signed with the previous key version continue to verify until they expire.

**HMAC secret rotation (development/staging):**

1. Generate new secret: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `FLOWFORGE_SIGNING_SECRET` in your secrets manager.
3. Use the key-map form of `HmacDevSigning` during the transition window (SK-02):

```python
signing = HmacDevSigning(
    keys={
        "key-v1": old_secret,   # for verifying existing tokens
        "key-v2": new_secret,   # for signing new tokens
    },
    current_key_id="key-v2",
)
```

4. After all tokens signed with `key-v1` have expired, remove it from the map.
5. Record the rotation in the audit log (see section 1.5).

**Database password rotation:**

1. Generate new password in your secrets manager.
2. Update the Postgres user password: `ALTER USER flowforge_app PASSWORD 'new_password';`
3. Update `DATABASE_URL` in your secrets manager.
4. Perform a rolling restart of the application (connections will re-authenticate).
5. Verify health checks pass before removing the old password.

**Session cookie secret rotation:**

Same procedure as HMAC secret rotation. The `CookiePrincipalExtractor` does not support a key map (only a single secret), so plan for a brief window where old sessions are invalidated. Use a 24-hour TTL (the default) to minimize the disruption window.

---

## 5. Observability and Incident Response

### 5.1 Prometheus Scraping Setup

flowforge metrics are emitted via the `MetricsPort`. Wire the Prometheus Gauge/Counter/Histogram collector in your application startup:

```python
from flowforge import config
from flowforge.ports.metrics import (
    FIRE_DURATION_HISTOGRAM,
    OUTBOX_DISPATCH_DURATION_HISTOGRAM,
    AUDIT_APPEND_DURATION_HISTOGRAM,
)
# Use your Prometheus client library to register collectors
# and wire them into config.metrics
```

Add a `/metrics` scrape endpoint and configure Prometheus:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: flowforge
    static_configs:
      - targets: ['flowforge-app:8080']
    scrape_interval: 15s
    metrics_path: /metrics
```

### 5.2 Critical Alerts

The following alert rules cover the most important failure modes. Add them to your Alertmanager configuration:

```yaml
# prometheus/rules/flowforge.yml
groups:
  - name: flowforge_critical
    rules:

      # Lock contention — more than 10 concurrent-fire rejections per minute
      - alert: FlowforgeConcurrentFireSpike
        expr: |
          rate(flowforge_engine_fire_rejected_concurrent_total[1m]) > 10
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "flowforge engine lock contention"
          description: >
            {{ $value | humanize }} concurrent-fire rejections/min.
            Indicates multiple callers racing on the same workflow instance.
            Check for runaway retry loops or missing instance-level queuing.

      # Engine latency — p95 > 500ms
      - alert: FlowforgeFireLatencyHigh
        expr: |
          histogram_quantile(0.95,
            rate(flowforge_fire_duration_seconds_bucket[5m])
          ) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "flowforge fire() p95 latency > 500ms"
          description: >
            The workflow engine's p95 transaction time is {{ $value | humanizeDuration }}.
            Check Postgres query plan, connection pool exhaustion, and advisory lock wait time.

      # Outbox DLQ — any stuck messages
      - alert: FlowforgeOutboxDLQDepth
        expr: |
          sum(flowforge_outbox_dlq_depth) > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "flowforge outbox has stuck messages"
          description: >
            {{ $value }} outbox messages have been in the DLQ for > 5 minutes.
            These represent workflow events that failed delivery and need investigation.
            Check the outbox worker logs and downstream event consumer health.

      # Audit chain break — immediate escalation
      - alert: FlowforgeAuditChainBroken
        expr: |
          increase(flowforge_audit_chain_breaks_total[5m]) > 0
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "flowforge audit chain integrity violation"
          description: >
            The SHA-256 audit hash chain has detected a broken link.
            This may indicate database tampering or a bug in audit write ordering.
            Immediately escalate to the security team. Do not restart services until
            forensic investigation is complete.

      # Insecure signing default — P0 misconfiguration
      - alert: FlowforgeInsecureSigningDefault
        expr: |
          increase(flowforge_signing_secret_default_used_total[5m]) > 0
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "flowforge is using the insecure dev signing secret"
          description: >
            FLOWFORGE_ALLOW_INSECURE_DEFAULT=1 is active in this environment.
            The hard-coded dev secret is being used for production signing.
            This is a P0 security misconfiguration. Rotate credentials immediately
            and set FLOWFORGE_SIGNING_SECRET from KMS.

      # CSRF misconfiguration
      - alert: FlowforgeCsrfConfigError
        expr: |
          increase(flowforge_fastapi_csrf_config_error_total[5m]) > 0
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "flowforge CSRF secure=False attempted in production"
          description: >
            issue_csrf_token() was called with secure=False without dev_mode=True.
            Review recent deployments for CSRF cookie misconfiguration.

      # KMS transient errors — may indicate credential expiry or network issue
      - alert: FlowforgeKmsTransientErrors
        expr: |
          rate(flowforge_kms_transient_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "flowforge KMS is returning transient errors"
          description: >
            {{ $value | humanize }} KMS transient errors/sec. Check KMS endpoint
            availability, IAM role permissions, and network connectivity.
            Sustained KMS unavailability will cause all JWT verification to return 503.
```

### 5.3 PagerDuty / Alertmanager Integration

```yaml
# alertmanager.yml
route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
        alertname: FlowforgeAuditChainBroken
      receiver: 'pagerduty-security'
      repeat_interval: 1h

receivers:
  - name: 'pagerduty-security'
    pagerduty_configs:
      - routing_key: '<your-pd-integration-key>'
        description: '{{ template "pagerduty.default.description" . }}'
        severity: critical

  - name: 'default'
    slack_configs:
      - api_url: '<your-slack-webhook-url>'
        channel: '#flowforge-alerts'
```

### 5.4 Incident Response: Audit Log as Reconstruction Tool

The `ff_audit_events` table is the primary incident reconstruction tool. Every workflow state transition, RBAC decision, and admin action is recorded with `actor_user_id`, `kind`, `subject_id`, and `occurred_at`.

**Incident reconstruction query template:**

```sql
-- Reconstruct all activity around a suspicious event
WITH incident_window AS (
    SELECT
        event_id,
        tenant_id,
        actor_user_id,
        kind,
        subject_kind,
        subject_id,
        occurred_at,
        payload,
        row_sha256
    FROM ff_audit_events
    WHERE occurred_at BETWEEN
        '2026-01-10 14:00:00+00'::timestamptz - INTERVAL '15 minutes'
        AND
        '2026-01-10 14:00:00+00'::timestamptz + INTERVAL '1 hour'
    ORDER BY occurred_at
)
SELECT * FROM incident_window;
```

**Check for gaps in the audit timeline** (a gap may indicate deleted rows — the DELETE trigger should prevent this, but check after any restore):

```sql
SELECT
    lag(occurred_at) OVER (PARTITION BY tenant_id ORDER BY ordinal) AS prev_at,
    occurred_at,
    event_id,
    ordinal,
    ordinal - lag(ordinal) OVER (PARTITION BY tenant_id ORDER BY ordinal) AS ordinal_gap
FROM ff_audit_events
WHERE tenant_id = 'your-tenant-id'
ORDER BY ordinal;
-- Any ordinal_gap > 1 indicates a potential deletion
```

---

## 6. Dependency Security

### 6.1 Pin All Dependencies with Hashes

`uv.lock` pins every transitive dependency with content hashes. This prevents supply-chain substitution attacks.

```bash
# Verify the lockfile is present and contains hashes
grep -c "sha256" uv.lock

# Sync from lockfile (use frozen in CI — fails if lockfile is out of date)
uv sync --frozen
```

Never run `uv sync` without `--frozen` in CI. Use `--frozen` to catch any drift between `pyproject.toml` and `uv.lock`.

### 6.2 Run `pip-audit` in CI

`pip-audit` is step 6/19 in `scripts/check_all.sh`. It scans for known CVEs in all transitive dependencies. Run it locally before merging:

```bash
uv run --with pip-audit pip-audit \
  --skip-editable \
  --format columns

# JSON output for evidence package
uv run --with pip-audit pip-audit \
  --skip-editable \
  --format json \
  --output pip-audit-$(date +%Y%m%d).json
```

A non-zero exit code from `pip-audit` blocks the build. CVEs must be remediated (dependency upgrade) or formally accepted in a security review before they can be added to a suppression list.

### 6.3 SBOM Generation

Generate a Software Bill of Materials for each release:

```bash
# Export all dependencies as requirements.txt, then audit
uv export --format requirements-txt --no-hashes \
  | pip-audit --requirement /dev/stdin --format json \
  > sbom-$(date +%Y%m%d).json

# Full requirements with hashes (for supply-chain attestation)
uv export --format requirements-txt \
  > requirements-hashed-$(date +%Y%m%d).txt
```

Include the SBOM in your SOC 2 evidence package for CC9.1 (vendor/dependency risk management).

### 6.4 JS Workspace Dependency Audit

```bash
# Audit the JS workspace dependencies
cd js && pnpm audit --audit-level=high

# Fix known vulnerabilities
pnpm audit --fix
```

Include the JS audit output alongside the Python audit in the evidence package.

---

## 7. Compliance-Specific Settings

### 7.1 SOC 2

**Required configuration:**

1. `validate_production_config(required_ports=("tenancy","rbac","audit","outbox","rls","signing"))` — ensures the signing port is wired for tamper-evident audit records.
2. `PgAuditSink.verify_chain()` on a daily schedule — hash chain integrity verification.
3. `AwsKmsSigning` with automatic key rotation enabled.
4. The 5 CI ratchets passing on every commit.
5. `pip-audit` with zero critical CVEs.

**Evidence to collect quarterly:**
- Audit chain verification output (must show `ok=True`)
- `flowforge_audit_chain_breaks_total` counter (must be 0)
- `flowforge_signing_secret_default_used_total` counter (must be 0)
- SpiceDB relationship snapshot
- `pip-audit` JSON output
- Ratchet check output

### 7.2 GDPR

**Per-tenant data deletion procedure:**

When a subject requests erasure under GDPR Article 17:

1. Identify all `tenant_id` and `actor_user_id` values associated with the subject.
2. Redact PII fields from the audit log (preserving the hash chain):

```python
count = await sink.redact(
    paths=[
        "payload.email",
        "payload.name",
        "payload.phone",
        "payload.address",
        "payload.ip_address",
    ],
    reason=f"GDPR Art.17 erasure — subject={subject_id}, ticket={ticket_id}",
)
```

3. Delete (or tombstone) workflow instance data scoped to the tenant. Because RLS uses `tenant_id`, you can safely delete by tenant:

```sql
-- Soft-delete workflow instances for the subject
UPDATE workflow_instances
SET state = 'erased', payload = '{}'::jsonb, updated_at = NOW()
WHERE tenant_id = :tenant_id
  AND payload->>'subject_id' = :subject_id;
```

4. Cardholder data and other regulated categories: use the `payload` redaction path above. Do not store regulated data in `audit_events.payload` unredacted — redact at the application layer before calling `config.audit.record()`.

5. Document the erasure in your GDPR log with a record of which `event_id`s were affected.

**Data residency:** `PgAuditSink` stores data in the Postgres instance you configure. Ensure your Postgres deployment is in the required geographic region before onboarding GDPR-regulated tenants.

### 7.3 PCI DSS

**Cardholder data protection:**

PCI DSS Requirement 3 prohibits storing sensitive authentication data (SAD) after authorization. flowforge's audit log stores the `payload` of every workflow event.

**Critical rule:** Never pass cardholder data (PAN, CVV, track data) directly into `audit_events.payload`. Redact before calling `config.audit.record()`:

```python
# Correct: redact before recording
audit_payload = {
    "order_id": order.id,
    "amount_cents": charge.amount,
    "pan_last4": card.last4,       # last 4 digits only — PCI DSS compliant
    # "pan": card.pan              # NEVER — full PAN in audit log
    # "cvv": card.cvv              # NEVER — SAD in audit log
}
await config.audit.record(AuditEvent(
    kind="payment.charge.completed",
    payload=audit_payload,
    ...
))
```

**Payment workflow step data:** The `workflow_instances.payload` JSON column must not contain full PAN values. Tokenize using your payment processor's vault (Stripe, Braintree) before storing any reference in the workflow.

**Scope reduction:** If flowforge is deployed on a Kubernetes cluster that also hosts cardholder data systems, the PCI DSS scope applies to the entire cluster. Isolate flowforge to a separate namespace or cluster if possible.

### 7.4 HIPAA

**PHI in workflow payloads:**

Protected Health Information (PHI) must be encrypted at rest and in transit. The framework itself does not encrypt column values — use Postgres Transparent Data Encryption (TDE) or column-level encryption (e.g., `pgcrypto`) at the database layer.

For audit log payloads containing PHI, use the same redaction approach as PCI DSS: redact before recording, and store only de-identified references.

---

## 8. Security Ratchets (CI Enforcement)

The ratchet system is a grep-based CI gate that prevents regression of fixed security findings. Each ratchet is a shell script under `scripts/ci/ratchets/`. They run as part of `make audit-2026` and block merges on failure.

### 8.1 Active Ratchets

| Ratchet Script | Finding | What It Bans |
|---|---|---|
| `no_default_secret.sh` | SK-01 (E-34) | The literal string `flowforge-dev-secret-not-for-production` in committed code |
| `no_string_interp_sql.sh` | T-01, J-01, OB-01 | f-string / `.format()` / `%` SQL construction (parameterized queries only) |
| `no_eq_compare_hmac.sh` | NM-01 (E-54) | `==` comparison against HMAC digests or `.hexdigest()` output; mandates `hmac.compare_digest` |
| `no_except_pass.sh` | J-10, JH-06, CL-04 | `except Exception: pass` (bare exception swallowing) |
| `no_idempotency_bypass.sh` | CL-04 | Bypassing the idempotency key check in outbox dispatch |

Additionally, the JS workspace has:

| Ratchet Script | What It Bans |
|---|---|
| `no_design_token_hardcode.sh` | Hardcoded hex color values outside of design token files |
| `no_unparried_expr_in_step_template.sh` | Expression interpolation in step templates without cross-runtime parity fixture |
| `no_orphan_promql_metrics.sh` | PromQL references to metric names not emitted by the framework |

### 8.2 How to Run the Ratchets

```bash
# Run all ratchets
bash scripts/ci/ratchets/check.sh

# Run a single ratchet
bash scripts/ci/ratchets/no_eq_compare_hmac.sh

# Non-zero exit code means new violations exist outside baseline.txt
```

### 8.3 How to Add a New Ratchet

When fixing a new security finding, add a ratchet to prevent regression:

1. **Write the ratchet script** in `scripts/ci/ratchets/<ratchet_name>.sh`. Follow the existing pattern:

```bash
#!/usr/bin/env bash
# scripts/ci/ratchets/no_plaintext_jwt.sh
# Ratchet for finding JWT-01: JWT tokens must not be logged in plaintext.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

VIOLATIONS=$(git grep -rn \
    --include="*.py" \
    'logger.*jwt\|log.*jwt\|print.*jwt' \
    -- ':!scripts/ci/ratchets' \
    ':!tests/' \
    | grep -v '# noqa' || true)

BASELINE_SECTION=$(awk '/^## ratchet=no_plaintext_jwt/,/^## ratchet=/' \
    scripts/ci/ratchets/baseline.txt | grep -v '^#' | grep -v '^##' || true)

NEW_VIOLATIONS=$(comm -23 \
    <(echo "$VIOLATIONS" | sort) \
    <(echo "$BASELINE_SECTION" | sort))

if [[ -n "$NEW_VIOLATIONS" ]]; then
    echo "FAIL: no_plaintext_jwt — new violations:"
    echo "$NEW_VIOLATIONS"
    echo "Add to baseline.txt with security-team review, or fix the violation."
    exit 1
fi
echo "OK: no_plaintext_jwt"
```

2. **Register the ratchet** by adding its name to the `RATCHETS=()` array in `scripts/ci/ratchets/check.sh`.

3. **Add a baseline section** in `scripts/ci/ratchets/baseline.txt`:

```
## ratchet=no_plaintext_jwt
# (finding JWT-01) JWT tokens must not appear in log output.
# No exceptions currently approved.
```

4. **Update the README** at `scripts/ci/ratchets/README.md` with a row in the table.

5. **Write the signoff test** at `tests/audit_2026/test_JWT_01_no_plaintext_jwt.py` and add a row to `docs/audit-2026/signoff-checklist.md`. Run `make audit-2026-signoff` to verify.

### 8.4 Updating the Baseline for Legitimate Exceptions

If a pattern must exist for a legitimate reason (e.g., a test that verifies the dev-secret warning is emitted):

1. Run the ratchet to get the exact `path:line:matched_text` string.
2. Add the line to the correct `## ratchet=<name>` section in `baseline.txt`.
3. Get security-team review of the PR (required — the `check_signoff.py` gate enforces this for security-tagged findings).
4. Document the rationale as a comment in `baseline.txt`.

```
## ratchet=no_default_secret
# Legitimate occurrences — each requires security-team review in the PR.
python/flowforge-signing-kms/src/flowforge_signing_kms/hmac_dev.py:38:_LEGACY_DEFAULT_SECRET: Final = "flowforge-dev-secret-not-for-production"
```

---

## Appendix A: Security Finding Reference

| Finding ID | Description | Package | Status |
|---|---|---|---|
| SK-01 | No implicit signing default — `HmacDevSigning` raises without `FLOWFORGE_SIGNING_SECRET` | `flowforge-signing-kms` | Fixed (E-34) |
| SK-02 | Per-key-ID signed key map — `verify()` raises `UnknownKeyId` for unknown keys | `flowforge-signing-kms` | Fixed (E-34) |
| SK-03 | KMS error classification — transient vs. permanent vs. unknown-key | `flowforge-signing-kms` | Fixed (E-56) |
| SK-04 | Async KMS calls — `asyncio.to_thread` for blocking boto3/gRPC calls | `flowforge-signing-kms` | Fixed (E-56) |
| NM-01 | `hmac.compare_digest` everywhere — no `==` on HMAC output | Multiple | Fixed + ratchet |
| T-01 | No f-string SQL in tenancy GUC binder | `flowforge-tenancy` | Fixed + ratchet |
| J-01 | No f-string SQL in JTBD queries | `flowforge-jtbd` | Fixed + ratchet |
| OB-01 | No f-string SQL in outbox | `flowforge-outbox-pg` | Fixed + ratchet |
| BLK-01 | Extractor fault → 503, not auth bypass | `flowforge-jtbd-hub` | Fixed |
| FA-01 | Base64 padding canonicalization in `CookiePrincipalExtractor` | `flowforge-fastapi` | Fixed (E-41) |
| FA-02 | `issue_csrf_token(secure=True)` default; `ConfigError` on `secure=False` | `flowforge-fastapi` | Fixed (E-41) |
| FA-03 | `WSPrincipalExtractor` takes `WebSocket` directly | `flowforge-fastapi` | Fixed (E-41) |
| FA-06 | `iat`/`exp` in cookie payload; expired cookies rejected | `flowforge-fastapi` | Fixed (E-41) |
| C-04 | `ConcurrentFireRejected` — per-instance serialization | `flowforge` (core) | Fixed (E-32) |
| AU-01 | Per-tenant advisory lock on audit insert | `flowforge-audit-pg` | Fixed (E-37) |
| AU-02 | Chunked chain verification — bounded memory | `flowforge-audit-pg` | Fixed (E-37) |
| AU-04 | ISO-8601 datetime parsing in `verify_chain` — rejects UUID-shaped event IDs | `flowforge-audit-pg` | Fixed (E-60) |
| H-03 | `EmailAdapter` raises on `SMTP_HOST=localhost` or `SMTP_FROM=noreply@example.com` | `flowforge-notify-multichannel` | Fixed |
| H-04 | `SESEmailAdapter` raises on `SES_FROM_ADDRESS=noreply@example.com` | `flowforge-notify-multichannel` | Fixed |
| E-35 | Expression operator registry frozen at module init | `flowforge` (core) | Fixed |
| E-61 | Copy-on-read snapshot store | `flowforge` (core) | Fixed |

---

## Appendix B: Minimum Production Environment Variables

The following environment variables must be set in production. Missing or placeholder values cause startup failures.

```bash
# Signing (required — use KMS ARN, not FLOWFORGE_SIGNING_SECRET)
KMS_SIGNING_KEY_ARN=arn:aws:kms:us-east-1:123456789:alias/flowforge-signing
AWS_REGION=us-east-1

# Database
DATABASE_URL=postgresql+asyncpg://flowforge_app:${DB_PASSWORD}@db.internal/flowforge

# Session cookie (if using CookiePrincipalExtractor)
SESSION_COOKIE_SECRET=<32+ random bytes, base64-encoded>

# Email (if using EmailAdapter)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=${SENDGRID_API_KEY}
SMTP_FROM=noreply@yourdomain.com  # must not be noreply@example.com

# Email (if using SESEmailAdapter)
SES_REGION=us-east-1
SES_FROM_ADDRESS=noreply@yourdomain.com  # must not be noreply@example.com

# Webhooks (if using WebhookAdapter)
WEBHOOK_HMAC_SECRET=<32+ random bytes, hex-encoded>
WEBHOOK_ALLOWED_HOSTS=hooks.stripe.com,api.github.com

# SpiceDB (if using flowforge-rbac-spicedb)
SPICEDB_ENDPOINT=spicedb.internal:50051
SPICEDB_TOKEN=${SPICEDB_PSK}
```

**Never set these in production:**
- `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1`
- `FLOWFORGE_SIGNING_SECRET=flowforge-dev-secret-not-for-production`

---

*This guide has been refreshed for the v0.5.x package line. Re-review before each minor release, particularly sections covering KMS adapter behaviour, the signing port protocol, FastAPI authentication, tenant resolution, and production port validation.*
