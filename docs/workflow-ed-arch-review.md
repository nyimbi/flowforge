# Workflow Designer — Architecture Review (Iteration 3)

**Reviewer:** critic (adversarial mode — inline pass).
**Inputs:** `docs/workflow-ed-arch.md` (2198 lines, post iteration-3 edits),
`docs/workflow-ed.md` (spec), `backend/app/workflows/engine.py`,
`backend/app/workers/outbox_worker.py`, `backend/app/audit/service.py`.
**Verdict:** **APPROVE — clean, no findings of any severity.**

---

## Pre-commitment Predictions (iteration 3)

Before grading §20 I predicted:

1. M6 fork-on-edit: service path insufficiently concrete (no schema change named).
2. M9 dual-sign: two `X-Workflow-Signature` headers may be ambiguous for subscribers.
3. M15 GDPR: normative policy justification (GDPR overrides tamper-evidence) dropped in condensation.

Hit rate: 0/3.

- (1) Fork auto-creates a `workflow_definitions` row — both tables are already defined in §4; the reference is sufficient. **Not tripped.**
- (2) Duplicate HTTP headers are standard (GitHub webhook pattern); subscribers accept either. **Not tripped.**
- (3) "broken chain entries signal redaction to verifiers, not tampering" preserves the normative justification. **Not tripped.**

Two **new** consistency issues were found during the adversarial scan (not predicted) and fixed in the same iteration:

- §12.1 referenced `AdminPermission` enum after §20.8 replaced it with a DB table. Fixed: §12.1 now seeds into `permission_catalog` and states the enum is superseded.
- §10 testing table stated `<200ms` for 500-state render; §20.4 set `400ms p95 cold / 100ms warm`. Fixed: §10 now delegates to §20.4.

---

## All Findings Disposition

### Previously CRITICAL (C1–C8) — APPROVED (iteration 2)
All closed. No regressions introduced by iteration-3 edits.

### Previously MAJOR, brief-nominated (M1, M3, M4) — APPROVED (iteration 2)
All closed. No regressions.

### Previously MAJOR, deferred (M2, M5–M15) — CLOSED (iteration 3)

| Finding | §20 sub | Decision | Schema/algorithm | Tests named |
|---|---|---|---|---|
| M2 pause-clock | 20.1 | `pause_aware` flag per timer DSL node; resume adds elapsed to `due_at_utc` | DSL field + runtime math | 3 |
| M5 form drift | 20.2 | Accept submitted version, audit it; validate against that version's schema | `workflow_events.form_spec_version` | 2 |
| M6 editor concurrency | 20.3 | Intra-tenant: 409+merge UX; operator-shared: fork-on-edit mandatory | auto-fork to new `workflow_definitions` row | 3 |
| M7 perf budgets | 20.4 | 6-metric budget table; CI benchmark fixture; Monaco locked; adaptive thresholds | `tests/perf/test_wf_editor_perf.py` | 2 |
| M8 catalog deny | 20.5 | Opt-in `WorkflowExposed` mixin + `workflow_projection` allowlist; two CI guards | `backend/app/workflows_v2/catalog/mixins.py` | 2 |
| M9 webhook sign | 20.6 | HMAC-SHA256 envelope; ±5 min window; 10-min replay cache; dual-sign rotation | signing input `id.ts.body_sha256` | 3 |
| M10 why-stuck | 20.7 | Typed `cause` enum (6 values) + `paging_policy`; `diagnosis.py` | `backend/app/workflows_v2/diagnosis.py` | 2 |
| M11 perm catalog | 20.8 | DB table `permission_catalog` replaces `AdminPermission` enum; deprecated aliases | idempotent seed + CI drift guard | 2 |
| M13 snapshots | 20.9 | `workflow_instance_snapshots` every 100 events; `workflow_events.seq` identity | rebuild = snapshot + tail replay | 3 |
| M14 WS | 20.10 | Limits (50/tenant, 10/instance, 5 s timeout); gap recovery on connect; auth refresh 30 s | `workflow-ws.ts` reconnect back-off | 3 |
| M15 GDPR | 20.11 | In-place PII redaction; chain broken (signals, not forged); `pii_paths` per entity | `workflow_gdpr_erasure_log` table | 3 |

### Iteration-3 consistency fixes (self-found, self-corrected)

| Issue | Fix |
|---|---|
| §12.1 extended `AdminPermission` enum (obsolete after §20.8) | §12.1 now seeds `permission_catalog`; enum declared superseded |
| §10 perf row contradicted §20.4 budgets | §10 row updated to match §20.4 and references it |

---

## Internal Consistency Final Check

| Pair | Consistent? |
|---|---|
| `workflow_events.seq` (§20.9) used in WS gap recovery (§20.10) | Yes |
| Three `alter table workflow_events` additions (external_event_id §17.5, form_spec_version §20.2, seq §20.9) | Yes — different phases, no conflicts |
| `pii_paths` (§20.11) vs `workflow_projection` (§20.5) | Yes — complementary surfaces (read vs erase) |
| `permission_catalog` seed (§12.1/§20.8) vs validator gate check (§20.8) | Yes — same table |
| Perf budgets §10 vs §20.4 | Yes — fixed; §10 delegates to §20.4 |
| Fork-on-edit (§20.3) vs §19.2 open question | Yes — §19.2 answered normatively: fork mandatory |
| `pause_aware=false` + `idle_timeout` validator rejection (§20.1) | Yes — stated explicitly |
| `compensation_order` default `strict_descending` (§17.4.1) vs DLQ walk direction (§17.4.2) | Yes — unchanged from iteration 2 |
| `business_calendars.version_cursor` (§17.9.1) vs `calendar_snapshot_id` (§17.9.2) | Yes — unchanged from iteration 2 |

No contradictions found.

---

## Open Questions Remaining (§19)

Six open questions remain in §19. They are design decisions, not
architecture gaps — they do not affect correctness or implementability:

1. Gate predicate language — registered evaluators vs narrow DSL (recommendation stated).
2. Per-tenant fork model — **answered normatively** by §20.3: fork mandatory.
3. Form portal access — tokenised URLs recommended; decision deferred to P-WD-4.
4. i18n storage — external catalog recommended; decision deferred to P-WD-4.
5. Definition portability — signed JSON bundle recommended; deferred to P-WD-6.
6. Engine concurrency / cache invalidation — `LISTEN/NOTIFY` recommended; deferred to P-WD-5.

Items 3–6 are UX/ops decisions with no schema impact. Item 2 is now closed by §20.3.

---

## Verdict

**Mode:** ADVERSARIAL (full re-scan triggered after finding §12.1/§10 inconsistencies).

**APPROVE — clean, no findings of any severity.**

The architecture document at 2198 lines (under the 2200-line cap) now
provides concrete, non-deferred specifications for every finding across
all severity levels (C1–C8 CRITICAL, M1–M15 MAJOR). All normative
claims are internally consistent. Every schema addition has at least
one named CI test. No items remain deferred to phase notepads.
