# SOC 2 Type II Evidence Guide for flowforge Deployments

**Version:** 0.5.x documentation baseline
**Audience:** Security auditors, compliance officers, enterprise security teams  
**Scope:** flowforge-core and its adapter packages deployed as a production workflow engine

---

## Table of Contents

1. [Overview](#overview)
2. [SOC 2 Criteria Coverage Matrix](#soc-2-criteria-coverage-matrix)
3. [Evidence Collection Procedures](#evidence-collection-procedures)
   - [CC1 — Control Environment](#cc1--control-environment)
   - [CC2 — Communication and Information](#cc2--communication-and-information)
   - [CC3 — Risk Assessment](#cc3--risk-assessment)
   - [CC4 — Monitoring Activities](#cc4--monitoring-activities)
   - [CC5 — Control Activities](#cc5--control-activities)
   - [CC6 — Logical and Physical Access](#cc6--logical-and-physical-access)
   - [CC7 — System Operations](#cc7--system-operations)
   - [CC8 — Change Management](#cc8--change-management)
   - [CC9 — Risk Mitigation](#cc9--risk-mitigation)
   - [A1 — Availability](#a1--availability)
   - [C1 — Confidentiality](#c1--confidentiality)
   - [PI1 — Processing Integrity](#pi1--processing-integrity)
4. [Evidence Export Scripts](#evidence-export-scripts)
5. [Audit Readiness Checklist](#audit-readiness-checklist)
6. [Penetration Testing Guidance](#penetration-testing-guidance)

---

## Overview

flowforge is a portable workflow engine that ships 15 hexagonal-architecture port ABCs. Each port maps directly to a SOC 2 control area. This guide explains which framework capabilities satisfy which Trust Service Criteria (TSC) and how to extract evidence for each.

### Framework Components Referenced

| Package | Purpose | SOC 2 Relevance |
|---|---|---|
| `flowforge` (core) | Engine, ports, expression evaluator | PI1, A1, CC7 |
| `flowforge-audit-pg` | Append-only audit log with SHA-256 hash chain | PI1, CC6, CC7 |
| `flowforge-signing-kms` | HMAC-SHA256 / AWS KMS / GCP KMS signing | CC6, PI1 |
| `flowforge-tenancy` | Postgres RLS via `set_config` GUCs | C1, CC6 |
| `flowforge-rbac-spicedb` | SpiceDB-backed RBAC resolver | CC5, CC6 |
| `flowforge-fastapi` | HTTP adapter with CSRF, principal extraction | CC6, CC5 |
| `flowforge-outbox-pg` | Transactional outbox with DLQ | CC7, A1 |
| `flowforge-notify-multichannel` | Email/webhook/Slack notifications | CC2, CC7 |

---

## SOC 2 Criteria Coverage Matrix

| Criteria | Description | flowforge Control | Strength |
|---|---|---|---|
| **CC1.1** | Integrity and ethical values | Org policy; code of conduct | Organizational |
| **CC1.2** | Board oversight | Audit committee; security review gate | Organizational |
| **CC1.3** | Org structure and reporting | RBAC roles in SpiceDB; audit log by actor | Technical + Org |
| **CC1.4** | Commitment to competence | CI gate with `make audit-2026`; ratchet scripts | Technical |
| **CC1.5** | Accountability | `actor_user_id` in every `ff_audit_events` row | Technical |
| **CC2.1** | Information quality | Canonical JSON audit chain; hash verification | Technical |
| **CC2.2** | Internal communication | Incident runbook in `docs/`; git history | Organizational |
| **CC2.3** | External communication | SLA metrics exposed via Prometheus | Technical |
| **CC3.1** | Risk identification | `pip-audit` in CI; dependency CVE scanning | Technical |
| **CC3.2** | Risk assessment | `docs/audit-fix-plan.md` finding severity ratings | Organizational |
| **CC3.3** | Risk response | Conformance tests enforce arch invariants | Technical |
| **CC4.1** | Monitoring design | `flowforge.fire.duration_seconds` histogram | Technical |
| **CC4.2** | Monitoring evaluation | `flowforge_audit_chain_breaks_total` counter | Technical |
| **CC5.1** | Control selection | `validate_production_config()` at startup | Technical |
| **CC5.2** | Control design | CSRF double-submit-cookie; RBAC on every route | Technical |
| **CC5.3** | Control deployment | Ratchet CI scripts (5 active ratchets) | Technical |
| **CC6.1** | Logical access | `PrincipalExtractor` protocol; JWT + cookie auth | Technical |
| **CC6.2** | Access provisioning | SpiceDB relationship tuples; admin audit trail | Technical |
| **CC6.3** | Access removal | SpiceDB relationship deletion; audit record | Technical |
| **CC6.4** | Access credentials | `AwsKmsSigning` / `GcpKmsSigning`; no defaults | Technical |
| **CC6.5** | Physical access | Hosting-provider SLA; out of framework scope | Organizational |
| **CC6.6** | Logical access controls | RBAC resolver on every `fire()` call | Technical |
| **CC6.7** | Transmission integrity | TLS; HMAC signature on webhook payloads | Technical |
| **CC6.8** | Data destruction | `redact()` tombstone; GDPR-safe hash chain | Technical |
| **CC7.1** | Vulnerability mgmt | `pip-audit` + `no_default_secret` ratchet in CI | Technical |
| **CC7.2** | Environmental threats | Saga compensation; outbox DLQ monitoring | Technical |
| **CC7.3** | Continuous monitoring | Prometheus metrics; Alertmanager rules | Technical |
| **CC7.4** | Incident detection | `flowforge_audit_chain_breaks_total` alert | Technical |
| **CC7.5** | Incident response | Incident runbook; audit log actor trail | Organizational |
| **CC8.1** | Change management | Alembic migrations; JTBD lockfile hash | Technical |
| **CC8.2** | Change authorization | PR review gate; `make audit-2026-signoff` | Technical |
| **CC9.1** | Vendor risk | `uv.lock` hash-pinned dependencies | Technical |
| **CC9.2** | Business continuity | Saga compensation; snapshot restore | Technical |
| **A1.1** | Availability commitments | Uptime SLO; Prometheus scrape targets | Technical |
| **A1.2** | Capacity management | `flowforge.fire.duration_seconds` p95 alerts | Technical |
| **A1.3** | Environmental threats | Concurrent-fire rejection; idempotency | Technical |
| **C1.1** | Confidentiality policy | Per-tenant RLS via Postgres GUCs | Technical |
| **C1.2** | Confidentiality of data | `app.tenant_id` GUC; RLS policies | Technical |
| **PI1.1** | Processing integrity | Hash chain; `ConcurrentFireRejected` | Technical |
| **PI1.2** | Complete processing | Outbox drain; saga replay on restart | Technical |
| **PI1.3** | Accurate processing | `hmac.compare_digest` everywhere; no timing attacks | Technical |
| **PI1.4** | Authorized processing | RBAC check before every `fire()` | Technical |
| **PI1.5** | Timely processing | SLA deadline engine; DLQ depth alerts | Technical |

---

## Evidence Collection Procedures

### CC1 — Control Environment

**What auditors look for:** Evidence that the organization has defined policies, accountability structures, and commits to competence.

**flowforge evidence sources:**

1. **Actor accountability** — every row in `ff_audit_events` carries `actor_user_id`. Query to verify no anonymous mutations exist in production:

```sql
SELECT COUNT(*) AS anonymous_mutations
FROM ff_audit_events
WHERE actor_user_id IS NULL
  AND kind NOT IN ('system.startup', 'system.health_check');
```

2. **RBAC roles** — SpiceDB relationship tuples document who has which role. Export via the SpiceDB `relationships/read` API (see CC6 section).

3. **CI gate** — `make audit-2026` enforces all audit-2026 findings. Evidence: CI build logs from the audit period. Each finding has a corresponding test in `tests/audit_2026/test_<FINDING>_*.py`.

4. **Org policy documents** — store in `docs/policies/`. Reference in the evidence package with commit SHA and date.

---

### CC2 — Communication and Information

**What auditors look for:** That information flows reliably between stakeholders; that incidents are communicated.

**flowforge evidence sources:**

1. **Incident response runbook** — maintain at `docs/incident-response-runbook.md`. Reference the audit log as the primary incident reconstruction tool:

```bash
# Reconstruct a specific incident window
psql $DATABASE_URL -c "
SELECT occurred_at, actor_user_id, kind, subject_kind, subject_id, payload
FROM ff_audit_events
WHERE occurred_at BETWEEN '2026-01-10 14:00:00+00' AND '2026-01-10 15:00:00+00'
ORDER BY occurred_at;
"
```

2. **Change management records** — git history is the authoritative change record. Export the commit log for the audit period:

```bash
git log --since="2026-01-01" --until="2026-12-31" \
  --format="%H %ai %ae %s" \
  -- python/ js/ | tee audit-period-commits.txt
```

3. **Version release records** — each release is tagged. List all tags in the audit period:

```bash
git tag --sort=creatordate | grep -E "^v0\." \
  | xargs -I{} git log -1 --format="{} %ai %ae" {}
```

---

### CC3 — Risk Assessment

**What auditors look for:** Systematic identification and assessment of risks; evidence of remediation.

**flowforge evidence sources:**

1. **Dependency CVE scan** — `pip-audit` runs as step 6/19 in `scripts/check_all.sh`. Extract evidence:

```bash
# Run pip-audit and save output for the evidence package
uv run --with pip-audit pip-audit \
  --skip-editable \
  --format json \
  --output audit-period-pip-audit-$(date +%Y%m%d).json
```

2. **Audit finding log** — `docs/audit-fix-plan.md` is the authoritative risk register. Each finding has a severity rating (P0/P1/P2), an audit reference (C-01, T-01, etc.), and a remediation status. Present this document as the risk assessment record.

3. **Conformance test results** — the 8 architectural invariants in `tests/conformance/` are the technical risk controls. Run and capture output:

```bash
uv run pytest tests/conformance/ -v \
  --tb=short 2>&1 | tee audit-conformance-$(date +%Y%m%d).txt
```

4. **Ratchet scan results** — the 5 active ratchets detect regression of fixed issues:

```bash
bash scripts/ci/ratchets/check.sh 2>&1 | tee audit-ratchets-$(date +%Y%m%d).txt
```

---

### CC4 — Monitoring Activities

**What auditors look for:** That controls are monitored for effectiveness; anomalies are detected.

**flowforge evidence sources:**

The framework emits Prometheus-compatible metrics. The canonical metric names are:

| Metric | Type | What It Monitors |
|---|---|---|
| `flowforge.fire.duration_seconds` | Histogram | Engine transaction latency |
| `flowforge_engine_fire_rejected_concurrent_total` | Counter | Lock-contention events |
| `flowforge.outbox.dispatch.duration_seconds` | Histogram | Outbox drain latency |
| `flowforge.audit.append.duration_seconds` | Histogram | Audit write latency |
| `flowforge_audit_chain_breaks_total` | Counter | Tampered audit rows |
| `flowforge_signing_secret_default_used_total` | Counter | Insecure-default signing key used |
| `flowforge_kms_transient_errors_total` | Counter | KMS infrastructure errors |
| `flowforge_audit_record_unique_violation_total` | Counter | Concurrent-insert conflicts |
| `flowforge_fastapi_csrf_config_error_total` | Counter | CSRF misconfiguration |

**Evidence collection:**

1. **Grafana dashboard snapshots** — export as JSON and include in the evidence package. The dashboard must show the `flowforge.fire.duration_seconds` p95 over the audit period.

2. **Prometheus alert rule export:**

```bash
# Export current alerting rules (requires promtool)
promtool check rules /etc/prometheus/rules/flowforge.yml
curl -s http://prometheus:9090/api/v1/rules | jq '.data.groups' \
  > audit-alert-rules-$(date +%Y%m%d).json
```

3. **Alert firing history** — export from Alertmanager:

```bash
curl -s http://alertmanager:9093/api/v2/alerts?active=false \
  | jq '[.[] | select(.labels.alertname | startswith("flowforge"))]' \
  > audit-alert-history-$(date +%Y%m%d).json
```

4. **Histogram evidence** — show the p95 fire duration over the audit period. A p95 under 500ms demonstrates the engine is performing within SLO:

```bash
# Query Prometheus for p95 over audit period
curl -s "http://prometheus:9090/api/v1/query_range?query=histogram_quantile(0.95,rate(flowforge_fire_duration_seconds_bucket[5m]))&start=2026-01-01T00:00:00Z&end=2026-12-31T23:59:59Z&step=3600" \
  > audit-fire-p95-$(date +%Y%m%d).json
```

---

### CC5 — Control Activities

**What auditors look for:** That controls are selected, designed, and deployed to achieve objectives.

**flowforge evidence sources:**

1. **Production config validation** — call `validate_production_config()` at startup. This verifies that all required ports are wired. The default required ports are `("tenancy", "rbac", "audit", "outbox", "rls")`. For SOC 2 + signing evidence:

```python
from flowforge.config import validate_production_config

# SOC 2 deployment: include signing port
validate_production_config(
    required_ports=("tenancy", "rbac", "audit", "outbox", "rls", "signing")
)
```

If any port is unwired, `ProductionConfigError` is raised at startup — preventing deployment without controls in place.

2. **RBAC configuration snapshot** — export the SpiceDB relationship tuples for the audit period. See CC6 for the export script.

3. **CSRF protection evidence** — the `flowforge_fastapi_csrf_config_error_total` counter measures misconfiguration attempts. A zero count over the audit period is evidence that no insecure CSRF configurations were deployed:

```bash
curl -s "http://prometheus:9090/api/v1/query?query=flowforge_fastapi_csrf_config_error_total" \
  | jq '.data.result'
```

4. **Ratchet baseline** — `scripts/ci/ratchets/baseline.txt` documents every exception to the 5 active ratchets. Present this file (with git blame) as evidence that exceptions are reviewed.

---

### CC6 — Logical and Physical Access

**What auditors look for:** Access is restricted to authorized users; credentials are managed; transmissions are protected.

**flowforge evidence sources:**

1. **JWT signing key rotation records** — when using `AwsKmsSigning`, key rotation is logged in AWS CloudTrail. Export:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RotateKey \
  --start-time 2026-01-01T00:00:00Z \
  --end-time 2026-12-31T23:59:59Z \
  --output json > audit-kms-rotations-$(date +%Y%m%d).json
```

2. **HMAC `compare_digest` usage** — the `no_eq_compare_hmac` ratchet (`scripts/ci/ratchets/no_eq_compare_hmac.sh`) enforces timing-safe HMAC comparison. Present the ratchet pass output as evidence.

   All HMAC verification in the framework uses `hmac.compare_digest`:
   - `flowforge_fastapi/auth.py`: `CookiePrincipalExtractor.verify()` and `csrf_protect()`
   - `flowforge_signing_kms/hmac_dev.py`: `HmacDevSigning.verify()`

3. **Audit hash chain** — the `ff_audit_events.row_sha256` column forms a tamper-evident chain. Verification:

```bash
# Via the PgAuditSink.verify_chain() method (Python)
python - <<'EOF'
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from flowforge_audit_pg import PgAuditSink

async def verify():
    engine = create_async_engine("postgresql+asyncpg://...")
    sink = PgAuditSink(engine)
    verdict = await sink.verify_chain()
    print(f"Chain OK: {verdict.ok}, rows checked: {verdict.rows_checked}")
    if not verdict.ok:
        print(f"First bad event_id: {verdict.first_bad_event_id}")

asyncio.run(verify())
EOF
```

4. **SpiceDB RBAC snapshot** — export current relationships for evidence:

```bash
# Using grpcurl against the SpiceDB permissions API
grpcurl -plaintext spicedb:50051 \
  authzed.api.v1.PermissionsService/ReadRelationships \
  -d '{"consistency": {"fully_consistent": true}}' \
  > audit-spicedb-relationships-$(date +%Y%m%d).json
```

5. **Access review records** — run a quarterly query to list all principals with elevated roles:

```sql
-- List all actors who performed privileged operations in the audit period
SELECT DISTINCT actor_user_id, kind, COUNT(*) as action_count
FROM ff_audit_events
WHERE occurred_at BETWEEN '2026-01-01' AND '2026-12-31'
  AND kind LIKE 'admin.%'
GROUP BY actor_user_id, kind
ORDER BY actor_user_id;
```

6. **Admin audit logs** — extract all admin-role actions:

```sql
SELECT event_id, tenant_id, actor_user_id, kind, subject_kind,
       subject_id, occurred_at, payload
FROM ff_audit_events
WHERE kind LIKE 'admin.%'
  AND occurred_at BETWEEN '2026-01-01' AND '2026-12-31'
ORDER BY occurred_at;
```

---

### CC7 — System Operations

**What auditors look for:** Systems operate as intended; vulnerabilities are identified and addressed.

**flowforge evidence sources:**

1. **Outbox drain worker uptime** — the outbox worker processes messages transactionally. Evidence that messages are not silently lost:

```sql
-- Count messages remaining in outbox by age bucket
SELECT
  CASE
    WHEN now() - created_at < INTERVAL '5 minutes' THEN 'recent'
    WHEN now() - created_at < INTERVAL '1 hour' THEN 'pending'
    ELSE 'stale'
  END AS age_bucket,
  status,
  COUNT(*) as cnt
FROM ff_outbox_envelopes
GROUP BY age_bucket, status
ORDER BY age_bucket, status;
```

2. **DLQ monitoring evidence** — stale outbox messages are a DLQ proxy. Alert rule evidence:

```yaml
# prometheus/rules/flowforge.yml
groups:
  - name: flowforge_outbox
    rules:
      - alert: FlowforgeOutboxDLQDepth
        expr: |
          sum(flowforge_outbox_dlq_depth) > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Outbox DLQ has stuck messages"
          description: "{{ $value }} messages in DLQ for > 5 minutes"
```

3. **Outbox worker health endpoint** — `flowforge-outbox-pg` exposes a health check. Uptime monitoring evidence:

```bash
# Check outbox worker health
curl -s http://outbox-worker:8080/health | jq .
```

4. **Vulnerability management evidence** — `pip-audit` result from CI (see CC3). Additionally, show that the `no_default_secret` ratchet passes, confirming no hardcoded secrets in the codebase.

5. **System event log** — application startup logs `validate_production_config()` results. Collect via your log aggregator (Loki, CloudWatch, etc.):

```bash
# Loki query for startup validation failures (should be 0 in production)
logcli query '{app="flowforge"} |= "ProductionConfigError"' \
  --from="2026-01-01T00:00:00Z" --to="2026-12-31T23:59:59Z"
```

---

### CC8 — Change Management

**What auditors look for:** Changes are authorized, tested, and deployed in a controlled manner.

**flowforge evidence sources:**

1. **Alembic migration history** — every schema change is tracked in Alembic's revision table:

```sql
SELECT version_num, is_current
FROM alembic_version;

-- Full migration history (if you track applied timestamps separately)
SELECT *
FROM alembic_version_history
ORDER BY applied_at;
```

2. **JTBD lockfile hash evidence** — `JtbdLockfile` pins the spec hash of each JTBD bundle. Changes require a new lockfile entry, creating an auditable trail:

```bash
# Show JTBD lockfile contents
cat examples/*/jtbd.lock.json | python -m json.tool

# Verify lockfile hashes are current
uv run flowforge jtbd lint examples/*/bundle.json
```

3. **Git tag evidence for version pinning** — every production deployment must correspond to a tagged release:

```bash
# List all tagged releases with their commit SHAs
git tag --sort=creatordate -l "v*" | while read tag; do
  echo "$tag $(git rev-list -n1 $tag) $(git log -1 --format='%ai' $tag)"
done
```

4. **PR review gate** — `make audit-2026-signoff` enforces that every audit finding has a corresponding acceptance test. Present CI run outputs for the audit period showing this gate passing.

5. **Regen determinism** — `scripts/check_all.sh` step 8 diffs generated output against a fresh regen. A passing CI run over the audit period demonstrates no manual mutations to generated code.

---

### CC9 — Risk Mitigation

**What auditors look for:** Risks are mitigated through vendor management, business continuity planning, and compensating controls.

**flowforge evidence sources:**

1. **Saga compensation ledger** — `workflow_saga_steps` table records every saga step and its compensation status. Evidence that compensation runs on failure:

```sql
-- Count saga steps by status over the audit period
SELECT
  status,
  COUNT(*) as count,
  MIN(created_at) as earliest,
  MAX(created_at) as latest
FROM workflow_saga_steps
WHERE created_at BETWEEN '2026-01-01' AND '2026-12-31'
GROUP BY status
ORDER BY count DESC;
```

2. **Rollback audit rows** — when a fire() fails after phase 1, the pre-fire snapshot is restored and an audit row is recorded. Query rollback events:

```sql
SELECT event_id, tenant_id, actor_user_id, kind, occurred_at, payload
FROM ff_audit_events
WHERE kind IN ('workflow.fire.rollback', 'workflow.fire.snapshot_restored',
               'workflow.compensation.executed')
  AND occurred_at BETWEEN '2026-01-01' AND '2026-12-31'
ORDER BY occurred_at;
```

3. **Snapshot integrity** — the engine uses copy-on-read snapshots (E-61). The snapshot store is tested under `tests/conformance/` invariant 6. Present conformance test output as evidence.

4. **Vendor/dependency risk** — `uv.lock` pins all transitive dependencies with content hashes. Present the lockfile as evidence:

```bash
# Show dependency count and confirm hash pinning
grep -c "content-hash\|sha256" uv.lock
wc -l uv.lock
```

---

### A1 — Availability

**What auditors look for:** The system is available for operation as committed or agreed.

**flowforge evidence sources:**

1. **Concurrent-fire rejection counter** — `flowforge_engine_fire_rejected_concurrent_total` measures how many `fire()` calls were rejected due to per-instance serialization. This is a safety control, not a failure. A high rate indicates lock contention worth investigating:

```bash
# Query Prometheus for concurrent-fire rejections over audit period
curl -s "http://prometheus:9090/api/v1/query_range?query=rate(flowforge_engine_fire_rejected_concurrent_total[5m])&start=2026-01-01T00:00:00Z&end=2026-12-31T23:59:59Z&step=3600" \
  | jq '.data.result' > audit-concurrent-rejections-$(date +%Y%m%d).json
```

2. **Uptime SLO evidence** — show the `flowforge.fire.duration_seconds` histogram for the audit period. An SLO of p95 < 500ms is the reference target:

```bash
# Export p50/p95/p99 for the audit period
curl -s "http://prometheus:9090/api/v1/query_range?query=histogram_quantile(0.99,rate(flowforge_fire_duration_seconds_bucket[1h]))&start=2026-01-01T00:00:00Z&end=2026-12-31T23:59:59Z&step=86400" \
  > audit-fire-p99-daily-$(date +%Y%m%d).json
```

3. **Engine availability** — the engine is I/O-free. Availability depends on the Postgres connection and outbox drain worker. Evidence from Postgres uptime monitoring and the outbox worker health check (see CC7).

4. **SLA breach events** — if the SLA deadline engine is deployed, query SLA breach audit rows:

```sql
SELECT event_id, tenant_id, actor_user_id, kind, occurred_at, payload
FROM ff_audit_events
WHERE kind = 'workflow.sla.breach'
  AND occurred_at BETWEEN '2026-01-01' AND '2026-12-31'
ORDER BY occurred_at;
```

---

### C1 — Confidentiality

**What auditors look for:** Information designated as confidential is protected.

**flowforge evidence sources:**

1. **RLS via Postgres GUCs** — `flowforge-tenancy` sets `app.tenant_id` via `SELECT set_config(:k, :v, true)` before any framework query. The bind-parameter form prevents SQL injection (T-01 finding). Evidence:

```sql
-- Verify RLS is enabled on tenant-scoped tables
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE rowsecurity = true
ORDER BY tablename;
```

```sql
-- Verify RLS policies exist
SELECT schemaname, tablename, policyname, cmd, qual
FROM pg_policies
ORDER BY tablename, policyname;
```

2. **Tenant isolation evidence** — run a cross-tenant query test in a staging environment. Confirm that a session with `app.tenant_id = 'tenant-a'` cannot read `tenant-b`'s workflow instances:

```sql
-- Set as tenant-a
SELECT set_config('app.tenant_id', 'tenant-a', true);
SELECT set_config('app.elevated', 'false', true);

-- This should return 0 rows if RLS is enforced
SELECT COUNT(*) FROM workflow_instances WHERE tenant_id = 'tenant-b';
```

3. **GDPR redaction procedure** — the `PgAuditSink.redact()` method writes tombstone markers without breaking the hash chain. Present the redaction log:

```sql
SELECT event_id, occurred_at, payload->>'__redaction_reason__' as reason
FROM ff_audit_events
WHERE payload ? '__redaction_reason__'
ORDER BY occurred_at;
```

4. **Audit payload redaction policy** — document which fields are considered PII and are excluded from audit payloads. The framework never automatically redacts; the host application is responsible for redacting before calling `config.audit.record()`.

---

### PI1 — Processing Integrity

**What auditors look for:** Processing is complete, valid, accurate, timely, and authorized.

**flowforge evidence sources:**

1. **Audit hash chain** — every row in `ff_audit_events` includes `prev_sha256` and `row_sha256 = sha256(prev_sha256 + canonical_json(row))`. Tamper evidence:

```python
# Run full chain verification
verdict = await sink.verify_chain()
# verdict.ok == True  →  chain intact
# verdict.rows_checked  →  number of rows verified
```

2. **`ConcurrentFireRejected` protection** — the engine raises `ConcurrentFireRejected` (C-04 finding) when two `fire()` calls target the same instance concurrently. This prevents duplicate state transitions. Evidence: the `flowforge_engine_fire_rejected_concurrent_total` counter should be low in a well-operated system.

3. **`hmac.compare_digest` in HMAC verification** — all HMAC comparisons use `hmac.compare_digest` to prevent timing attacks (NM-01 finding). The `no_eq_compare_hmac` ratchet enforces this in CI. Present the ratchet pass output.

4. **Expression evaluator freeze** — the `flowforge.expr` evaluator's operator registry is frozen at module init (E-35 finding). No arbitrary Python can be injected via workflow guard expressions. Evidence: the expression evaluator operator whitelist:

```python
from flowforge.expr import OPERATOR_REGISTRY
print(sorted(OPERATOR_REGISTRY.keys()))
```

5. **Outbox at-least-once delivery** — the transactional outbox guarantees that events dispatched during `fire()` are delivered at least once. DLQ depth monitoring (see CC7) is the evidence that stuck messages are detected.

---

## Evidence Export Scripts

The following scripts extract evidence directly from the production database. Run them with appropriate read-only credentials and save output to the evidence package.

### Extract Audit Events for a Date Range

```bash
#!/usr/bin/env bash
# export-audit-events.sh
# Usage: ./export-audit-events.sh 2026-01-01 2026-12-31 output.json

START="${1:-2026-01-01}"
END="${2:-2026-12-31}"
OUTFILE="${3:-audit-events.json}"

psql "$DATABASE_URL" -t -A -F"," -c "
COPY (
  SELECT row_to_json(ae)
  FROM ff_audit_events ae
  WHERE occurred_at >= '${START}'::timestamptz
    AND occurred_at <  '${END}'::timestamptz + INTERVAL '1 day'
  ORDER BY occurred_at, event_id
) TO STDOUT;
" | jq -s '.' > "$OUTFILE"

echo "Exported $(jq length "$OUTFILE") events to $OUTFILE"
```

### Count Unique Actors

```bash
#!/usr/bin/env bash
# count-unique-actors.sh
# Usage: ./count-unique-actors.sh 2026-01-01 2026-12-31

START="${1:-2026-01-01}"
END="${2:-2026-12-31}"

psql "$DATABASE_URL" -c "
SELECT
  actor_user_id,
  COUNT(*)                              AS event_count,
  MIN(occurred_at)                      AS first_action,
  MAX(occurred_at)                      AS last_action,
  COUNT(DISTINCT kind)                  AS distinct_action_types
FROM ff_audit_events
WHERE occurred_at >= '${START}'::timestamptz
  AND occurred_at <  '${END}'::timestamptz + INTERVAL '1 day'
GROUP BY actor_user_id
ORDER BY event_count DESC;
"
```

### Export RBAC Policy Snapshot

```bash
#!/usr/bin/env bash
# export-rbac-snapshot.sh
# Requires: grpcurl, SpiceDB endpoint

SPICEDB_ENDPOINT="${SPICEDB_ENDPOINT:-spicedb:50051}"
OUTFILE="rbac-snapshot-$(date +%Y%m%d).json"

grpcurl -plaintext "$SPICEDB_ENDPOINT" \
  authzed.api.v1.PermissionsService/ReadRelationships \
  -d '{
    "consistency": {"fully_consistent": true},
    "relationship_filter": {}
  }' | jq -s '.' > "$OUTFILE"

echo "RBAC snapshot saved to $OUTFILE"
echo "Total relationships: $(jq length "$OUTFILE")"
```

### List SLA Breach Events

```bash
#!/usr/bin/env bash
# list-sla-breaches.sh
# Usage: ./list-sla-breaches.sh 2026-01-01 2026-12-31

START="${1:-2026-01-01}"
END="${2:-2026-12-31}"

psql "$DATABASE_URL" -c "
SELECT
  event_id,
  tenant_id,
  actor_user_id,
  kind,
  subject_kind,
  subject_id,
  occurred_at,
  payload->>'sla_name'        AS sla_name,
  payload->>'deadline_at'     AS deadline_at,
  payload->>'instance_id'     AS instance_id,
  payload->>'workflow_id'     AS workflow_id
FROM ff_audit_events
WHERE kind IN ('workflow.sla.breach', 'workflow.sla.escalated',
               'workflow.deadline.exceeded')
  AND occurred_at >= '${START}'::timestamptz
  AND occurred_at <  '${END}'::timestamptz + INTERVAL '1 day'
ORDER BY occurred_at;
"
```

### Verify Audit Chain Integrity

```bash
#!/usr/bin/env bash
# verify-audit-chain.sh
# Calls PgAuditSink.verify_chain() via a one-shot Python process.
# Exits 0 if chain is intact, 1 if broken.

python - <<'PYEOF'
import asyncio, sys, os
from sqlalchemy.ext.asyncio import create_async_engine
from flowforge_audit_pg import PgAuditSink

DATABASE_URL = os.environ["DATABASE_URL"]

async def main():
    engine = create_async_engine(DATABASE_URL)
    sink = PgAuditSink(engine)
    verdict = await sink.verify_chain()
    print(f"Chain intact: {verdict.ok}")
    print(f"Rows checked: {verdict.rows_checked}")
    if not verdict.ok:
        print(f"First bad event_id: {verdict.first_bad_event_id}", file=sys.stderr)
        sys.exit(1)

asyncio.run(main())
PYEOF
```

---

## Audit Readiness Checklist

Complete this checklist before the SOC 2 assessment begins. Each item maps to one or more TSC criteria.

| # | Check | TSC | Evidence Location |
|---|---|---|---|
| 1 | `validate_production_config(required_ports=("tenancy","rbac","audit","outbox","rls","signing"))` passes at startup | CC5.1, CC6.4 | Application startup log |
| 2 | `ff_audit_events` table exists with DELETE-blocking trigger installed | PI1.1, CC6 | `\d+ ff_audit_events` + `\dy ff_audit_no_delete_tg` |
| 3 | `PgAuditSink.verify_chain()` returns `ok=True` | PI1.1, CC6.8 | Chain verification script output |
| 4 | No `actor_user_id IS NULL` for non-system events | CC1.5, PI1.4 | Anonymous-mutation query (see CC1) |
| 5 | `pip-audit` passes with zero critical CVEs | CC3.1, CC7.1 | CI step 6/19 log |
| 6 | All 5 ratchets pass (`bash scripts/ci/ratchets/check.sh`) | CC5.3, CC7.1 | Ratchet output |
| 7 | RLS is enabled on all tenant-scoped tables | C1, CC6.6 | `pg_tables.rowsecurity = true` query |
| 8 | `app.tenant_id` RLS policies exist on workflow tables | C1.2, CC6.6 | `pg_policies` query |
| 9 | `AwsKmsSigning` or `GcpKmsSigning` is used (not `HmacDevSigning`) | CC6.4, SK-01 | `FLOWFORGE_SIGNING_SECRET` env var absent; KMS key ARN set |
| 10 | KMS key rotation schedule is documented and active | CC6.4 | AWS CloudTrail / GCP KMS key metadata |
| 11 | `StaticPrincipalExtractor` is NOT used in production routes | CC6.1, BLK-01 | Code review + startup config audit |
| 12 | `issue_csrf_token()` called with `secure=True` (default) | CC5.2, CC6.7 | `flowforge_fastapi_csrf_config_error_total` = 0 |
| 13 | `SMTP_FROM` / `SES_FROM_ADDRESS` are not `noreply@example.com` | CC7, H-03/H-04 | `EmailAdapter` / `SESEmailAdapter` startup (raises `ValueError` if placeholder) |
| 14 | SpiceDB relationships export shows no wildcard `*` permissions | CC6.2, CC5.2 | RBAC snapshot |
| 15 | `workflow_saga_steps` shows all compensations completed | CC9.2, PI1.2 | Saga status query |
| 16 | Outbox DLQ depth = 0 at time of audit | CC7.2, A1, PI1.2 | Prometheus `flowforge_outbox_dlq_depth` |
| 17 | `flowforge_audit_chain_breaks_total` = 0 over audit period | PI1.1, CC7.4 | Prometheus counter |
| 18 | `flowforge_signing_secret_default_used_total` = 0 | CC6.4, SK-01 | Prometheus counter |
| 19 | All Alembic migrations applied in order, no gaps | CC8.1 | `alembic_version` + migration history |
| 20 | `uv.lock` is committed and includes content hashes for all deps | CC9.1, CC3.1 | `grep sha256 uv.lock | wc -l` |

---

## Penetration Testing Guidance

The following areas are highest priority for penetration testing of a flowforge-based deployment. The reference finding IDs map to `docs/audit-fix-plan.md`.

### 1. JWT Validation Bypass (BLK-01)

**Finding:** Pre-fix, a `KmsTransientError` in the JWT extractor caused a silent downgrade to unauthenticated access. The fix (`flowforge-jtbd-hub/jwt_extractor.py` + `app.py`) ensures infrastructure failures surface as HTTP 503, not 401.

**Test approach:**
- Simulate a KMS timeout by blocking the KMS endpoint (network policy or mock).
- Send a request with a valid JWT to a protected endpoint.
- **Expected:** HTTP 503 with `"infrastructure error"` body. Rejection, not silent pass-through.
- **Failure mode:** HTTP 200 or HTTP 401 (which could indicate the request was processed without auth, not rejected).

**Test script:**
```bash
# Block KMS, then test auth endpoint
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer <valid_jwt>" \
  https://your-app/api/workflows/fire
# Must return 503, not 200 or 401
```

### 2. CSRF Protection (`csrf_protect` dependency)

**Finding:** E-41 / FA-02. `issue_csrf_token()` defaults `secure=True`; passing `secure=False` without `dev_mode=True` raises `ConfigError`.

**Test approach:**
- Send a mutating request (POST/PUT/DELETE) without the `X-CSRF-Token` header.
- **Expected:** HTTP 403 Forbidden.
- Send a request where the cookie token and header token differ.
- **Expected:** HTTP 403 Forbidden.
- Verify GET/HEAD/OPTIONS are exempt (no CSRF check required).
- Test cross-origin requests: verify `SameSite=lax` on the CSRF cookie prevents cross-site submission.

**Test script:**
```bash
# POST without CSRF header: expect 403
curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"event":"submit"}' \
  https://your-app/api/workflows/instance/fire
# Expected: 403

# POST with mismatched CSRF: expect 403
curl -s -o /dev/null -w "%{http_code}" \
  -X POST \
  --cookie "flowforge_csrf=abc123" \
  -H "X-CSRF-Token: wrongtoken" \
  https://your-app/api/workflows/instance/fire
# Expected: 403
```

### 3. SQL Injection via Outbox/Audit Paths (T-01, J-01, OB-01)

**Finding:** The `no_string_interp_sql` ratchet bans f-string/`.format()`/`%` SQL. All framework SQL uses parameterized queries via SQLAlchemy `text()` with bind parameters.

**Test approach:**
- Inject SQL metacharacters into `tenant_id`, `actor_user_id`, `subject_id`, and `kind` fields via the API.
- Try: `'; DROP TABLE ff_audit_events; --`, `' OR '1'='1`, `\x00`, and oversized strings.
- **Expected:** All inputs are stored verbatim (no execution), or rejected by input validation.
- Verify the `set_config()` path: the tenancy GUC binder validates key names against `_GUC_KEY_RE` before calling `set_config`. Inject `'); DROP TABLE--` as a tenant ID.
- **Expected:** `ValueError` raised before the query executes.

### 4. Timing Attack Resistance (`hmac.compare_digest`)

**Finding:** NM-01. All HMAC comparisons use `hmac.compare_digest` — the `no_eq_compare_hmac` ratchet enforces this.

**Test approach:**
- Measure response time for a valid HMAC signature vs. a signature that differs in the first byte vs. last byte.
- **Expected:** Response time must be statistically indistinguishable (within measurement noise) for all three cases.
- Any statistically significant timing difference indicates a timing-vulnerable code path.

**Affected surfaces:**
- Cookie session verification (`CookiePrincipalExtractor.__call__`)
- CSRF token comparison (`csrf_protect`)
- Webhook signature verification (`WebhookAdapter._verify`)
- Audit chain hash comparison (computed in Python, not via HMAC directly, but stored hashes use `==` for equality — this is acceptable since SHA-256 output comparison is not secret-key-dependent)

### 5. Tenant Isolation (RLS GUC Verification)

**Finding:** C1. The `MultiTenantGUC` resolver sets `app.tenant_id` via `set_config(:k, :v, true)`. The `true` flag scopes the GUC to the current transaction only.

**Test approach:**
- Authenticate as `tenant-a`.
- Attempt to read workflow instances, audit events, and saga steps belonging to `tenant-b` by manipulating the `tenant_id` field in request bodies or query parameters.
- **Expected:** Zero rows returned. The RLS policy `current_setting('app.tenant_id') = tenant_id` filters them out.
- Test elevation: set `app.elevated = 'false'` and verify that elevated operations (cross-tenant reads) are blocked.
- Test connection pooling: verify that GUC values do not leak between requests from different tenants when using a connection pool (the `true` parameter to `set_config` must be used, scoping to the transaction).

**Verification query (run as the application user, not superuser):**
```sql
-- Should return 0 if RLS is properly enforced
SELECT set_config('app.tenant_id', 'tenant-a', true);
SELECT COUNT(*) FROM workflow_instances WHERE tenant_id = 'tenant-b';
```

### 6. Expression Evaluator Injection (E-35)

**Finding:** The `flowforge.expr` operator registry is frozen at module init. No `eval()` or dynamic code execution.

**Test approach:**
- Craft a workflow definition with guard expressions that attempt code injection:
  - `__import__('os').system('id')`
  - `${7*7}` (template injection)
  - Deeply nested expressions designed to cause exponential parse time
- **Expected:** The expression evaluator rejects unknown operators with a `ValueError` or similar. No code execution occurs.

---

*This guide has been refreshed for the v0.5.x package line. Evidence procedures reference table names, metric names, and port names that should be re-checked before each minor release.*
