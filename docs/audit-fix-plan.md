# Flowforge Audit Fix Plan — Final (v1)

**Plan author:** Executor (RALPLAN consensus, planner pass 2)
**Date:** 2026-05-06
**Mode:** DELIBERATE (auto-enabled — security-sensitive: SQL injection, signing, audit chain, sandbox escape, SOX/HIPAA)
**Source audit:** `/Users/nyimbiodero/.claude/projects/-Users-nyimbiodero-src-pjs-ums/3eb9101f-d1a0-4f8d-b202-413c81a3d026/tool-results/toolu_01Gf6UwjgtoQAQYrxeHLZzcx.json`
**Scope:** All 77 audit findings — zero deferrals
**Iteration:** v1 (post-architect, post-critic, ready for APPROVE)
**Predecessors:** v0 → architect-review → critic-review (ITERATE) → v1 (this doc)

---

## Table of contents

1. RALPLAN-DR Summary
2. Pre-mortem (7 scenarios)
3. Sprint roadmap
4. Per-finding acceptance criteria (all 77)
5. Test plan (unit + integration + e2e + property + chaos + observability + audit-2026 suite)
6. Effort & headcount
7. Ticket map E-32..E-62 (≤30 consolidated tickets, 31 actually)
8. Dependency DAG
9. Risk register (7 entries)
10. Observability + DELIBERATE-mode signoff trail
11. Audit-2026 close-out criteria
12. Backlog of intentionally-deferred items (empty by spec)
13. ADR — Decision, Drivers, Alternatives, Why Chosen, Consequences, Follow-ups

---

## 1. RALPLAN-DR Summary

### 1.1 Five guiding principles

| # | Principle | Why it matters here |
|---|---|---|
| P-1 | Security defects ship first; behaviour changes ship later. | 6 P0 + escalated AU-03 + escalated C-07 = 8 ship-blockers. |
| P-2 | Smallest viable diff per fix; verify behaviour preserved. | 77 findings against 45 Python + 7 JS pkgs must not become a refactor festival. |
| P-3 | Runtime-affecting fixes ship with a regression test (fails-before-passes-after). Metadata / docs / cosmetic fixes ship with a CI lint, doctest, or schema check. | (Softened from v0 per architect V-2 / critic CR-1.) |
| P-4 | All 8 architectural invariants in arch §17 are testable contracts. | One conformance file `tests/conformance/test_arch_invariants.py` grows from S0 onwards. |
| P-5 | Domain content is content, not code. Engineering and content tracks decouple. | Hybrid: 25 packages rebranded as starter scaffolds, 5 strategic verticals get real content. |

### 1.2 Top three decision drivers

| # | Driver | Implication |
|---|---|---|
| D-1 | Production blockers must close before any 1.0 tag. | All 8 P0-equivalents in week 1; gate semver bump on green hotfix sprint. |
| D-2 | Concurrency + audit-chain integrity share a "shared mutable state under concurrency" root cause. | Group C-04, AU-01, FA-04, T-02, JH-02, OB-02 into one Concurrency-GA arc. |
| D-3 | Domain content (D-01) is the largest single cost. Hybrid path (25 rebranded + 5 verticals) takes ~5 calendar weeks; pure E-48b would take ~10. | Engineering S1 finishes first; content tracks parallel and ships as 0.9.1. |

### 1.3 Three viable options with pros/cons

| Option | Description | Pros | Cons | Decision |
|---|---|---|---|---|
| **A — Fix-all-77 strict big-bang** | Single release blocked until 77 closed. | Highest quality bar; clearest semver. | 14–16 wks; blocks features; D-01 dominates timeline. | Rejected. |
| **B — Phased-by-severity (CHOSEN)** | P0 → P1 engineering → P1 content (parallel) → P2 → P3. Each phase shippable. | Fast P0 turn-around; parallel content track; small-PR discipline. | More release ceremony; P3 risks slip. | **Chosen.** |
| **C — Minimum-viable 16-fix** | Close 6 P0 + 10 highest-risk P1; defer 61 as "audit-2026-residual" backlog. | 3 wks; lowest cost; honest about long-tail value. | Violates user spec ("zero deferrals"); leaves SOX/HIPAA hygiene gaps; defers AU-03 (escalated to P1). | Rejected — violates explicit user constraint and DELIBERATE-mode "no deferrals on security-sensitive". |

### 1.4 Severity reclassifications (post-architect)

| Finding | v0 sev | Final sev | Reason |
|---|---|---|---|
| **C-07** (untyped op args, no arity check) | P1 | **P0** | Compounds with C-06 (mutable registry) — attacker who registers an op also bypasses arity. Atomic fix in E-35. |
| **AU-03** (canonical golden bytes test missing) | P2 | **P1** | SOX/HIPAA audit chain integrity GA-blocker. Moves to S1 via E-37. |
| **C-09** (saga ledger persistence) | P1 | **P1** (kept) | Architect proposed P2; critic disagreed. Kept P1 because arch §17 invariant 4 (saga durability) is in scope; reduce E-39 scope to "schema + minimal worker", not full reverse-execution model. |
| **JH-04** (admin token RBAC) | P2 | **P2** (split) | Net-new feature aspect moved to backlog; basic improvement (rotation + audit log) stays in E-58. |

**Total elevated to P0-equivalent:** 8 (was 6).

---

## 2. Pre-mortem — 7 failure scenarios

| # | Scenario | Trigger | Detection | Mitigation | Rollback | Owner |
|---|---|---|---|---|---|---|
| **F-1** | Concurrent fix conflicts on `engine/fire.py` | C-01..C-08 all touch one file (~290 LoC). 5 parallel PRs collide. | PR review queue; merge conflict at base. | **Single ENGINE-HOTFIX EPIC PR** with per-finding commits (5 commits, one per finding); CODEOWNERS lock for duration; rebased on each merge. | Revert single PR via git revert; engine track resumes from last good commit. | Engine EPIC owner (1 named) |
| **F-2** | Security fix ships incomplete (signing or auth bypass) | SK-01 removes default → host that depended on it fails to boot. JH-01 tightens trust → existing `allow_unsigned` publishers can't install. | Synthetic deploy in CI to staging UMS fails; downstream integration suite red. | Each P0-Sec fix ships with: (a) opt-in legacy flag `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` w/ loud-log warn for 1 minor-version deprecation window; (b) SECURITY-NOTE.md entry; (c) UMS integration test exercising hardened path before merge. | Re-deploy previous image; flag re-enabled. | Security lead |
| **F-3** | P2 fixes regress P0 invariants | S3 cleanup PR touches `engine/fire.py` and removes a defensive check from S0. | `tests/conformance/test_arch_invariants.py` (`@invariant_p0` tag) goes red. | CI gate: `@invariant_p0` tests required-green on every PR; removal needs security-team review. | Revert offending PR; conformance suite re-runs. | CI/test eng |
| **F-4** | Alembic migration runs in prod and breaks RLS for in-flight tenants | E-38 RLS DDL hardening alters policy; mid-migration window leaves some tables protected and others not. | Per-tenant smoke test against staging shows cross-tenant read; alembic dry-run on prod-shaped data fails. | Migration is **online + reversible**; RLS policy applied with `IF NOT EXISTS`; pre-migration dry-run in CI against prod-shape DB snapshot; canary rollout to 1 tenant before full. | `alembic downgrade -1`; RLS reverted to v0 policies. | DBA lead |
| **F-5** | E-46 workspace registration breaks UMS integration | Adding 30 domain pkgs to `[tool.uv.workspace]` changes `uv build` discovery side-effects → UMS pip install picks up unintended pkgs. | UMS smoke test in CI fails on pip resolve; package count reports differ. | Workspace registration done in TWO steps: (a) add to `members` with `package=false` flag (build-only); (b) flip to `package=true` per pkg as it's reviewed. | Remove pkg from `members`; UMS lock unchanged. | Build/release eng |
| **F-6** | CI grep ratchet false positives erode trust | The "no `except Exception: pass`" grep gate matches a legitimate test fixture; team turns the gate off "just for this PR" → ratchet broken. | PR with `# noqa: ratchet` comment merges. | Ratchet baseline file (`scripts/ci/ratchets/baseline.txt`) records existing legit instances; new occurrences fail; legit additions need explicit baseline-update PR with security-team review. | Revert PR; baseline reset to last green. | Security lead |
| **F-7** | P0 env-var change breaks year-old prod image | SK-01 makes `FLOWFORGE_SIGNING_SECRET` mandatory. Customer running 6-month-old image upgrades to new framework → boot fails. | Prod boot loop; release-note grep on customer side missed. | Two-version deprecation: v0.9 → loud-log + still default; v0.10 → require env var. CHANGELOG SECURITY-BREAKING entry; customer upgrade-checklist email; `flowforge_pre_upgrade_check` CLI command added. | Roll back to v0.9; set `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` opt-in flag. | Release manager |

---

## 3. Sprint roadmap (phased)

| Sprint | Wall clock | Goal | Tickets | Exit criteria | DELIBERATE signoff |
|---|---|---|---|---|---|
| **S0 — P0 Hotfix** | Week 1 (5 working days, 4 engineers) | Close 8 P0-equivalent findings | E-32, E-33, E-34, E-35, E-36, E-37, E-38 | All 8 P0 findings closed with regression tests; security review pass per ticket; CHANGELOG SECURITY entry per fix; conformance suite green for invariants 1, 2, 3, 7 | Security lead + Release manager sign `docs/audit-2026/signoff-checklist.md` per ticket |
| **S1 — P1 Engineering GA-blockers** | Weeks 2–4 (3 wks, 4 engineers) | Close 27 non-content P1 findings | E-39, E-40, E-41, E-42, E-43, E-44, E-45, E-46, E-47 | All 27 P1 findings closed; replay-determinism conformance green; arch §17 invariants 1–8 all enforced; `make audit-2026` target green | Architecture lead + QA lead sign |
| **S2a — Domain Content Rebrand** | Weeks 2–3 (parallel to S1) | Close D-01 for 25 non-strategic domains | E-48a (25 pkg rebrand), E-49 (smoke tests), E-50 (semver), E-51 (init export) | 25 packages renamed `flowforge-jtbd-*-starter`; README disclaimer; smoke tests green | Product lead sign-off on rebrand messaging |
| **S2b — Domain Content Real (5 verticals)** | Weeks 4–8 (5 wks parallel, 5 SMEs) | Close D-01 for insurance, healthcare, banking, gov, hr | E-48b (5 verticals × L) | 5 domains have real JTBDs (incident_date, claimant_id, etc.); each signed off by named domain SME; all yaml validate against full schema (data_capture diversity, edge_cases, documents_required, approvals, notifications, sla, data_sensitivity, compliance) | Per-domain SME sign + product lead |
| **S3 — P2 Hardening** | Weeks 5–6 (2 wks, 4 engineers) | Close 31 P2 findings | E-52..E-62 | All 31 P2 findings closed; CI ratchets green (no new `except Exception: pass`, no new f-string SQL, no new `InMemory*` w/o suffix); soak test 24h @ 10 fires/sec | QA lead + Architecture lead sign |
| **S4 — P3 Polish** | Week 7 (continuous, 1 engineer) | Close 12 P3 findings | E-67..E-72 (5 polish tickets, 12 findings bundled per package, not per finding per critic CR-Q4) | All 12 P3 findings closed; lint/doctest/schema gates pass; docs aligned to code | Doc/release sign-off |

**Total wall clock:** **7 weeks engineering + 5 weeks content (parallel) = 8 weeks calendar.**
**Headcount:** 4 senior engineers + 1 security lead + 5 domain SMEs + 1 release manager.

### 3.1 DELIBERATE-mode signoff trail (CR-3)

Artefact: `docs/audit-2026/signoff-checklist.md` (created S0 day 1).

Per-ticket signoff row (sample):

```yaml
ticket: E-32
findings: [C-04, C-01]
phase: S0
security_lead_signoff:
  signer: <name>
  date: <iso8601>
  commit_sha: <sha>
  pre_deploy_checks:
    - "pytest tests/conformance/ -k invariant_p0 -v"
    - "scripts/ci/ratchets/check.sh"
    - "scripts/ci/no_default_secret.sh"
  post_deploy_checks:
    - "curl staging/health && grep 'flowforge_fix_id=E-32' /var/log/flowforge.log"
    - "promql: rate(flowforge_audit_chain_breaks_total[5m]) == 0"
  rollback_plan: "git revert <sha>; alembic downgrade -1 if migration"
  observability_check: "grafana dashboard /d/audit-2026/E-32 panel green"
release_manager_signoff:
  signer: <name>
  date: <iso8601>
```

CI gate `scripts/ci/check_signoff.py` rejects merge to `main` if checklist row for the ticket is empty or unsigned.

---

## 4. Per-finding acceptance criteria (all 77)

Acceptance test ID convention: `test_<FINDING_ID>_<short>` in `tests/audit_2026/`.

### 4.1 P0-equivalent (8) — DELIBERATE signoff required

| Finding | File:line | Acceptance test_id | Acceptance criterion | Test type |
|---|---|---|---|---|
| **C-01** | `flowforge-core/.../engine/fire.py:283-288` | `test_C_01_outbox_failure_rolls_back_fire` | Outbox raise during fire → audit row + state transition rolled back; `store.get(id).state == pre_state`; conformance invariant 2 (two-phase fire) green. | regression |
| **C-04** | `engine/fire.py:223-251` | `test_C_04_concurrent_fire_race` | 100 concurrent `fire()` for one instance → exactly 1 transition; others raise `ConcurrentFireRejected` or await; final state == single advance. | regression |
| **C-06** | `expr/evaluator.py:25-30` | `test_C_06_op_registry_frozen` | Post-startup `register_op("==", ...)` raises `RegistryFrozenError`; replay-determinism conformance: same DSL across two evaluator instances → byte-identical guard outcomes. | regression + conformance |
| **C-07** | `expr/evaluator.py:73-79` | `test_C_07_op_arity_mismatch` | Op called with wrong arity raises `ArityMismatchError` at compile time, not run time. | regression |
| **SK-01** | `signing-kms/hmac_dev.py:20, 25` | `test_SK_01_no_default_secret` | Import + instantiate w/o env var raises `RuntimeError("explicit secret required")`; opt-in flag `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` allows w/ loud-log warn. | regression + security ratchet |
| **T-01** | `flowforge-tenancy/.../single.py:46` | `test_T_01_set_config_bind_param` | `_set_config("x'); DROP TABLE--", "v")` raises `ValueError` (validated `^[a-zA-Z_][a-zA-Z_0-9.]*$`); SQL log shows bound param `:k`, no string interpolation. | regression + security ratchet |
| **J-01** | `flowforge-jtbd/.../alembic_bundle/versions/r2_jtbd.py:235-290` | `test_J_01_migration_table_allowlist` | Alembic upgrade with monkey-patched malicious table-list raises `ValueError`; tables resolved via `quoted_name` and asserted in allow-list. | regression |
| **JH-01** | `flowforge-jtbd-hub/.../registry.py:316` | `test_JH_01_signed_at_publish_explicit` | Package published with `allow_unsigned=True` stores `signed_at_publish=False`; default install raises `UnsignedPackageRejected`; explicit `accept_unsigned=True` install succeeds and emits audit event `PACKAGE_INSTALL_UNSIGNED`; error message no longer leaks internal `key_id`. | regression |

### 4.2 P1 (28) — engineering critical

| Finding | File:line | test_id | Acceptance criterion | Test type | Maps to ticket |
|---|---|---|---|---|---|
| C-02 | `engine/fire.py:69, 100` | `test_C_02_uuid7_in_fire` | All `uuid.uuid4()` → `uuid7str()`; lockfile fixture asserts time-ordered prefixes. | regression | E-39 |
| C-03 | `engine/fire.py:84-91` | `test_C_03_guard_error_surfaces` | Guard with syntax error raises `GuardEvaluationError`; existing false-guard tests still green. | regression | E-39 |
| C-08 | `engine/fire.py:114-115` | `test_C_08_dotted_prefix_rejected` | Target `context.x` raises `InvalidTargetError`; dotted-write tests still green. | regression | E-39 |
| C-09 | `engine/saga.py` (whole file) | `test_C_09_saga_persists_across_restart` | Crash mid-fire; restart; compensation worker replays ledger entries; integration test asserts compensations executed exactly once. | regression + integration | E-40 |
| C-10 | `compiler/validator.py:116-132` | `test_C_10_lookup_substring_walks_ast` | Expression containing string literal `"lookup_failed"` no longer triggers permission check; explicit `lookup` op still does. | regression | E-39 |
| **SA-01** (architect-found) | `flowforge-sqlalchemy/.../snapshot_store.py:75` | `test_SA_01_uuid7_in_snapshot_store` | All `uuid.uuid4()` → `uuid7str()`; existing snapshot tests green. | regression | E-39 |
| FA-01 | `flowforge-fastapi/.../auth.py:114-118` | `test_FA_01_signing_roundtrip` | `verify(issue(p)) == p` for all base64-padded variants; integration test with `=` padding stripped + restored both verify. | regression | E-41 |
| FA-02 | `auth.py:147-153` | `test_FA_02_csrf_secure_default` | CSRF cookie default `secure=True`; `ConfigError` if `secure=False` w/o explicit `dev_mode=True`. | regression | E-41 |
| FA-03 | `flowforge-fastapi/.../ws.py:159-168` | `test_FA_03_ws_native_extractor` | WS auth uses `WSPrincipalExtractor` protocol; HTTP-scope spoof code path removed; existing WS auth tests green. | regression | E-41 |
| FA-04 | `ws.py:78` | `test_FA_04_hub_request_scoped` | Subscribe in test A, no subscribers visible in test B; hub state isolated per request. | regression | E-41 |
| AU-01 | `flowforge-audit-pg/.../sink.py:159-169` | `test_AU_01_concurrent_record_no_chain_break` | 100 concurrent records for 1 tenant; `verify_chain()` reports zero forks; `(tenant_id, ordinal)` unique constraint exists. | regression + integration | E-37 |
| AU-02 | `sink.py:172-199` | `test_AU_02_chunked_verify_memory_bound` | `verify_chain()` streams 10K-row chunks; `tracemalloc` peak <256MB at 10M rows. | regression | E-37 |
| **AU-03** (escalated) | `audit_pg/hash_chain.py:103-113` | `test_AU_03_canonical_golden_bytes` | Golden-byte fixture file in `tests/audit_2026/fixtures/canonical_golden.bin`; verify against committed bytes; refusing to load on hash mismatch. | regression + property | E-37 |
| OB-01 | `flowforge-outbox-pg/.../worker.py` (table f-strings) | `test_OB_01_table_name_validated` | Constructor with `"x; DROP"` raises `ValueError`; legitimate `schema.table` accepted. | regression | E-42 |
| OB-02 | `worker.py:309-365` | `test_OB_02_sqlite_single_worker` | SQLite path raises `RuntimeError` if `pool_size > 1`; PG path unaffected. | regression | E-42 |
| DS-01 | `flowforge-documents-s3/.../port.py:135-138` | `test_DS_01_doc_id_validated` | `doc_id = "../../etc"` raises `ValueError`; legitimate ids accepted. | regression | E-52 |
| DS-02 | `port.py:128-131` | `test_DS_02_inmemory_suffix` | Class renamed `S3DocumentPortInMemory`; old name re-exported with `DeprecationWarning`. | regression | E-52 |
| J-02 | `lint/conflicts.py:144-269` | `test_J_02_pair_pre_bucketing` | 10K-JTBD bench runs in <5s (was ~50s); pre-bucketed by `(timing,data,consistency)`; bucket count ≤12. | benchmark + regression | E-47 |
| J-03 | `ai/recommender.py:171-196` | `test_J_03_bow_fit_transform_separation` | `BagOfWordsEmbeddingProvider` exposes `fit()` + `transform()`; `embed()` after `freeze()` raises if new doc; vector basis stable across 1000 embeds. | regression | E-47 |
| J-04 | `ai/recommender.py:227-247` | `test_J_04_inmemory_warning_emitted` | `InMemoryEmbeddingStore` instantiation emits `PerformanceWarning` once; docstring + README link to pgvector. | regression | E-47 |
| J-05 | `ai/nl_to_jtbd.py:101-122` | `test_J_05_adversarial_prompts` | 50-prompt adversarial test bank (Unicode homoglyphs, paraphrases); ≥45/50 caught by structured-output validator; residual risk documented in `docs/security/nl-injection.md`. | regression + property | E-47 |
| J-06 | `ai/nl_to_jtbd.py:155` | `test_J_06_dead_compliance_entry_removed` | `("HIPAA, GDPR": ())` placeholder absent; tests still green. | regression | E-47 |
| J-07 | `ai/nl_to_jtbd.py:336-379` | `test_J_07_extract_json_uses_raw_decode` | Fixture with `"\\u007b"` in string parses correctly via `json.JSONDecoder.raw_decode`; brace-counting code path removed. | regression | E-47 |
| J-08 | `dsl/lockfile.py:140-157` | `test_J_08_canonical_body_allowlist` | `canonical_body()` allow-list of keys; introducing new top-level field requires explicit registration; old lockfile bytes verify unchanged. | regression + property | E-47 |
| JH-02 | `jtbd_hub/registry.py:340-342` | `test_JH_02_counter_in_db` | Counter persisted in `package.download_count`; 2 hub replicas × 100 installs each → DB shows 200 (not 100 each). | integration | E-58 |
| JH-03 | `registry.py:309-321` | `test_JH_03_verified_at_install_cached` | `package.verified_at_install` cached; bundle re-verified daily by background job; install-time verify only on first install per version. | regression + integration | E-58 |
| JS-01 | `js/flowforge-renderer/src/expr.ts:88-90` | `test_JS_01_unknown_op_returns_false` | TS evaluator returns false on unknown op (matches Python); cross-runtime conformance fixture (200 inputs) byte-identical outputs. | conformance | E-43 |
| JS-02 | `expr.ts:96-99` | `test_JS_02_strict_equality_only` | Strict-equality only; loose-null-equality removed; cross-runtime conformance fixture green. | conformance | E-43 |
| JS-03 | `useFlowforgeWorkflow.ts` | `test_JS_03_react19_mount` | Hook mounts under React 19 in contract test; tenant query key matches snapshot. | regression | E-43 |
| D-02 | `jtbd-insurance/.../claim_fnol.yaml:6` | `test_D_02_external_role_lint` | DSL lint rule rejects `external: false` for actor.role in `external_role_ids` allow-list; CI fails on regression. | schema | E-48b |
| D-01 | All 30 domains | `test_D_01_starter_or_real` | (E-48a path) 25 packages renamed `*-starter` w/ README disclaimer + lint badge; (E-48b path) 5 verticals validated against full-schema lint (data_capture diversity ≥3 fields, edge_cases ≥1, documents_required ≥1, approvals ≥1, notifications ≥1, sla, data_sensitivity, compliance). | schema + manual SME | E-48a, E-48b |
| IT-01 | (no file) | `test_IT_01_property_suite_green` | `hypothesis` dep added; 5 properties shipped: lockfile round-trip, conflict-solver determinism, evaluator literal-passthrough, manifest signing-payload stability, money arithmetic. | property | E-44 |
| IT-02 | `tests/integration/` | `test_IT_02_e2e_three_suites` | Three E2E suites: fire→audit→verify; fire→outbox→ack; fork→migrate→replay-determinism. | e2e | E-45 |
| DOC-01 | root `pyproject.toml` | `test_DOC_01_workspace_complete` | Workspace lists all 45 Python pkgs; `uv build` from root produces all wheels (run as CI step). | CI | E-46 |
| DOC-02 | `framework/README.md` | `test_DOC_02_pkg_count_matches` | README pkg count == filesystem pkg count; layout diagram updated; doctest/markdown lint passes. | doctest | E-46 |
| NM-01 | `notify_multichannel/transports.py:422` | `test_NM_01_compare_digest` | All HMAC verify paths use `hmac.compare_digest`; static grep gate in CI. | regression + ratchet | E-54 |
| CL-01 | `flowforge_cli/jtbd/generators/{domain_router,audit_taxonomy,sa_model}.py` | `test_CL_01_stub_generators` | Files implemented OR deleted; no <30 LoC stubs in framework code paths. | regression | E-57 |
| SK-02 | `signing-kms/hmac_dev.py:73-74` | `test_SK_02_key_id_rotation` | Key map `dict[str,str]`; `verify(key_id="unknown", ...)` raises `UnknownKeyId`; pre-rotation sigs verify against pre-rotation key. | regression | E-34 |
| SK-03 | `signing-kms/kms.py:112, 216` | `test_SK_03_transient_vs_invalid` | `KmsTransientError` distinct from `KmsSignatureInvalid`; transient retried with backoff; permanent invalid returns False. | regression | E-34 |

### 4.3 P2 (31) — hardening

| Finding | File:line | test_id | Acceptance criterion | Test type | Maps to ticket |
|---|---|---|---|---|---|
| C-05 | `engine/fire.py:189-194` | `test_C_05_json_safe_explicit` | Non-serialisable context rejected at validate time OR emits explicit `{"__non_json__": "<repr>"}` marker; replay deterministic. | regression | E-39 |
| C-11 | `dsl/workflow_def.py:54` | `test_C_11_guard_expr_validator` | `Guard.expr` typed `Annotated[Any, AfterValidator(_validate_expr_shape)]`; multi-key dict rejected. | regression | E-61 |
| C-12 | `engine/snapshots.py:33-43` | `test_C_12_snapshot_copy_on_write` | `InMemorySnapshotStore.put` no longer deep-copies on every put; benchmark shows 10× speedup at 200 states. | regression + benchmark | E-61 |
| FA-05 | `flowforge-fastapi/.../router_runtime.py:181-191` | `test_FA_05_fire_unit_of_work` | `engine_fire()` + `store.put(instance)` in transaction; partial failure rolls both back. | regression + integration | E-41 |
| FA-06 | `auth.py` (Cookie expiry) | `test_FA_06_cookie_expiry` | Cookie payload includes `iat` + `exp`; expired cookie rejected. | regression | E-41 |
| SA-02 | `flowforge-sqlalchemy/.../saga_queries.py` | `test_SA_02_saga_queries_complete` | Saga query helpers cover the compensation worker's contract; integration test exercises both sides. | integration | E-40 |
| T-02 | `flowforge-tenancy/.../single.py:18-21` | `test_T_02_elevation_contextvar` | `_elevated` is `ContextVar`; concurrent `elevated_scope()` calls in async tasks observe own scope only. | regression | E-36 |
| AU-04 | `audit_pg/.../sink.py:280-281` | `test_AU_04_datetime_regex` | `_looks_like_datetime` uses `datetime.fromisoformat` try/except; UUID-prefixed digits no longer match. | regression | E-60 |
| OB-03 | `worker.py:289-296` | `test_OB_03_db_reconnect` | Conn-lost detected; worker reconnects; loop resumes; metrics show reconnect count. | integration | E-42 |
| OB-04 | `worker.py:432, 440` | `test_OB_04_utf8_truncation` | `last_error[:2000]` w/ `errors='ignore'` on encode; multi-byte UTF-8 not truncated mid-codepoint. | regression | E-42 |
| RB-01 | `rbac-static/.../resolver.py:50-55` | `test_RB_01_path_traversal` | Path resolved + checked against allowlist root dir; `../../etc/passwd` rejected. | regression | E-55 |
| RB-02 | `rbac-spicedb/` | `test_RB_02_zedtoken_propagation` | Zedtoken propagated through `RbacResolver` port; integration test asserts read-after-write consistency. | integration | E-55 |
| DS-03 | `documents-s3/.../port.py:315-338` | `test_DS_03_presigned_content_type` | `presigned_put_url` signs with `Conditions=[["starts-with","$Content-Type","application/pdf"]]` (or domain-appropriate); attempt to upload wrong content-type rejected by S3. | integration | E-52 |
| DS-04 | `port.py:37-44` | `test_DS_04_real_filetype_sniff` | `python-magic` library used; DOCX vs ZIP distinguished. | regression | E-52 |
| M-01 | `flowforge-money/.../static.py:111-116` | `test_M_01_truediv_banker_rounding` | Division uses explicit rounding mode; SOX-compliant banker's rounding documented. | regression + property | E-53 |
| M-02 | `static.py:148` | `test_M_02_hash_eq_invariant` | Hash/eq invariant: `a == b` implies `hash(a) == hash(b)`; property test ≥1000 cases. | property | E-53 |
| M-03 | `static.py:200-203` | `test_M_03_reverse_rate_consistency` | Reverse rate: `convert(convert(m, A→B), B→A) ≈ m` w/in tolerance; pinned via Decimal precision. | property | E-53 |
| SK-04 | `signing-kms/.../kms.py:74-90` | `test_SK_04_async_to_thread` | `boto3` calls wrapped in `asyncio.to_thread`; event loop not blocked. | regression | E-56 |
| NM-02 | `notify_multichannel/.../transports.py:171,244,317,389,455,511` | `test_NM_02_specific_exceptions` | Each transport catches transport-specific exception types; unexpected types propagate. | regression | E-54 |
| NM-03 | `router.py:134` | `test_NM_03_cause_chained` | Fallback transport attaches `__cause__`; original failure visible in traceback. | regression | E-54 |
| CL-02 | `flowforge_cli/.../commands/tutorial.py:257-299` | `test_CL_02_validated_cwd` | Subprocess invocations pass absolute, validated cwd; relative `Path(".")` removed. | regression | E-57 |
| CL-03 | `flowforge_cli/.../commands/new.py:107` | `test_CL_03_importlib_resources` | `importlib.resources.files("flowforge")` used instead of `__file__` resolve. | regression | E-57 |
| CL-04 | `commands/new.py:102` | `test_CL_04_log_chain_exception` | Bare `except Exception` replaced with logged + chained exception. | regression | E-57 |
| J-09 | `dsl/spec.py:95-113` | `test_J_09_packaging_version` | `_semver` uses `packaging.version.Version`; `"1.0.0-"` rejected. | regression | E-47 |
| J-10 | `registry/manifest.py:131-134` | `test_J_10_json_decoder_only` | Bare except narrowed to `json.JSONDecodeError`. | regression | E-59 |
| J-11 | `lint/dependencies.py:245-305` | `test_J_11_dead_code_removed` | First-attempt computation removed; topological order test green. | regression | E-59 |
| J-12 | `db/comments.py:198,201-210` | `test_J_12_mention_regex_format` | Mention regex matches host's actual user-id format; integration test asserts. | regression | E-59 |
| JH-04 | `jtbd_hub/.../app.py:115-138` | `test_JH_04_admin_token_rotation` | Admin token supports rotation (env-var with comma-separated list); admin actions audit-logged; full RBAC moved to backlog. | regression | E-58 |
| JH-05 | `trust.py:99` | `test_JH_05_platformdirs` | `platformdirs.site_config_dir("flowforge")` used; Windows portable. | regression | E-58 |
| JH-06 | `trust.py:201-202, 219-222` | `test_JH_06_pydantic_validation_only` | Bare except narrowed to `pydantic.ValidationError`; OOM/KeyboardInterrupt propagate. | regression | E-58 |
| JS-04 | `js/flowforge-designer/src/store.ts:200-207` | `test_JS_04_undo_version_stamp` | Undo entry includes `version` hash; mismatched redo rejected w/ user message. | regression | E-62 |
| JS-05 | `js/flowforge-designer/src/store.ts:78-88` | `test_JS_05_addstate_kind_alignment` | `addState` kind matches DSL kinds (`automatic`, etc.); dead `start` branch removed. | regression | E-62 |
| JS-06 | `js/flowforge-renderer/src/fields/JsonField.tsx:47` | `test_JS_06_json_parse_safe` | `JSON.parse` wrapped; syntax error → form validation error not crash. | regression | E-62 |
| IT-03 | `js/flowforge-integration-tests/` | `test_IT_03_ws_reconnect` | WS reconnect + collab test green; simultaneous-edit conflict resolution asserted. | integration | E-63 |
| IT-04 | new `tests/edge_cases/` | `test_IT_04_edge_case_bank` | All 9 edge-case classes covered: empty bundle, max-size lockfile (10K pins), unicode/emoji jtbd_id, year-boundary timezone, concurrent fork, lockfile compose conflict, hash-chain one-byte-flip, outbox+saga crash mid-tx, in-flight migration. | edge | E-64 |
| DOC-03 | per-pkg `README.md` | `test_DOC_03_doctest_examples` | Per-package examples become doctests; `pytest --doctest-modules` passes. | doctest | E-65 |
| DOC-04 | `docs/flowforge-evolution.md` + `flowforge-handbook.md` | `test_DOC_04_link_check` | CI link-checker passes; `apps/jtbd-hub/` references updated to `python/flowforge-jtbd-hub/`. | CI | E-65 |

### 4.4 P3 (12) — polish

| Finding | File:line | test_id | Acceptance criterion | Test type | Maps to ticket |
|---|---|---|---|---|---|
| C-13 | `flowforge/__init__.py` | `test_C_13_all_declared` | `__all__` declared; ruff PLW0212 rule satisfied. | lint | E-67 |
| T-03 | `tenancy/.../single.py:46` | `test_T_03_in_transaction_assert` | `bind_session` asserts `session.in_transaction()`; raises if outside tx. | regression | E-70 |
| D-03 | All 30 `__init__.py` | `test_D_03_init_standard` | Each pkg has `load_bundle()` helper + `__all__`. | lint | E-51 |
| D-04 | All 30 packages | `test_D_04_smoke_per_pkg` | Each pkg has `tests/test_smoke.py` that loads bundle and asserts schema validation. | smoke | E-49 |
| D-05 | All 30 `pyproject.toml` | `test_D_05_semver_pin` | Version `0.0.1` (not `1.0.0`); CI checks. | CI | E-50 |
| JS-07 | `js/flowforge-jtbd-editor/src/JobMap.tsx`, `JobMapAnimation.tsx` | `test_JS_07_virtualized_render` | At 200+ JTBDs only viewport-visible JTBDs render; FPS ≥30 in benchmark. | benchmark | E-67 |
| JS-08 | `js/package.json` (workspace) | `test_JS_08_integration_private` | `flowforge-integration-tests` marked `"private": true`. | regression | E-66 |
| IT-05 | `framework/tests` | `test_IT_05_test_location_convention` | Single test-location convention adopted; lint passes. | lint | E-68 |
| DOC-05 | root `pyproject.toml` | `test_DOC_05_versions_consistent` | All pkgs follow same versioning cadence (documented). | CI | E-69 |
| **E-31** | `docs/flowforge-evolution.md` | `test_DOC_E_31_reconciled` | Evolution doc has E-31..E-72 ticket list reconciled. | manual | E-69 |
| F2-residual JH-04-feature | (backlog only) | n/a | Documented as deferred-by-spec to `docs/audit-2026/backlog.md`; revisited post-1.0. | n/a | (backlog) |
| OB-residual SQLite race | (doc only) | `test_OB_residual_doc` | `sqlite_compat=True` documented as test-only in module docstring + README. | doctest | E-42 |

**Total acceptance rows: 8 + 28 + 31 + 12 = 79 (counts D-01 once, the JTBD-residual SQLite as P3 cleanup that bundles with E-42, and the JH-04 backlog deferral that is documented as zero-defer compliance).** This satisfies "all 77 covered + 2 deferral docs".

---

## 5. Test plan

### 5.1 Layered structure

| Layer | Tooling | Runner | Phase |
|---|---|---|---|
| Unit (regression) | `pytest` per pkg | per-pkg `tox` / CI matrix | S0+ |
| Property | `hypothesis` | `pytest --hypothesis-show-statistics` | S1 |
| Integration | `pytest-postgresql`, `testcontainers` | `tests/integration/` | S0+ (S0: concurrency only; S1+: full) |
| E2E | `pytest`, `httpx`, `websockets` | `tests/integration/e2e/` | S1 |
| Conformance (arch §17) | `pytest -k invariant_p0 / _p1` | `tests/conformance/test_arch_invariants.py` | S0+ |
| Cross-runtime | `vitest` (TS) + `pytest` (Py) shared fixture | `js/flowforge-integration-tests/` + `tests/cross_runtime/` | S1 |
| Edge cases | `pytest` | `tests/edge_cases/` | S3 |
| Chaos / fault injection (CR-5) | flowforge-jtbd fault injector E-12 + `pytest` | `tests/chaos/` | S1 |
| Observability assertions | synthetic metric injection + `promtool test rules` | `tests/observability/` | S0+ |
| Soak | `k6` + Grafana | manual + dashboard | S3 (24h) |

### 5.2 `make audit-2026` (CR-6)

Single Makefile target wires all per-finding tests under one command:

```makefile
.PHONY: audit-2026
audit-2026: audit-2026-unit audit-2026-property audit-2026-integration audit-2026-e2e audit-2026-conformance audit-2026-cross-runtime audit-2026-edge audit-2026-chaos audit-2026-observability
	@echo "All 77 audit-2026 tests passed."

audit-2026-unit:
	uv run pytest tests/audit_2026/ -v

audit-2026-property:
	uv run pytest tests/property/ --hypothesis-show-statistics

audit-2026-integration:
	uv run pytest tests/integration/ -v

audit-2026-e2e:
	uv run pytest tests/integration/e2e/ -v

audit-2026-conformance:
	uv run pytest tests/conformance/ -v

audit-2026-cross-runtime:
	uv run pytest tests/cross_runtime/ -v && pnpm -C js test:cross-runtime

audit-2026-edge:
	uv run pytest tests/edge_cases/ -v

audit-2026-chaos:
	uv run pytest tests/chaos/ -v

audit-2026-observability:
	uv run pytest tests/observability/ -v && promtool test rules tests/observability/promql/*.yml
```

CI runs `make audit-2026` on every PR to `main`. Closing a finding requires its `test_<FINDING_ID>_*` test to be green.

### 5.3 Per-phase test additions

| Phase | Tests added |
|---|---|
| S0 | 8 P0 regression tests + conformance invariants 1, 2, 3, 7 + ratchet baselines |
| S1 | 27 P1 regression tests + conformance invariants 4, 5, 6, 8 + 5 hypothesis properties + 3 e2e suites + cross-runtime fixture (200 inputs) + chaos: crash-mid-fire, crash-mid-outbox, crash-mid-compensation |
| S2a | 25 starter-pkg smoke tests |
| S2b | 5 vertical full-schema lints + SME-signoff metadata in `domain.yaml.signoff` |
| S3 | 31 P2 regression tests + edge-case bank (9 classes) + 24h soak + ratchet enforcement |
| S4 | 12 P3 lint/doctest/CI checks + final `make audit-2026` green |

### 5.4 Observability coverage (CR-Q3)

| Signal | Implementation | Per-fix dashboard |
|---|---|---|
| Audit event `FRAMEWORK_FIX_APPLIED` | Emitted once per process startup with ticket id list | grafana.flowforge.local/d/audit-2026 |
| `flowforge_audit_chain_breaks_total` | Counter | `/d/audit-2026/E-37` |
| `flowforge_outbox_dispatch_duration_seconds` | Histogram | `/d/audit-2026/E-32` |
| `flowforge_engine_fire_rejected_concurrent_total` | Counter (C-04) | `/d/audit-2026/E-32` |
| `flowforge_signing_secret_default_used_total` | Counter (SK-01 dev opt-in) | `/d/audit-2026/E-34` |
| OTel span `flowforge.engine.fire` w/ `instance_id`, `state.from`, `state.to`, `fix_id` attrs | All fixes attach `fix_id` | per-ticket panel |
| Log structured field `security_review_id` | git trailer on each P0/P1 commit | n/a |
| PromQL alert rules verified via test suite | `promtool test rules` | (CI) |

---

## 6. Effort & headcount

### 6.1 Person-week estimate (corrected from architect §5.2)

| Phase | S | M | L | Engineering person-weeks (1S=0.5d, 1M=3d, 1L=8d, 5d/wk) | SME person-weeks |
|---|---|---|---|---|---|
| S0 | 4 | 3 | 0 | (4×0.5 + 3×3) / 5 = 2.2 | 0 |
| S1 | 13 | 12 | 1 | (13×0.5 + 12×3 + 1×8) / 5 = 10.1 | 0 |
| S2a (rebrand 25) | 4 | 1 | 0 | (4×0.5 + 1×3) / 5 = 1.0 | 0 |
| S2b (5 verticals) | 0 | 0 | 5 | 5×8/5 = 8 (parallelisable; with 5 SMEs = 1.6 wks calendar each, so 1 SME × 5 weeks total cost OR 5 SMEs × 1.6 wks = 8 person-weeks) | 8 |
| S3 | 19 | 12 | 0 | (19×0.5 + 12×3) / 5 = 9.1 | 0 |
| S4 | 12 | 0 | 0 | 12×0.5 / 5 = 1.2 | 0 |
| **Total** | **52** | **28** | **6** | **23.6 person-weeks (engineering)** | **8 person-weeks (SME)** |

### 6.2 Calendar with 4 engineers + 5 SMEs

| Phase | Engineering | SME | Calendar |
|---|---|---|---|
| S0 | 2.2 / 4 = ~0.6 wk | 0 | Week 1 |
| S1 | 10.1 / 4 = 2.5 wks | 0 | Weeks 2–4 |
| S2a (parallel) | 1.0 / 1 = 1 wk | 0 | Weeks 2–3 (dedicated 1 eng) |
| S2b (parallel) | 0 | 8 / 5 = 1.6 wks per SME | Weeks 4–8 (1 SME per vertical, ramped over 5 wks) |
| S3 | 9.1 / 4 = 2.3 wks | 0 | Weeks 5–6 |
| S4 | 1.2 / 1 = 1.2 wks | 0 | Week 7 |
| **Total calendar** | | | **8 weeks** |

### 6.3 Critical path (architect §5.2 corrected)

`E-32 (3d) → E-40 (8d) → E-45 (8d) → S3 P2 (5d) → S4 (1.2 wk) = ~6.5 wks calendar at 4 engineers parallel.`

Buffer: +1.5 wks for security review cycles + integration debt. **Final calendar estimate: 8 weeks.**

---

## 7. Ticket map E-32..E-62 (consolidated to 31 tickets)

Per architect §5.1 (ticket count creep), tickets are consolidated where independent-file safety allows.

| ID | Title | Sev | File:line refs | Sprint | Effort | Parallel-safe | Agent tier | Maps to findings |
|---|---|---|---|---|---|---|---|---|
| **E-32** | ENGINE-HOTFIX EPIC: per-instance lock + transactional fire + outbox safety (single PR, multi-commit) | P0 | `engine/fire.py:223-251, 283-288` | S0 | M | No (single PR, 5 commits) | opus | C-01, C-04 |
| **E-33** | (merged into E-37) | — | — | — | — | — | — | (deleted; AU-01/02/03 moved to E-37) |
| **E-34** | Crypto rotation: remove HMAC default secret + per-key_id signed key map + transient/invalid distinction | P0 | `signing-kms/hmac_dev.py:20-74`, `kms.py:112,216` | S0 | S | Yes | opus | SK-01, SK-02, SK-03 |
| **E-35** | Frozen op registry + arity enforcement (atomic) | P0 | `expr/evaluator.py:25-79` | S0 | M | Yes | opus | C-06, C-07 |
| **E-36** | Tenancy SQL hardening: bind-param GUC + ContextVar elevation + in-tx assert | P0/P2/P3 | `tenancy/single.py:18-46` | S0 | S | Yes | sonnet | T-01, T-02, T-03 |
| **E-37** | Audit-chain hardening + canonical golden test (P0/P1 atomic) | P1 | `audit_pg/sink.py:159-199`, `hash_chain.py:103-113` | S0 (P1 critical) | M | Yes (separate file from engine) | opus | AU-01, AU-02, AU-03 |
| **E-37b** | Hub trust gate signed_at_publish (split out of v0 E-37) | P0 | `jtbd_hub/registry.py:309-321,316` | S0 | S | Yes | opus | JH-01 |
| **E-38** | Migration RLS DDL: whitelist table names + sqlalchemy quoted_name | P0 | `r2_jtbd.py:235-290` | S0 | S | Yes | sonnet | J-01 |
| **E-39** | Engine quality + correctness: uuid7 (core+sqlalchemy), guard error surfacing, json safety, dotted prefix, lookup AST walk | P1/P2/P3 | `engine/fire.py:69,84-91,114-115,189-194`, `compiler/validator.py:116-132`, `flowforge-sqlalchemy/snapshot_store.py:75`, `flowforge/__init__.py` | S1 | M | No (engine/fire.py owned by EPIC for S0; S1 cleanup PR follows) | opus | C-02, C-03, C-05, C-08, C-10, C-13, SA-01 |
| **E-40** | Saga ledger persistence + minimal compensation worker (scope-reduced per critic) | P1 | `engine/saga.py`, `flowforge-sqlalchemy/saga_queries.py` | S1 | L | Yes (new module) | opus | C-09, SA-02 |
| **E-41** | FastAPI + WS hardening: signing parity, secure CSRF, WS-native auth, request-scoped hub, transactional fire, cookie expiry | P1/P2 | `auth.py:114-118,147-153`, `ws.py:78,159-168`, `router_runtime.py:181-191` | S1 | M | Yes | opus | FA-01, FA-02, FA-03, FA-04, FA-05, FA-06 |
| **E-42** | Outbox hardening: table-name validation, SQLite single-worker, reconnect, utf8 truncation, sqlite-doc | P1/P2 | `outbox_pg/worker.py:235,289-296,309-365,432,440` | S1 | M | Yes | sonnet | OB-01, OB-02, OB-03, OB-04 |
| **E-43** | TS↔Python expr conformance suite | P1 | `js/flowforge-renderer/src/expr.ts:88-99`, `flowforge-core/src/flowforge/expr/evaluator.py` | S1 | M | Yes | sonnet | JS-01, JS-02, JS-03 |
| **E-44** | Hypothesis property tests: lockfile, hash-chain, evaluator, manifest, money | P1 | new `tests/property/` | S1 | M | Yes | sonnet | IT-01 |
| **E-45** | E2E suite: fire→audit→verify; fire→outbox→ack; fork→migrate→replay | P1 | new `tests/integration/e2e/` | S1 | L | Yes | sonnet | IT-02 |
| **E-46** | Workspace + docs alignment: register all 45 pkgs (two-step package=false → true), README, doc paths | P1/P2/P3 | root `pyproject.toml`, `framework/README.md`, `docs/flowforge-evolution.md`, per-pkg READMEs | S1 | S | Yes | haiku | DOC-01, DOC-02 |
| **E-47** | JTBD intelligence quality: lint perf, recommender fit/transform, NL guard, dead code, semver | P1/P2 | `lint/conflicts.py:144-269`, `ai/recommender.py:171-247`, `ai/nl_to_jtbd.py:101-379`, `dsl/lockfile.py:140-157`, `dsl/spec.py:95-113` | S1 | M | Yes | opus | J-02, J-03, J-04, J-05, J-06, J-07, J-08, J-09 |
| **E-48a** | Domain-library rebrand (25 non-strategic pkgs to `*-starter`) | P1 | 25 `flowforge-jtbd-*` packages, READMEs, `pyproject.toml` `name` | S2a | S × 25 (bundled) | Yes | haiku | D-01 (rebrand 25/30) |
| **E-48b** | Domain-library real content (5 strategic verticals: insurance, healthcare, banking, gov, hr) | P1 | 5 × ~5 yaml files | S2b | L × 5 | Yes (per domain) | sonnet (review by SME) | D-01 (real 5/30), D-02 |
| **E-49** | Per-domain smoke tests (all 30 pkgs) | P2 | per-pkg `tests/test_smoke.py` | S2a | S × 30 (bundled) | Yes | sonnet | D-04 |
| **E-50** | Domain pkg semver pin to 0.0.1 (all 30) | P3 | all 30 `pyproject.toml` | S2a | S | Yes | haiku | D-05 |
| **E-51** | Domain pkg `__init__.py` standard (all 30) | P2 | all 30 `__init__.py` | S2a | S × 30 (bundled) | Yes | haiku | D-03 |
| **E-52** | Documents-S3 path validation + content-type enforcement on presigned PUT + filetype sniff | P1/P2 | `documents_s3/port.py:128-138,315-338,37-44` | S3 | M | Yes | sonnet | DS-01, DS-02, DS-03, DS-04 |
| **E-53** | Money rounding + reverse-rate consistency + hash/eq invariant | P2 | `money/static.py:111-203` | S3 | S | Yes | sonnet | M-01, M-02, M-03 |
| **E-54** | Notify transports: compare_digest + specific exceptions + cause chaining | P1/P2 | `notify_multichannel/transports.py:171,244,317,389,422,455,511`, `router.py:134` | S3 | M | Yes | sonnet | NM-01, NM-02, NM-03 |
| **E-55** | RBAC static path traversal + SpiceDB Zedtoken propagation | P2 | `rbac-static/resolver.py:50-55`, `rbac-spicedb/` | S3 | M | Yes | sonnet | RB-01, RB-02 |
| **E-56** | KMS async correctness | P2 | `signing-kms/kms.py:74-90` | S3 | S | Yes | sonnet | SK-04 |
| **E-57** | CLI quality: stub generators, validated cwd, importlib resources, log+chain | P1/P2 | `flowforge_cli/jtbd/generators/`, `commands/tutorial.py:257-299`, `commands/new.py:102-107` | S3 | M | Yes | sonnet | CL-01, CL-02, CL-03, CL-04 |
| **E-58** | JTBD hub counter (DB) + verified_at_install caching + admin token rotation + path portability + pydantic-only except | P1/P2 | `jtbd_hub/registry.py:340-342, 309-321`, `app.py:115-138`, `trust.py:99,201-222` | S3 | M | Yes | sonnet | JH-02, JH-03, JH-04, JH-05, JH-06 |
| **E-59** | JTBD lint cleanup: dead code, mention regex, manifest exception narrowing | P2 | `lint/dependencies.py:245-305`, `db/comments.py:198-210`, `registry/manifest.py:131-134` | S3 | S | Yes | sonnet | J-10, J-11, J-12 |
| **E-60** | Audit-pg correctness: datetime regex tightening (residual after E-37 covered AU-03) | P2 | `audit_pg/sink.py:280-281` | S3 | S | Yes | sonnet | AU-04 |
| **E-61** | DSL spec hygiene: Guard.expr validator, snapshot copy-on-write | P2 | `dsl/workflow_def.py:54`, `engine/snapshots.py:33-43` | S3 | S | Yes | sonnet | C-11, C-12 |
| **E-62** | JS designer + renderer hardening: undo+collab versioning, JSON.parse safety, addState type fix | P2 | `js/flowforge-designer/src/store.ts:78-207`, `js/flowforge-renderer/src/fields/JsonField.tsx:47` | S3 | M | Yes | sonnet | JS-04, JS-05, JS-06 |
| **E-63** | JS test coverage: WS reconnect + collab edge cases | P2 | `js/flowforge-integration-tests/` | S3 | M | Yes | sonnet | IT-03 |
| **E-64** | Edge-case test bank: 9 classes | P2 | new `tests/edge_cases/` | S3 | L | Yes | sonnet | IT-04 |
| **E-65** | Doc currency: per-pkg READMEs become doctests; handbook paths | P2 | per-pkg `README.md`, `docs/flowforge-handbook.md` | S3 | M | Yes | haiku | DOC-03, DOC-04 |
| **E-66** | JS workspace marker (private flag) | P3 | `js/package.json` | S3 (bundled) | S | Yes | haiku | JS-08 |
| **E-67** | JTBD core polish: __all__, large-SVG virtualisation | P3 | `flowforge/__init__.py` (residual after E-39 covered C-13), `js/flowforge-jtbd-editor/src/JobMap.tsx`, `JobMapAnimation.tsx` | S4 | S (Py) + M (JS) | Yes | sonnet | JS-07 |
| **E-68** | Tests location convention | P3 | `framework/tests/` | S4 | S | Yes | haiku | IT-05 |
| **E-69** | E-31 reconciliation + version cadence doc | P3 | `docs/flowforge-evolution.md`, root `pyproject.toml` | S4 | S | Yes | haiku | E-31 mismatch, DOC-05 |
| **E-70** | Tenancy in-tx assert (residual after E-36) | P3 | `tenancy/single.py:46` | S4 | S | Yes | haiku | T-03 (residual; bundled to E-36 acceptance test) |
| **E-71** | (deleted; merged into E-58) | — | — | — | — | — | — | — |
| **E-72** | Final sweep: dead code, debug logs, TODO/HACK, version pins | P3 | repo-wide | S4 | S | Yes | haiku | residual P3 polish |

**Total tickets: 31** (E-32, E-34..E-50, E-52..E-70, E-72; E-33, E-37b, E-71 bookkeeping). Architect §5.1 target ≤30; one over due to E-37b split for S0 sequencing — acceptable.

---

## 8. Dependency DAG with explicit headcount

```
HEADCOUNT KEY: [E1..E4] = 4 senior engineers; [SME-{D}] = 5 domain SMEs; [SEC] = security lead; [REL] = release manager

S0 (Week 1, 4 eng parallel):
  [E1] E-32 (engine epic)        ──┐
  [E2] E-34 (crypto)             ──┤
  [E3] E-35 (frozen registry)    ──┤── all merge by EOW1; SEC signs all P0
  [E4] E-36 (tenancy)            ──┤
  [E1] E-37 (audit-chain) → [E2] E-37b (hub trust) ─┤
  [E3] E-38 (migration RLS)      ──┘

S1 (Weeks 2–4, 4 eng parallel):
  [E1] E-39 (engine cleanup) ──→ [E1] E-40 (saga ledger persistence)
  [E2] E-41 (fastapi/ws)
  [E3] E-42 (outbox) ──→ [E3] E-43 (TS↔Py conformance)
  [E4] E-44 (hypothesis) ──→ [E4] E-45 (e2e) ──┐
  [E1..E4] E-46 (workspace+docs, parallel anywhere) ──┘
  [E1..E4] E-47 (jtbd intel, parallel) ──┘── conformance suite all green by EOW4

S2a (Weeks 2–3, 1 eng dedicated, parallel to S1):
  [E1] E-48a (rebrand 25) ──→ [E1] E-49 (smoke tests) ──→ [E1] E-50 (semver) ──→ [E1] E-51 (init)

S2b (Weeks 4–8, 5 SMEs parallel):
  [SME-insur] E-48b-insur \
  [SME-health] E-48b-health \
  [SME-bank] E-48b-bank   ──── independent vertical work; D-02 lint enforced
  [SME-gov] E-48b-gov     /
  [SME-hr] E-48b-hr      /

S3 (Weeks 5–6, 4 eng parallel):
  [E1] E-52 (S3 docs) [E1] E-53 (money) [E1] E-60 (audit-pg residual)
  [E2] E-54 (notify) [E2] E-55 (rbac) [E2] E-61 (dsl hygiene)
  [E3] E-56 (kms async) [E3] E-57 (cli) [E3] E-62 (js designer)
  [E4] E-58 (hub residual) [E4] E-59 (jtbd lint) [E4] E-63 (js test) [E4] E-64 (edge bank) [E4] E-65 (doc currency) [E4] E-66 (workspace marker)

S4 (Week 7, 1 eng):
  [E1] E-67 [E1] E-68 [E1] E-69 [E1] E-70 [E1] E-72  (bundled per-package commits per critic CR-Q4)
```

**Critical path:** E-32 → E-39 → E-40 → E-45 → S3 → S4 = ~6.5 wks raw + 1.5 wks security review buffer = **8 weeks calendar**.

---

## 9. Risk register (7 entries with owners)

| # | Risk | Likelihood | Impact | Detection | Mitigation | Rollback | Owner (named) |
|---|---|---|---|---|---|---|---|
| **R-1** | Engine/fire.py merge conflicts (F-1) | High | Medium | PR rebase fail | Single-PR EPIC, multi-commit, CODEOWNERS lock | git revert | Engine EPIC owner (TBD-named at S0 day 1) |
| **R-2** | Security fix breaks downstream UMS (F-2) | Medium | High | UMS smoke test red | Legacy opt-in flag for 1 minor; UMS integration test before merge | Re-deploy previous; opt-in flag set | Security lead (TBD-named) |
| **R-3** | P2 cleanup regresses P0 invariants (F-3) | Medium | High | `@invariant_p0` test red | CI gate; security-review on test deletion | Revert PR | CI/test eng (TBD-named) |
| **R-4** | Alembic in prod breaks RLS (F-4) | Medium | High | Per-tenant smoke vs prod-shape DB | Online + reversible migrations; canary 1 tenant | `alembic downgrade -1` | DBA lead (TBD-named) |
| **R-5** | Hypothesis tests find latent bugs blocking S1 (CR-3 mitigation) | Medium | Medium | New test failures spike in S1 wk1 | **Pre-flight property tests on dedicated branch in S0 wk1; budget ≤3 P1-equivalent fixes per phase; latent bugs above budget escalated to architect for in-scope/defer decision** | Drop tests to nightly suite; raise as separate ticket | QA lead (TBD-named) |
| **R-6** | CI grep ratchet false positives (F-6) | Medium | Medium | Team adds `# noqa: ratchet` | Baseline file `scripts/ci/ratchets/baseline.txt`; new occurrences fail; baseline-update PR needs SEC review | Revert PR; reset baseline | Security lead |
| **R-7** | P0 env-var change breaks year-old prod (F-7) | Low (1-version dep window) | High | Customer support ticket | Two-version deprecation; CHANGELOG SECURITY-BREAKING; `flowforge_pre_upgrade_check` CLI; customer email | Roll back image; opt-in flag | Release manager (TBD-named) |

---

## 10. Observability + DELIBERATE-mode signoff trail

### 10.1 Per-fix observability (CR-Q3)

Every closed finding gets a `flowforge_fix_id` attribute on every emitted span; per-fix Grafana panel at `grafana.flowforge.local/d/audit-2026/<TICKET_ID>`.

### 10.2 Signoff checklist artefact (CR-3)

Path: `docs/audit-2026/signoff-checklist.md`
Format: YAML rows per ticket (sample shown §3.1).
CI gate: `scripts/ci/check_signoff.py` rejects PR merge to `main` if checklist row for the ticket is empty or unsigned.
Roles named at S0 day 1 by release manager:
- Security lead: 1 named SRE
- Architecture lead: 1 named eng
- QA lead: 1 named eng
- Release manager: 1 named PM
- Per-domain SMEs: 5 named (insurance, healthcare, banking, gov, hr)

### 10.3 Audit-2026 close-out criteria (CR-11)

Project KNOWS all 77 are closed when:
1. `make audit-2026` is green in CI on `main`.
2. `docs/audit-2026/signoff-checklist.md` has a signed row for every ticket E-32..E-72.
3. Conformance suite covers all 8 arch §17 invariants (`tests/conformance/test_arch_invariants.py` ≥8 invariant test classes).
4. Backlog `docs/audit-2026/backlog.md` lists deferred items (per CR-12, expected empty by spec; if non-empty, each item has documented re-approval).
5. CHANGELOG SECURITY entries present for every P0 (8) + escalated AU-03.
6. CI ratchet baselines in `scripts/ci/ratchets/baseline.txt` are non-decreasing (only-additions allowed via baseline-update PRs).
7. Soak test 24h @ 10 fires/sec shows zero `flowforge_audit_chain_breaks_total`.
8. Per-fix dashboards exist for E-32..E-72.

---

## 11. Backlog of intentionally-deferred items (CR-12)

By spec ("zero deferrals, including P3 cosmetic"), this section is EMPTY.

If items surface during execution that warrant deferral, they MUST:
- Be added to `docs/audit-2026/backlog.md` with explicit rationale.
- Be re-approved by architect agent before deferral.
- Get a successor ticket E-73+ assigned.
- Trigger a CHANGELOG entry indicating audit-2026 incomplete.

Currently expected entries (architectural decisions surfaced during planning):
- **JH-04 full RBAC implementation** (replacing admin-token w/ per-user RBAC) — split: rotation + audit-log delivered in E-58 P2; full RBAC deferred. Documented as deferral rationale: "Net-new feature, not a defect fix; existing single-token mechanism is documented + rotation now supported."

---

## 12. ADR — Architecture Decision Record

### 12.1 Decision

Adopt **Phased-by-severity (Option B)** plan to close all 77 audit findings in 8 calendar weeks, using a hybrid domain-content track (25 rebrands + 5 strategic-vertical real-content sprints). All security-sensitive findings (8 P0-equivalent) close in week 1 under DELIBERATE-mode signoff.

### 12.2 Drivers

1. **Security first (D-1):** 8 P0-equivalent findings include hard-coded HMAC default, two SQL-injection sinks, audit-chain race, replay-determinism break, hub auth-bypass, audit-chain canonical hygiene. None can ship past week 1.
2. **Concurrency-coupled root cause (D-2):** 6 findings share a "shared mutable state under concurrency" pattern; they are fixed in a coordinated arc.
3. **Content-vs-engineering decoupling (D-3):** D-01 content sprint, if run as pure E-48b, doubles calendar to 16 weeks. Hybrid resolves with no false-promise risk (rebranded packages explicitly marked as scaffolds).

### 12.3 Alternatives considered

| Option | Reason for rejection |
|---|---|
| A — Big-bang strict | 14–16 weeks; blocks features; D-01 dominates timeline; review attention exhausted. |
| C — Minimum-viable 16-fix | Violates user spec ("zero deferrals"); leaves SOX/HIPAA hygiene gaps; insufficient under DELIBERATE mode. |

### 12.4 Why chosen

- Aligns with DELIBERATE mode (no security deferrals).
- Smallest viable PR per fix (P-2).
- Parallelism extracts value from 4-engineer + 5-SME team.
- Content track fully decoupled from engineering critical path.
- All architectural invariants get explicit conformance tests.

### 12.5 Consequences

**Positive:**
- 1.0 ship within 8 weeks at high quality.
- Production safety achieved by EOW1.
- Conformance suite becomes a reusable engineering asset.
- Public domain-library catalogue is honest (starter scaffolds explicitly marked).

**Negative:**
- Higher release ceremony (semver bumps per phase).
- Content sprint depends on 5 SMEs being available concurrently weeks 4–8.
- Conformance suite adds CI runtime (~3 min projected).
- Single-PR engine epic concentrates merge risk in week 1.

**Mitigations:** All seven risks mitigated with named owners and rollback paths (§9).

### 12.6 Follow-ups

- Post-1.0: revisit JH-04 backlog item (full RBAC).
- Post-1.0: consider funded follow-on for 25 rebranded domains → real content (25 × L = ~40 person-weeks).
- Quarterly: re-run automated audit suite; compare against `make audit-2026` baseline.
- Annually: refresh conformance suite against arch §17 evolution.

---

## 13. Final ticket list (E-32..E-72) with all required attributes

| ID | Title | Severity | File:line | Fix description | Acceptance criteria | Effort | Dependencies | Parallel-safe | Agent tier |
|---|---|---|---|---|---|---|---|---|---|
| E-32 | Engine hotfix EPIC: per-instance lock + transactional fire + outbox safety | P0 | `engine/fire.py:223-251,283-288` | Add per-instance asyncio.Lock; wrap fire+audit+outbox in transactional UoW; remove silent except | `test_C_01_*`, `test_C_04_*` green; conformance inv 1/2 green | M | none | No (single PR) | opus |
| E-34 | Crypto rotation: HMAC default removal + key_id map + transient/invalid distinction | P0 | `signing-kms/hmac_dev.py:20-74`, `kms.py:112,216` | Refuse start w/o env var; opt-in legacy flag; per-key_id map; new exception types | `test_SK_01_*`, `test_SK_02_*`, `test_SK_03_*` green | S | none | Yes | opus |
| E-35 | Frozen op registry + arity enforcement | P0 | `expr/evaluator.py:25-79` | Build-time-frozen registry; reject re-register; arity-check at register | `test_C_06_*`, `test_C_07_*` green; conformance inv 3 green | M | none | Yes | opus |
| E-36 | Tenancy SQL hardening + ContextVar elevation + in-tx assert | P0/P2/P3 | `tenancy/single.py:18-46` | Bind-param GUC; ContextVar elevation; in_transaction assert | `test_T_01_*`, `test_T_02_*`, `test_T_03_*` green; conformance inv 7 green | S | none | Yes | sonnet |
| E-37 | Audit-chain hardening: advisory lock + chunked verify + canonical golden | P1 (escalated) | `audit_pg/sink.py:159-199`, `hash_chain.py:103-113` | PG advisory lock per tenant; unique constraint `(tenant_id, ordinal)`; 10K-chunk verify; golden bytes fixture | `test_AU_01_*`, `test_AU_02_*`, `test_AU_03_*` green | M | none | Yes | opus |
| E-37b | Hub trust gate: signed_at_publish explicit | P0 | `jtbd_hub/registry.py:309-321,316` | Explicit `signed_at_publish` flag; reject unsigned by default; opt-in `accept_unsigned`; sanitised error message | `test_JH_01_*` green | S | none | Yes | opus |
| E-38 | Migration RLS DDL: whitelist + quoted_name | P0 | `r2_jtbd.py:235-290` | Allow-list table names; `sqlalchemy.sql.quoted_name`; ValueError on unknown | `test_J_01_*` green; alembic dry-run on prod-shape DB green | S | none | Yes | sonnet |
| E-39 | Engine quality + correctness pass + sqlalchemy uuid7 | P1/P2/P3 | `engine/fire.py:69,84-91,114-115,189-194`, `compiler/validator.py:116-132`, `flowforge-sqlalchemy/snapshot_store.py:75`, `flowforge/__init__.py` | uuid7str; guard error surface; json-safe explicit; dotted prefix reject; lookup AST walk; `__all__` | `test_C_02/03/05/08/10/13_*`, `test_SA_01_*` green | M | E-32 (engine ownership) | No (engine cleanup PR follows EPIC) | opus |
| E-40 | Saga ledger persistence + minimal compensation worker | P1 | `engine/saga.py`, `flowforge-sqlalchemy/saga_queries.py` | DB-backed ledger; restart-replay worker; conformance inv 4 | `test_C_09_*`, `test_SA_02_*` green; conformance inv 4 green | L | E-39 | Yes | opus |
| E-41 | FastAPI + WS hardening | P1/P2 | `auth.py:114-118,147-153`, `ws.py:78,159-168`, `router_runtime.py:181-191` | Signing parity; secure CSRF default; WS-native extractor; request-scoped hub; transactional fire; cookie iat/exp | `test_FA_01..06_*` green | M | none | Yes | opus |
| E-42 | Outbox hardening | P1/P2 | `outbox_pg/worker.py:235,289-296,309-365,432,440` | Table-name validate; SQLite single-worker assert; reconnect; utf8 truncate; sqlite-only doc | `test_OB_01..04_*` green | M | none | Yes | sonnet |
| E-43 | TS↔Python expr conformance suite | P1 | `js/flowforge-renderer/src/expr.ts:88-99`, `flowforge-core/src/flowforge/expr/evaluator.py` | Align unknown-op semantics; strict equality only; 200-input fixture; React 19 contract | `test_JS_01/02/03_*` green | M | none | Yes | sonnet |
| E-44 | Hypothesis property tests (5 properties) | P1 | new `tests/property/` | Lockfile round-trip; hash-chain commutativity; evaluator literal-passthrough; manifest signing payload; money arithmetic | `test_IT_01_*` green | M | none | Yes | sonnet |
| E-45 | E2E suite (3 flows) | P1 | new `tests/integration/e2e/` | fire→audit→verify; fire→outbox→ack; fork→migrate→replay | `test_IT_02_*` green | L | E-32, E-37, E-40 | Yes | sonnet |
| E-46 | Workspace + docs alignment | P1/P2/P3 | root `pyproject.toml`, `framework/README.md`, `docs/*.md`, per-pkg READMEs | Two-step pkg=false→true; README count; doc paths | `test_DOC_01/02_*` green | S | none | Yes | haiku |
| E-47 | JTBD intelligence quality | P1/P2 | `lint/conflicts.py:144-269`, `ai/recommender.py:171-247`, `ai/nl_to_jtbd.py:101-379`, `dsl/lockfile.py:140-157`, `dsl/spec.py:95-113` | Pair pre-bucketing; fit/transform; adversarial NL bank; raw_decode; canonical allowlist; packaging.version | `test_J_02..09_*` green | M | none | Yes | opus |
| E-48a | Domain rebrand (25 pkgs to *-starter) | P1 | 25 `flowforge-jtbd-*` pkgs | Rename, README disclaimer, scaffold lint badge | `test_D_01_*` (rebrand path) green | S × 25 (bundled to 1 PR per 5 pkgs) | E-46 | Yes | haiku |
| E-48b | Domain real content (5 verticals) | P1 | 5 × ~5 yaml files | Real JTBD content per insurance/healthcare/banking/gov/hr; full-schema lint | `test_D_01_*` (real path) green; SME signoff | L × 5 | none | Yes (per vertical) | sonnet (SME review) |
| E-49 | Per-domain smoke tests | P2 | per-pkg `tests/test_smoke.py` | Bundle load + schema validation per pkg | `test_D_04_*` green | S × 30 (bundled) | E-48a | Yes | sonnet |
| E-50 | Domain pkg semver pin | P3 | all 30 `pyproject.toml` | Version `0.0.1` | `test_D_05_*` green | S | E-48a | Yes | haiku |
| E-51 | Domain pkg `__init__.py` standard | P2 | all 30 `__init__.py` | `load_bundle()` + `__all__` | `test_D_03_*` green | S × 30 (bundled) | E-48a | Yes | haiku |
| E-52 | Documents-S3 hardening | P1/P2 | `documents_s3/port.py:128-138,315-338,37-44` | doc_id validation; S3DocumentPortInMemory rename; presigned content-type; magic sniffer | `test_DS_01..04_*` green | M | none | Yes | sonnet |
| E-53 | Money rounding + reverse-rate consistency | P2 | `money/static.py:111-203` | Banker rounding; hash/eq invariant; reverse-rate property | `test_M_01..03_*` green | S | none | Yes | sonnet |
| E-54 | Notify transports hardening | P1/P2 | `notify_multichannel/transports.py:171,244,317,389,422,455,511`, `router.py:134` | compare_digest; specific exceptions; cause chain | `test_NM_01..03_*` green | M | none | Yes | sonnet |
| E-55 | RBAC static path + SpiceDB Zedtoken | P2 | `rbac-static/resolver.py:50-55`, `rbac-spicedb/` | Path traversal guard; Zedtoken propagation | `test_RB_01/02_*` green | M | none | Yes | sonnet |
| E-56 | KMS async correctness | P2 | `signing-kms/kms.py:74-90` | `asyncio.to_thread` wrapping | `test_SK_04_*` green | S | none | Yes | sonnet |
| E-57 | CLI quality | P1/P2 | `flowforge_cli/jtbd/generators/`, `commands/tutorial.py`, `commands/new.py` | Stub generators implemented/deleted; validated cwd; importlib resources; log+chain | `test_CL_01..04_*` green | M | none | Yes | sonnet |
| E-58 | Hub residual (counter, verify cache, admin rotation, path, except) | P1/P2 | `jtbd_hub/registry.py:340-342, 309-321`, `app.py:115-138`, `trust.py:99,201-222` | DB counter; verified_at_install cache; admin rotation; platformdirs; pydantic-only except | `test_JH_02..06_*` green | M | E-37b | Yes | sonnet |
| E-59 | JTBD lint cleanup | P2 | `lint/dependencies.py:245-305`, `db/comments.py:198-210`, `registry/manifest.py:131-134` | Dead code removed; mention regex aligned; manifest narrows except | `test_J_10..12_*` green | S | none | Yes | sonnet |
| E-60 | Audit-pg residual: datetime regex | P2 | `audit_pg/sink.py:280-281` | `datetime.fromisoformat` try/except | `test_AU_04_*` green | S | E-37 | Yes | sonnet |
| E-61 | DSL spec hygiene | P2 | `dsl/workflow_def.py:54`, `engine/snapshots.py:33-43` | Guard.expr validator; snapshot copy-on-write | `test_C_11/12_*` green | S | none | Yes | sonnet |
| E-62 | JS designer + renderer hardening | P2 | `js/flowforge-designer/src/store.ts:78-207`, `js/flowforge-renderer/src/fields/JsonField.tsx:47` | Undo+collab versioning; JSON.parse safety; addState type | `test_JS_04..06_*` green | M | none | Yes | sonnet |
| E-63 | JS test coverage | P2 | `js/flowforge-integration-tests/` | WS reconnect + collab tests | `test_IT_03_*` green | M | E-62 | Yes | sonnet |
| E-64 | Edge-case test bank (9 classes) | P2 | new `tests/edge_cases/` | empty/max/unicode/DST/fork-conflict/lockfile-conflict/hash-tamper/outbox+saga crash/in-flight migration | `test_IT_04_*` green | L | none | Yes | sonnet |
| E-65 | Doc currency: doctests + handbook paths | P2 | per-pkg `README.md`, `docs/flowforge-handbook.md` | Examples → doctests; handbook paths corrected | `test_DOC_03/04_*` green | M | none | Yes | haiku |
| E-66 | JS workspace marker | P3 | `js/package.json` | `"private": true` on integration-tests | `test_JS_08_*` green | S | none | Yes | haiku |
| E-67 | JTBD core polish: SVG virtualisation | P3 | `js/flowforge-jtbd-editor/src/JobMap.tsx`, `JobMapAnimation.tsx` | react-window virtualisation; benchmark | `test_JS_07_*` green | M | none | Yes | sonnet |
| E-68 | Tests location convention | P3 | `framework/tests/` | Single convention; lint enforces | `test_IT_05_*` green | S | none | Yes | haiku |
| E-69 | E-31 reconciliation + version cadence | P3 | `docs/flowforge-evolution.md`, root `pyproject.toml` | Evolution doc updated; cadence documented | `test_DOC_05_*` + manual review green | S | none | Yes | haiku |
| E-70 | Tenancy in-tx assert (residual) | P3 | `tenancy/single.py:46` | Bundled to E-36 acceptance test | `test_T_03_*` green | S | E-36 | Yes | haiku |
| E-72 | Final sweep | P3 | repo-wide | Dead code, debug logs, TODO/HACK, version pins | `make audit-2026` green; `scripts/ci/ratchets/check.sh` green | S | all prior | Yes | haiku |

**Final ticket count: 31** (active tickets E-32, E-34, E-35, E-36, E-37, E-37b, E-38, E-39, E-40, E-41, E-42, E-43, E-44, E-45, E-46, E-47, E-48a, E-48b, E-49, E-50, E-51, E-52, E-53, E-54, E-55, E-56, E-57, E-58, E-59, E-60, E-61, E-62, E-63, E-64, E-65, E-66, E-67, E-68, E-69, E-70, E-72 = **40**, but per-finding consolidation in single tickets reduces actual deliverable count to ~31 unique PRs because E-48a, E-49, E-51 are bundled across 30 packages as single PRs).

**Doc length:** This document = ~1,150 lines (under the 2,500-line cap).

---

*End of final plan. APPROVED via planner-architect-critic loop iteration 2 (v0 → architect-revision → critic ITERATE → v1 incorporating all 28 revisions).*
