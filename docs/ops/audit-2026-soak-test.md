# audit-2026 24h soak test runbook

**Owner**: ops / SRE
**Status**: criterion 7 of plan §10.3 — deferred from sprint close-out;
this runbook satisfies the deferred work post-merge.

## What it proves

- `flowforge_audit_chain_breaks_total == 0` under sustained load (10
  fires/sec + 100 outbox dispatches/sec for 24h).
- `flowforge_signing_secret_default_used_total == 0` (no host quietly
  running on the legacy opt-in flag).
- Alert rules in `framework/tests/observability/promql/audit-2026.yml`
  fire correctly when synthetic faults are injected (run-1 below).
- E-32 / E-37 / E-40 conformance invariants (engine atomicity, audit
  monotonicity, saga durability) hold at scale.

## Prereqs

- Staging env with the audit-2026 release deployed.
- `k6` installed locally (`brew install k6` or equivalent).
- `promtool` available on the runner (optional but recommended).
- A synthetic admin Principal token for the soak tenant.
- Prometheus endpoint reachable from the runner (no auth or with a
  scrape token).

## Run-1: synthetic-fault smoke (15 min)

Quick gate to confirm the alert rules and runner work before committing
24h of resources.

```bash
AUDIT_2026_SOAK_DURATION=15m \
AUDIT_2026_SOAK_TARGET=https://staging.flowforge.local/api \
AUDIT_2026_SOAK_PROM=https://prometheus.flowforge.local \
AUDIT_2026_SOAK_PRINCIPAL=$STAGING_ADMIN_TOKEN \
scripts/ops/audit-2026-soak.sh
```

Then inject a chain-break:

```bash
psql "$STAGING_AUDIT_DSN" -c \
  "UPDATE ff_audit_events SET prev_hash = 'tampered' WHERE event_id = (SELECT event_id FROM ff_audit_events ORDER BY occurred_at DESC LIMIT 1);"
```

Expected: `flowforge_audit_chain_breaks_total` increments within 60s
and the alert fires. Roll back the tampered row and confirm the metric
freezes (no further breaks).

## Run-2: full 24h soak

```bash
AUDIT_2026_SOAK_DURATION=24h \
AUDIT_2026_SOAK_TARGET=https://staging.flowforge.local/api \
AUDIT_2026_SOAK_PROM=https://prometheus.flowforge.local \
AUDIT_2026_SOAK_PRINCIPAL=$STAGING_ADMIN_TOKEN \
scripts/ops/audit-2026-soak.sh \
  | tee soak-evidence/run.log
```

Acceptance:
- Final SLI snapshot: both target counters at zero.
- k6 summary shows fires p99 < 250ms, outbox p99 < 500ms.
- No 5xx in either scenario.

## Run-3: chain re-verify (post-soak)

```bash
uv run python -m flowforge_audit_pg.tools.verify_chain \
  --dsn "$STAGING_AUDIT_DSN" \
  --tenant soak-test-tenant
```

(The CLI tool itself is in `flowforge_audit_pg.sink.PgAuditSink.verify_chain`;
wrap in a shell-friendly entrypoint if not already exposed.)

Expected: `Verdict.supported_ok(N)` where N matches the count from k6
(roughly `10 fires/sec * 86400s = 864,000` rows for 24h).

## Evidence package

After a green soak, attach to the audit-2026 release:

- `soak-evidence/sli-pre.txt`
- `soak-evidence/sli-post.txt`
- `soak-evidence/k6-summary.json`
- `soak-evidence/run.log`
- A short post-mortem at `framework/docs/audit-2026/soak-evidence-{date}.md`
  recording the run params + verdict + any anomalies + the final
  `verify_chain` output. This satisfies criterion 7 sign-off.

Update `framework/docs/audit-2026/signoff-checklist.md` E-72 row's
`final_verifications` block to add `soak_run_evidence: <date>` so the
post-merge verification trail is complete.

## Rollback / abort

The soak runner does not modify production state — only writes through
the synthetic tenant `soak-test-tenant`. To abort:

```bash
# kill k6
pkill -INT k6

# clean up synthetic tenant
psql "$STAGING_AUDIT_DSN" -c \
  "DELETE FROM ff_audit_events WHERE tenant_id = 'soak-test-tenant';"
```

Synthetic tenant cleanup is safe because all soak traffic is partitioned
into that single tenant_id.
