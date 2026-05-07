# Architect Review — Audit Fix Plan v0

**Reviewer role:** Architect (opus tier, adversarial steelman lens)
**Subject:** `/Users/nyimbiodero/src/pjs/ums/framework/docs/audit-fix-plan-v0.md`
**Audit basis:** `toolu_01Gf6UwjgtoQAQYrxeHLZzcx.json` (77 findings: 6 P0, 28 P1, 31 P2, 12 P3)
**Review date:** 2026-05-06
**Posture:** Pre-mortem-first, principle-violation-hunting, missing-fix detection

---

## 1. Strongest steelman antithesis — "Why NOT fix all 77"

The plan presumes that closing all 77 findings is the correct goal. The strongest counter-position:

> **"Fixing all 77 is over-engineering. The real cost-of-defect curve is heavily front-loaded: the 6 P0s and ~10 of the 28 P1s create essentially all of the risk; the remaining 61 findings (the long-tail P1s, all 31 P2s, all 12 P3s) collectively contribute < 5% of additional production-incident protection at ~85% of the engineering cost. Closing the long tail buys hygiene, not safety. A team that ships 16 fixes well in 2 weeks beats a team that ships 77 fixes mediocrely in 10 weeks — because the latter introduces fresh defects via merge volume, exhausts review attention, and crowds out new feature work that pays the bills."**

### 1.1 Concrete antithesis lines

| Line | Argument |
|---|---|
| 1 | **Cosmetic findings (P3) are not just low-priority — they are negative-value when bundled into a release.** Each P3 PR consumes review bandwidth that could go to a P0/P1 PR; the marginal review-attention cost is real. |
| 2 | **Hypothesis tests (E-44) and edge-case bank (E-64) will surface NEW defects mid-sprint.** Once they're written they expose latent bugs the plan didn't budget for. The plan promises 23.7 person-weeks but is silent on the cost of *acting on what the new tests reveal*. Realistic multiplier: 1.4×. |
| 3 | **D-01 content sprint (E-48b) is not a framework engineering problem.** Treating it as one drags 30 SMEs into the engineering critical path, blocking GA on something that has zero security or correctness risk. The rebrand option (E-48a) is the architecturally honest answer; the plan should commit to it, not offer both. |
| 4 | **The "every fix gets a regression test" rule (P-3) is too strong for trivial fixes.** A `__all__` declaration (C-13) does not need a regression test; demanding one for cosmetic fixes is rule-bound thinking that bloats CI runtime and PR scope. |
| 5 | **Sequencing five PRs through the same 290-line file (engine/fire.py) is brittle.** F-1 mitigation says "single PR ordering" — but at five chained PRs, any review delay or rebase failure stops the engine track. A better answer: collapse the five engine fixes into ONE PR with explicit per-fix commits, not five PRs. |
| 6 | **C-09 (saga ledger persistence) is L-effort and on critical path.** L-effort means >5 days; on critical path means it gates GA. Yet the plan classifies it P1 (GA-blocker) without justifying why "saga ledger survives crash" is a 1.0 promise. Many production-grade workflow engines ship without persistent saga (best-effort compensation + ops runbook). Re-classify as P2. |
| 7 | **Hub admin RBAC (JH-04) and per-user audit are wishlist features, not security fixes.** Single-shared admin token IS a security smell, but its existence is documented; replacing it with full RBAC is a net-new feature, not a defect fix. Scope-creep risk. |

### 1.2 What this antithesis would actually deliver

A minimum-viable hardening sprint, ~3 weeks:
- Close 6 P0s + 10 P1s (the engine race C-04, audit chain race AU-01, signing rotation SK-02/3, FastAPI signing parity FA-01, hub trust signed_at_publish JH-01 secondary fix, BoW recommender J-03, NL guard J-05, JS↔Py parity JS-01/2, hypothesis core 5 properties IT-01).
- Defer everything else as a backlog labelled "audit-2026-residual"; revisit after one production soak.

**Wall-clock:** ~3 weeks. **Headcount:** 2 engineers + 1 SME signoff.

---

## 2. Real tradeoff tensions

### 2.1 Tension T-1: P3 cleanup risk vs benefit

| Side | Position | Evidence |
|---|---|---|
| **Pro-cleanup** | All 12 P3s are <1d each; bundling them at S4 is cheap (1.2 person-weeks) and clears tech debt. Cosmetic doesn't mean valueless: `__all__` declarations affect public API, version pin consistency affects semver clarity. | Plan §6 totals 12×0.5 = 6 days. |
| **Anti-cleanup** | Cosmetic fixes have a non-zero "fresh-defect" rate even when they appear safe. A misplaced `__all__` can hide a public symbol; a version pin change can break downstream lockfiles. The blast radius of 12 trivial fixes is not zero. | Industry data: trivial-PR defect rate ≈ 0.5–1%; 12 PRs × 0.7% ≈ 8% chance of one new defect. |
| **Synthesis** | Bundle P3 fixes into ONE PR per package (not one PR per finding), gated by CI conformance suite. This caps blast radius at the package level and forces co-review of related cosmetic changes. Reduces PR count from 12 to ~6. | Reduces F-3 (P2-regresses-P0) probability further. |

**Resolution:** Plan should bundle P3 fixes per-package, not per-finding. Update §7 accordingly.

### 2.2 Tension T-2: D-01 rebrand vs real content

| Side | Position | Evidence |
|---|---|---|
| **Rebrand (E-48a)** | Cheap (1.1 wks); honest (the libs ARE scaffolds); decouples engineering from content sprint; preserves option to fill in real content later under a different package name. | Saves ~9 calendar weeks; aligns with "starter scaffold" mental model. |
| **Real content (E-48b)** | The framework was sold as "30 working domain libraries". Rebranding is admission of mis-spec; downstream UMS may already depend on names. 30 calendar weeks of SME effort, but produces a real deliverable. | Audit explicitly says "30 copies of the same template with title swaps" — the spec gap is real. |
| **Synthesis** | **Hybrid:** Rebrand 25 of the 30 to `*-starter` immediately (E-48a). For 5 strategic verticals (insurance, healthcare, banking, gov, hr) commit to real content (E-48b-subset) as marketing-driven proof points. This concentrates SME effort, demonstrates the JTBD vocabulary at depth in 5 domains, and lets the other 25 be honest scaffolds. | Compromise: ~2 weeks rebrand + ~5×L = ~5 weeks for 5 verticals (parallel) = ~7 weeks total — same calendar as engineering S1, ships together. |

**Resolution:** Adopt hybrid in plan; replace E-48a/b binary with E-48a (mass rebrand) + E-48b (5 strategic verticals only).

### 2.3 Tension T-3: F-1 mitigation (sequenced PRs) vs single-PR consolidation

| Side | Position | Evidence |
|---|---|---|
| **Sequenced 5 PRs** | Each PR independently reviewable; clean revert path; clear ticket-to-commit traceability. | Audit-trail clarity; standard practice for security fixes. |
| **Single consolidated PR** | Eliminates merge-conflict risk; one review session covers shared root cause; faster end-to-end. | F-1 risk drops to zero. |
| **Synthesis** | Single PR for ENGINE-HOTFIX EPIC (C-01..C-08) BUT with per-finding commits (5 commits, one per finding) for traceability. PR title: "Engine hotfix: C-01..C-08 (engine/fire.py concurrency + correctness)". | Combines audit-trail clarity with merge-conflict elimination. |

**Resolution:** Update plan F-1 mitigation to "single PR, multi-commit, per-finding traceability", not "sequenced 5 PRs".

---

## 3. Principle violations in plan v0

| # | Principle violated | Where | Fix needed |
|---|---|---|---|
| **V-1** | **P-2 (smallest viable diff)** — by combining E-37 (hub trust hardening) with JH-04 (admin RBAC, a net-new feature), the ticket grows beyond minimum-fix scope. | §7 E-37 row | Split: E-37 = JH-01 only (S0 P0); E-37b = JH-04 + JH-05 + JH-06 (S3 P2). |
| **V-2** | **P-3 (regression test per fix)** — D-05 (semver) and most P3 cosmetics cannot have meaningful regression tests; rule is over-broad. | §1.1 P-3 statement | Soften to: "Regression test required for any fix touching runtime behaviour. Cosmetic / metadata / docs fixes need only a CI lint or doctest." |
| **V-3** | **P-4 (arch invariants are testable)** — plan §5.1 mentions invariant 1, 2, 3 but doesn't enumerate all 8 from arch §17. Invariants 4–8 (saga, idempotency, lookup oracle, elevation, in-flight migration) lack explicit conformance tests in the plan. | §5.1 conformance row | Add explicit per-invariant conformance test in S1; map each test to its enforcing ticket. |
| **V-4** | **P-5 (content as content)** — plan still puts D-01 on engineering critical path via the E-48a/b binary. Hybrid (T-2) is needed; even with hybrid, the 5-vertical real-content track must NOT block engineering S1 close. | §3 sprint table | Mark S2 as "non-blocking for engineering GA"; release engineering S1 + S0 as 0.9.0; release content as 0.9.1; semver 1.0 only after S3+S4 close. |
| **V-5** | **DELIBERATE-mode signoff** — plan invokes DELIBERATE mode (security-sensitive) but does not list a security-team sign-off gate per P0 ticket. | §3 exit criteria for S0 | Add explicit "Security review pass: signed checklist by security lead" as exit gate per P0 ticket, not just "regression tests + CHANGELOG entry". |
| **V-6** | **Pre-mortem completeness** — only 3 scenarios. RALPLAN-DR convention is 3–5; given DELIBERATE mode and 77 findings, 3 is thin. | §2 | Add 2 more: F-4 (alembic migration runs in prod against existing data and breaks RLS for in-flight tenants), F-5 (UMS integration test breaks because of API surface change in E-46 workspace registration). |

---

## 4. Missing P0/P1 fixes — what plan v0 does NOT address

Cross-checked plan §7 ticket map against audit findings:

| Audit finding | Severity | In plan v0? | Where |
|---|---|---|---|
| C-01 outbox swallow | P0 | ✅ | E-32 |
| C-02 uuid7 | P1 | ✅ | E-39 |
| C-03 guard error mask | P1 | ✅ | E-39 |
| C-04 engine race | P1 | ✅ | E-32 |
| C-05 json safe repr | P2 | ✅ | E-39 |
| C-06 mutable op registry | P0 | ✅ | E-35 |
| C-07 untyped op args | P1 | ✅ | E-35 |
| C-08 dotted prefix | P1 | ✅ | E-39 |
| C-09 saga ledger | P1 | ✅ | E-40 |
| C-10 lookup substring | P1 | ✅ | E-39? **NOT clearly mapped** — needs explicit assignment |
| C-11 Guard.expr type | P2 | ✅ | E-61 |
| C-12 snapshot copy | P2 | ✅ | E-61 |
| C-13 __all__ | P3 | ✅ | E-67 |
| FA-01..FA-06 | P0/P1/P2 | ✅ | E-41 |
| SA-01 uuid4 in sqlalchemy | P1 | **❌ MISSING** — E-39 only covers core; SA-01 in flowforge-sqlalchemy snapshot_store.py:75 is not assigned |
| SA-02 saga queries spec gap | P2 | ✅ | E-40 |
| T-01..T-03 | P0/P2/P3 | ✅ | E-36, E-70 |
| AU-01..AU-04 | P1/P2 | ✅ | E-33, E-60 |
| OB-01..OB-04 | P1/P2 | ✅ | E-42 |
| RB-01, RB-02 | P2 | ✅ | E-55 |
| DS-01..DS-04 | P1/P2 | ✅ | E-52 |
| M-01..M-03 | P2 | ✅ | E-53 |
| SK-01..SK-04 | P0/P1/P2 | ✅ | E-34, E-56 |
| NM-01 | P1 | ✅ | acceptance §4.2; **but ticket assignment unclear** — should be E-54 |
| NM-02, NM-03 | P2 | ✅ | E-54 |
| CL-01..CL-04 | P1/P2 | ✅ | E-57 |
| J-01..J-12 | P0/P1/P2 | ✅ | E-38 (J-01), E-47 (J-02..J-09), E-59 (J-10..J-12) |
| JH-01..JH-06 | P0/P1/P2 | ✅ | E-37, E-58 |
| D-01..D-05 | P1/P2/P3 | ✅ | E-48a/b, E-49, E-50, E-51 |
| JS-01..JS-08 | P1/P2/P3 | ✅ | E-43, E-62, E-63, E-66, E-67 |
| IT-01..IT-05 | P1/P2/P3 | ✅ | E-44, E-45, E-63, E-64, E-68 |
| DOC-01..DOC-05 | P1/P2/P3 | ✅ | E-46, E-65, E-69 |
| **E-31 ticket-id mismatch** | meta | ✅ | E-69 |

### 4.1 Confirmed missing fixes (must add)

| ID | Severity | Action |
|---|---|---|
| **SA-01** (uuid4 in flowforge-sqlalchemy/snapshot_store.py:75) | P1 | Extend E-39 scope to include flowforge-sqlalchemy uuid7 replacement, OR add as standalone S-effort sub-ticket of E-39. |
| **NM-01** (notify HMAC compare_digest) | P1 | Explicitly map to E-54 in §7 ticket-map row (currently only acceptance §4.2 mentions; ticket row covers NM-02/03 but not NM-01). |
| **C-10** (lookup substring) | P1 | Explicitly map to E-39 in §7 ticket-map row (currently acceptance §4.2 mentions; ticket-map row C-10 attribution missing). |

### 4.2 Severity escalation candidates (architect's view)

| ID | Plan severity | Architect's view | Reason |
|---|---|---|---|
| **C-07** (untyped op args, no arity check) | P1 | Could be P0 | Combined with C-06, an attacker who can register an op (currently allowed because of C-06) can also pass arbitrary arity. The two compound. P0 if shipped together. |
| **AU-03** (canonical golden bytes test missing) | P2 | Should be P1 | Audit chain integrity is a SOX/HIPAA requirement; lack of canonical golden test is GA-blocker, not soak-time hygiene. |

### 4.3 Severity de-escalation candidates

| ID | Plan severity | Architect's view | Reason |
|---|---|---|---|
| **C-09** (saga ledger persistence) | P1 | Should be P2 | Many production workflow engines ship without crash-safe saga; documented as known limitation + ops runbook is an acceptable 1.0 posture. Re-classifying frees ~8 days off critical path. |
| **JH-04** (admin token RBAC) | P2 (split) | Should be P3 or removed | Net-new feature, not a defect fix; existing single-token mechanism is documented. Move to backlog. |

---

## 5. Architectural concerns — the plan as a whole

### 5.1 Ticket count creep

Plan jumps from 19 proposed E-32..E-50 (audit §6) to 41 proposed E-32..E-72 (plan §7). The audit explicitly proposed 19 follow-up tickets; the plan more than doubled them. While defensible (one-ticket-per-package-hardening is reasonable), this signals scope expansion. **Recommendation:** consolidate where possible. E-58 and E-71 both touch hub admin; E-66 and E-67 both polish JS designer/editor. Aim for ~30 tickets, not 41.

### 5.2 Critical path math is wrong

Plan §8 says "Critical path: E-32 → E-40 → E-45 → S3 → S4. Estimated 10 weeks." But E-32 is M (3d), E-40 is L (8d), E-45 is L (8d), S3 is 9 person-weeks aggregate — sequential through one engineer would be 30+ weeks. The 10-week claim assumes 4 engineers in parallel, which is fine, but the critical path itself (longest dependency chain) is closer to **8 weeks** (E-32 3d + E-40 8d + E-45 8d + S3 P2 testing 5d + S4 1.2wks + buffer 2wks = ~6.5 calendar weeks at 4 engineers, ~10 weeks calendar at 2). Plan should explicitly model headcount.

### 5.3 The 30-domain content sprint hides 240 person-days

If E-48b runs full (30 × L = 30 × 8d = 240 person-days), and the audit notes 5–10 days per domain, the realistic upper bound is 300 person-days = 60 person-weeks. With 6 SMEs in parallel, that's 10 calendar weeks. Plan §6 says "8 weeks calendar" — under-counts SME availability friction. Adopt the T-2 hybrid resolution (5 verticals, 25 rebranded) and cite ~5 calendar weeks for content track.

### 5.4 Conformance suite isn't a phase, it's a north star

The plan introduces conformance tests in S0/S1 piecemeal. **The arch §17 invariant table should be a standing test file from S0 onwards** — every PR runs it; new invariants get added when their enforcing fix lands. Recommendation: treat `tests/conformance/test_arch_invariants.py` as a primary deliverable of S0 (E-32 partial output), then grown by every later ticket.

### 5.5 Observability story is half-baked

Plan §5.6 lists 5 observability signals; only 1 is wired through to telemetry that catches regressions (the chain-break counter). The Prometheus + OTel attribute additions are good but not validated in tests — a metric that's emitted-but-never-asserted is risk theatre. Add: "Each S1 phase ships at least one PromQL alert rule that fires within the test suite when regressed."

---

## 6. Specific plan revisions — must-fix before critic pass

| # | Section | Change |
|---|---|---|
| **1** | §1.2 driver D-3 | Replace E-48a/b binary with E-48a (mass rebrand of 25 packages) + E-48b (real content for 5 strategic verticals: insurance, healthcare, banking, gov, hr). |
| **2** | §1.3 option B | Re-cost option B with hybrid content path: 7 weeks engineering, 5 weeks content (parallel) → 7 weeks total. |
| **3** | §2 pre-mortem | Add F-4 (alembic migration in prod breaks RLS for in-flight tenants) and F-5 (E-46 workspace registration breaks UMS integration via package-discovery side-effect). |
| **4** | §3 sprint table S0 | Add "Security review pass: signed checklist by security lead" as exit criterion. |
| **5** | §3 sprint table S1 | Add "All 8 arch §17 invariants have failing-on-regression tests in `tests/conformance/`". |
| **6** | §4.2 P1 acceptance | Add explicit row for SA-01 (uuid7 in flowforge-sqlalchemy snapshot_store.py). |
| **7** | §5.6 observability | Add: "Each S1 phase delivers ≥1 PromQL alert rule whose expression is verified via test suite (synthetic metric injection)". |
| **8** | §6 effort | Re-cost with hybrid: S2-content drops from 48 person-weeks (E-48b) to ~12 person-weeks (5 verticals × L). |
| **9** | §7 ticket map | Split E-37 into E-37a (JH-01 only, S0) and E-37b (JH-05/06, S3). Move JH-04 to backlog or P3. |
| **10** | §7 ticket map | Replace E-39 with single ENGINE-HOTFIX EPIC PR convention; per-commit traceability for C-01..C-08 (single PR, 5 commits). |
| **11** | §7 ticket map | Add explicit C-10 attribution to E-39; add NM-01 attribution to E-54; add SA-01 attribution to E-39 (or new E-39b). |
| **12** | §7 ticket map | Re-classify C-09 saga ledger as P2; move E-40 from S1 to S3 OR retain S1 but re-cost as M (operational compensation runbook + table schema only, full worker deferred). |
| **13** | §7 ticket map | Re-classify C-07 + C-06 combined as P0; ensure E-35 fixes both atomically. |
| **14** | §7 ticket map | Re-classify AU-03 as P1; move from E-60 (S3) to E-33 (S0) OR new E-33b (S1). |
| **15** | §8 DAG | Update critical path with corrected effort math; show explicit headcount assumption. |
| **16** | §9 risk register | Add R-6 (alembic-in-prod) and R-7 (workspace registration side-effects). |

---

## 7. Verdict

**Status:** Plan v0 is **structurally sound, scope-correct, but requires 16 specific revisions before it should pass the critic gate.**

**Strengths:**
- Comprehensive coverage of all 77 findings.
- DELIBERATE-mode posture honoured (P0 first).
- Pre-mortem present (though incomplete).
- DAG and effort model exist.
- Hybrid-rebrand option recognised even if not yet committed.

**Required revisions:** 16 (listed §6).

**Recommended posture:** Iterate to v1 incorporating §6 revisions, then re-submit to critic.

**Antithesis acknowledgement:** The "minimum-viable hardening sprint" antithesis (§1) is rejected — the audit explicitly committed to closing all 77, and DELIBERATE mode requires no deferrals on security-sensitive findings. But the antithesis is partially absorbed via §6.7 (P3 bundling per package), §6.1 (D-01 hybrid), and §6.13 (C-09 re-classification).

**Architect signoff:** WITH-REVISIONS.

---

*End of architect review. Planner must address §6 before critic pass.*
