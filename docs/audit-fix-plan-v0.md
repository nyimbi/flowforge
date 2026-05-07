# Flowforge Audit Fix Plan — v0 (Planner Pass)

**Plan author:** Executor (RALPLAN consensus, planner pass)
**Date:** 2026-05-06
**Mode:** DELIBERATE (auto-enabled — security-sensitive: SQL injection, signing, audit chain, sandbox escape, SOX/HIPAA)
**Source audit:** `/Users/nyimbiodero/.claude/projects/-Users-nyimbiodero-src-pjs-ums/3eb9101f-d1a0-4f8d-b202-413c81a3d026/tool-results/toolu_01Gf6UwjgtoQAQYrxeHLZzcx.json`
**Scope:** All 77 audit findings — zero deferrals, including P3 cosmetic
**Iteration:** v0 (pre-architect)

---

## 1. RALPLAN-DR Summary

### 1.1 Five guiding principles

| # | Principle | Why it matters here |
|---|---|---|
| P-1 | **Security defects ship first, behaviour changes ship later.** | 6 P0 findings include hard-coded HMAC secret, two SQL-injection sinks, audit-chain race, replay-determinism break, hub auth-bypass — these are ship-blockers. |
| P-2 | **Smallest viable diff per fix; verify behaviour preserved.** | 77 findings against 45 Python + 7 JS packages must not become a refactor festival. Every PR must be small and reviewable. |
| P-3 | **Each fix carries a regression test that fails on the unfixed code and passes on the fix.** | We need an audit trail proving each ticket was actually closed. Generic tests are not acceptable. |
| P-4 | **Architectural invariants in arch §17 are testable contracts, not aspirations.** | Replay determinism, two-phase fire, idempotency, saga, elevation isolation — each invariant gets an explicit conformance test. |
| P-5 | **Domain content is content, not code.** | The 30 domain-library scaffolds (D-01) are a documentation/content workstream, not framework engineering — staffed and tracked separately so they don't block GA on engineering. |

### 1.2 Top three decision drivers

| Driver | Description | Implication |
|---|---|---|
| D-1 | **Production blockers must close before any 1.0 tag.** | All 6 P0s in week 1; gate semver bump on green hotfix sprint. |
| D-2 | **Concurrency + audit-chain integrity are coupled.** | C-04 (engine race), AU-01 (chain race), FA-04 (hub singleton), T-02 (elevation flag), JH-02 (counter), OB-02 (claim race) — all share a "shared mutable state under concurrency" root cause. Group into one Concurrency-GA sprint. |
| D-3 | **Domain content (D-01) is the largest single cost (~30 × L).** | Either invest L per domain (real cost) OR rebrand to "starter scaffolds" (cheap, honest). Plan covers BOTH paths via E-39a (rebrand+stub-quality) AND E-39b (real content per domain) — leadership picks which to fund. |

### 1.3 Two viable options with pros/cons

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A — Fix-all-77-strict** | Every finding closed including P3 cosmetics, with test coverage and zero deferrals. Single big-bang release blocked until all done. | Highest quality bar; clearest semver story; single integration window. | ~14–16 wall-clock weeks; dev capacity blocked from new features; D-01 dominates timeline; risk of stale parallel branches diverging. |
| **B — Phased-by-severity (chosen)** | P0 hotfix → P1 GA-blocker → P1 content (parallel track) → P2 hardening → P3 polish. Each phase shippable; semver gates per phase. | Smaller blast radius per release; P0 safety lands fast; team can resume features after P1 GA; content sprint runs parallel to engineering; clearer rollback boundary. | More release ceremony; P3 work risks slipping if not budgeted; harder to assert "all 77 fixed" at any single point until last phase. |

**Choice:** **Option B (phased)** — chosen because P-1 (security first) demands fast P0 turn-around; D-3 lets content track decouple from engineering; P-2 (small diffs) is harder under big-bang.

---

## 2. Pre-mortem — Three Failure Scenarios

| # | Scenario | Trigger / Root cause | Detection | Mitigation |
|---|---|---|---|---|
| **F-1** | **Concurrent fix conflicts on engine/fire.py** | C-01 (outbox swallow), C-02 (uuid7), C-03 (guard error mask), C-04 (race), C-05 (json fallback), C-08 (dotted prefix) all touch `engine/fire.py`. Five PRs in flight on one ~290-line file → merge conflicts, contradictory tests, partial reverts. | CI sees test churn rate spike; PR diffs overlap; mergebase drifts. | Sequence the five tickets behind a single Engine-Hotfix EPIC owner; commit single PRs in fixed order C-04 → C-01 → C-03 → C-02 → C-08 → C-05. Lock the file via CODEOWNERS for the duration. Each PR rebased on previous; no parallel branches. |
| **F-2** | **Security fix ships incomplete (signing or auth bypass)** | SK-01 (default secret) gets fixed by removing default; some host depends on the default and now fails to start in prod. Or JH-01 fix tightens trust gate but breaks `allow_unsigned=True` publish path that downstream depends on. | Synthetic deployment in CI fails to boot; downstream integration tests red. | Each P0-Sec ticket ships with: (a) feature flag for legacy behaviour with explicit `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` opt-in (loud log warning) for one minor-version deprecation window, (b) SECURITY-NOTE.md entry, (c) downstream integration test against UMS that exercises the hardened path before merge. |
| **F-3** | **P2 fixes regress P0 fixes (canary blindness)** | After P0 hotfix lands, we move to P2 sprint touching same hot-spot files (`engine/fire.py`, `auth.py`, `worker.py`). A P2 cleanup deletes a defensive check added during P0; race re-emerges. | Audit-chain verification suite (added in E-33) shows a missing chain hash; or fuzz test from E-43 starts failing. | Lock the new P0 invariants behind explicit invariant tests committed as part of the P0 fix and tagged `@invariant_p0` — these tests are required-green on every P2 PR, not just the merging one. Add a CI gate "no removal of `@invariant_p0` tests without security-team review". |

---

## 3. Sprint Roadmap (Phased)

| Sprint | Wall clock | Goal | Tickets | Exit criteria |
|---|---|---|---|---|
| **S0 — P0 Hotfix** | Week 1 | Close all 6 P0 production-blockers | E-32, E-33, E-34, E-35, E-36, E-37, E-38 | All 6 P0 findings closed with regression tests; security review sign-off; CHANGELOG SECURITY entry per fix |
| **S1 — Engineering GA-blockers** | Weeks 2–4 | Close all 28 P1 framework findings (excluding D-01 content) | E-39 (engine), E-40 (audit), E-41 (auth/ws), E-42 (jtbd), E-43 (parity), E-44 (hypothesis), E-45 (e2e), E-46 (workspace+docs), E-47 (saga) | All 27 non-content P1 findings closed; replay-determinism conformance suite green; arch §17 invariants 8/8 enforced |
| **S2 — Domain Content** (parallel, weeks 2–10) | Weeks 2–10 | Close D-01 across 30 domains via E-48a (rebrand) OR E-48b (real content) | E-48a OR E-48b, E-49 (smoke tests), E-50 (semver pin), E-51 (init export) | Either: 30 packages renamed `*-starter` with explicit scaffold disclaimer, OR 30 domains have real JTBD content signed off by domain SME; smoke tests green |
| **S3 — Hardening** | Weeks 5–6 | Close all 31 P2 findings | E-52..E-66 (one ticket per package hot-spot) | All 31 P2 findings closed; no `except Exception: pass` in framework code paths; in-memory defaults explicitly suffixed |
| **S4 — Polish** | Week 7 (continuous) | Close all 12 P3 findings | E-67..E-72 | All 12 P3 findings closed; docs aligned to code; no dead-code paths |

**Total wall clock (engineering track):** 7 weeks
**Total wall clock (with full content track E-48b):** 10 weeks
**Total wall clock (with rebrand track E-48a):** 7 weeks

---

## 4. Acceptance Criteria — per finding

Every finding gets an entry. Acceptance criteria are testable; "test exists, fails before fix, passes after" is the universal contract.

### 4.1 P0 findings (6)

| ID | File:lines | Acceptance criteria (testable) |
|---|---|---|
| **C-01** | `python/flowforge-core/src/flowforge/engine/fire.py:283-288` | Test: outbox dispatch raises `ConnectionError` mid-fire → fire raises and rolls back the audit row; no transition is visible via `store.get(instance_id).state == post`. Verify via integration test in `flowforge-core/tests/test_engine_outbox_failure.py`. |
| **C-06** | `python/flowforge-core/src/flowforge/expr/evaluator.py:25-30` | Test: post-engine-startup `register_op("==", lambda *a: True)` raises `RegistryFrozenError`; replay determinism conformance test runs same DSL across two evaluator instances and asserts byte-identical guard outcomes. |
| **SK-01** | `python/flowforge-signing-kms/src/flowforge_signing_kms/hmac_dev.py:20, 25` | Test: import + instantiate `HmacDevSigner()` with no `FLOWFORGE_SIGNING_SECRET` env → raises `RuntimeError("explicit secret required; set FLOWFORGE_SIGNING_SECRET or pass secret=")`. Loud-log warning when explicit dev opt-in `FLOWFORGE_ALLOW_INSECURE_DEFAULT=1` is set. |
| **T-01** | `python/flowforge-tenancy/src/flowforge_tenancy/single.py:46` | Test: malicious key `"x'); DROP TABLE users;--"` passed to `_set_config` raises `ValueError` (validated against `^[a-zA-Z_][a-zA-Z_0-9.]*$`) OR is bound as parameter so PG rejects with `42P01`. SQL log shows bound param, no string interpolation. |
| **J-01** | `python/flowforge-jtbd/src/flowforge_jtbd/db/alembic_bundle/versions/r2_jtbd.py:235-290` | Test: alembic upgrade with monkey-patched table-list containing `"users; DROP TABLE x"` raises `ValueError`. Tables resolved via `sqlalchemy.sql.quoted_name` and asserted in allow-list. |
| **JH-01** | `python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/registry.py:316` | Test: publish a package with `allow_unsigned=True` → manifest stores `signed_at_publish=False`. Install path with default config raises `UnsignedPackageRejected`; install with explicit `accept_unsigned=True` succeeds and emits audit event `PACKAGE_INSTALL_UNSIGNED`. Error message no longer leaks `key_id` internal value. |

### 4.2 P1 findings (28) — abridged acceptance criteria

| ID | File:lines | Acceptance criterion (one-line) |
|---|---|---|
| C-02 | `engine/fire.py:69, 100` | All `uuid.uuid4()` replaced with `uuid7str()`; lockfile fixture asserts time-ordered prefixes |
| C-03 | `engine/fire.py:84-91` | Guard with syntax error raises `GuardEvaluationError` instead of returning False; existing tests for false-guard still green |
| C-04 | `engine/fire.py:223-251` | Concurrent `fire()` for same instance from two coroutines: only one transition committed; the other awaits or returns `ConcurrentFireRejected`; integration test with 100 concurrent fires asserts state==final, not partial |
| C-08 | `engine/fire.py:114-115` | Target starting with `context.` raises `InvalidTargetError`; existing dotted-write tests still green |
| C-09 | `engine/saga.py` | Saga ledger persisted via `flowforge-sqlalchemy` adapter; compensation worker wakes on crash + replays; integration test crashes process mid-fire and asserts compensations executed on restart |
| C-10 | `compiler/validator.py:116-132` | Lookup-permission walks AST not substring; test with expression containing string literal `"lookup_failed"` no longer triggers permission check |
| FA-01 | `flowforge_fastapi/auth.py:114-118` | Round-trip test `verify(issue(p)) == p` passes for all base64-padded variants; integration test with `=` padding stripped + restored both verify |
| FA-02 | `auth.py:147-153` | CSRF cookie default `secure=True`; ConfigError raised if `secure=False` set without explicit `dev_mode=True` |
| FA-03 | `flowforge_fastapi/ws.py:159-168` | WS auth uses dedicated WSPrincipalExtractor protocol; HTTP-scope spoof removed; existing WS auth tests green |
| FA-04 | `ws.py:78` | `WorkflowEventsHub` is request-scoped via FastAPI dependency; cross-test leak test (subscribe in test A, assert no subscribers in test B) green |
| AU-01 | `audit_pg/sink.py:159-169` | 100 concurrent records for one tenant: `verify_chain()` reports zero forks; `(tenant_id, ordinal)` unique constraint exists in migration |
| AU-02 | `sink.py:172-199` | `verify_chain()` streams in 10K-row chunks; memory peak <256MB at 10M rows (measured via tracemalloc) |
| OB-01 | `outbox_pg/worker.py` (table-name f-strings) | Constructor asserts `re.match(r"^[a-zA-Z_][a-zA-Z_0-9.]*$", table)`; passing `"x; DROP"` raises `ValueError` |
| OB-02 | `worker.py:309-365` | SQLite path documented "test-only"; runtime check raises if `pool_size > 1` on SQLite |
| DS-01 | `flowforge_documents_s3/port.py:135-138` | `doc_id` validated `^[a-zA-Z0-9._-]+$`; `"../../etc"` rejected at port boundary |
| DS-02 | `port.py:128-131` | Class renamed `S3DocumentPortInMemory`; module re-exports old name with `DeprecationWarning` for 2 minor versions |
| J-02 | `lint/conflicts.py:144-269` | Pre-bucketing reduces complexity to O(B²) where B≤12; benchmark with 10K JTBDs runs in <5s (was ~50s) |
| J-03 | `ai/recommender.py:171-196` | `BagOfWordsEmbeddingProvider` exposes `fit()` and `transform()`; `embed()` after `freeze()` raises if new doc encountered; test asserts vector basis stable across 1000 embeds |
| J-04 | `ai/recommender.py:227-247` | `InMemoryEmbeddingStore.search()` emits `PerformanceWarning` once at instantiation; docstring + README link to pgvector |
| J-05 | `ai/nl_to_jtbd.py:101-122` | Adversarial test bank (Unicode homoglyphs, paraphrases) with 50 prompts; ≥45/50 caught by structured-output validator; residual risk documented |
| J-06 | `ai/nl_to_jtbd.py:155` | Dead `("HIPAA, GDPR": ())` entry deleted; tests pass |
| J-07 | `ai/nl_to_jtbd.py:336-379` | `_extract_json` uses `json.JSONDecoder.raw_decode` instead of brace-counting; fixture with `"\\u007b"` in string parses correctly |
| J-08 | `dsl/lockfile.py:140-157` | Allow-list of canonical_body keys; introducing new top-level field requires explicit registration; old lockfiles still verify |
| JH-02 | `jtbd_hub/registry.py:340-342` | Counter persisted in DB column `package.download_count`; test-spawned 2 hub replicas + 100 installs each → DB shows 200 |
| JH-03 | `registry.py:309-321` | `package.verified_at_install` cached; bundle re-verified on schedule (default daily); install-time verify only on first install per package version |
| JS-01 | `js/flowforge-renderer/src/expr.ts:88-90` | TS evaluator returns false on unknown operator (matches Python); cross-runtime conformance fixture (200 inputs) byte-identical outputs |
| JS-02 | `expr.ts:96-99` | Strict-equality only; loose null-equality removed; cross-runtime conformance fixture green |
| JS-03 | `useFlowforgeWorkflow.ts` | Contract test mounts hook under React 19; tenant query key generation matches snapshot |
| D-02 | `jtbd-insurance/.../claim_fnol.yaml:6` | Schema-level lint forbids `external: false` for actor.role in `external_role_ids` allow-list; CI fails on regression |
| D-01 | All 30 domains × ~5 jtbds = 150 yaml | Either: (E-48a path) packages renamed `flowforge-jtbd-*-starter`, README disclaimer, lint badge "scaffold-only"; OR (E-48b path) each domain has real JTBD content (`incident_date`, `claimant_id`, etc.) signed off by domain SME, with edge_cases, documents_required, approvals, notifications, sla, data_sensitivity, compliance |
| IT-01 | (no file) | `hypothesis` dependency added; 5 properties shipped: lockfile round-trip, conflict-solver determinism, evaluator literal-passthrough, manifest signing-payload stability, money arithmetic |
| IT-02 | `tests/integration/` | Three E2E suites green: fire→audit→hash-chain-verify; fire→outbox-dispatch→handler→ack; fork→migrate→replay-determinism |
| DOC-01 | root `pyproject.toml` | Workspace lists all 45 Python pkgs; `uv build` from root produces all wheels |
| DOC-02 | `framework/README.md` | README package count matches reality (45); layout diagram updated |
| NM-01 | `notify_multichannel/transports.py:422` | All HMAC verify paths use `hmac.compare_digest`; static check via grep gate in CI |
| CL-01 | `flowforge_cli/jtbd/generators/{domain_router,audit_taxonomy,sa_model}.py` | Files implemented OR deleted; if deleted, callers updated; no file <30 LoC unless explicit `__init__.py` |
| SK-02 | `signing-kms/hmac_dev.py:73-74` | Key map `dict[str,str]`; `verify(key_id="unknown", ...)` raises `UnknownKeyId`; rotation test verifies pre-rotation sigs against pre-rotation key still valid |
| SK-03 | `signing-kms/kms.py:112, 216` | Distinct `KmsTransientError` vs `KmsSignatureInvalid`; transient errors retried with backoff; permanent invalid returns False |

### 4.3 P2 findings (31) — acceptance criteria pattern

Pattern is uniform across P2: "find replaced by specific exception type, regression test added, no behaviour change visible to callers". Detail per ID below in the ticket map (§7).

### 4.4 P3 findings (12) — acceptance criteria pattern

Pattern: "cosmetic/dead-code/version drift fixed; lint or doctest verifies". Detail in §7.

---

## 5. Expanded Test Plan — per phase

### 5.1 S0 (P0 Hotfix) — test plan

| Layer | Tests added | Tooling | Owner |
|---|---|---|---|
| Unit | One regression test per P0 finding, scoped to the file under change | `pytest -vxs` per package | Engineer fixing the finding |
| Integration | Engine concurrency test (C-04), audit-chain race test (AU-01 — included in S0 because it pairs with C-04 root cause) | `pytest tests/integration/` + `pytest-postgresql` | Concurrency lead |
| Conformance | `test_arch_invariants.py` — explicit assertions for §17 invariants 1, 2, 3 (replay determinism via C-06 frozen registry) | New file `framework/tests/conformance/` | Architecture owner |
| Security | `test_no_default_secret.py`, `test_no_sql_string_interp.py` (grep-based ratchet) | Custom CI gate | Security lead |
| Observability | Each P0 fix emits a dedicated audit event (`SECURITY_PATCH_VERIFIED`) on first invocation; OpenTelemetry span attribute `flowforge.fix.id=E-32` etc. | otel-spec | Platform |
| Smoke | Manual: deploy hotfix branch to staging UMS; verify boot + 1 fire works | Manual checklist | Release manager |

### 5.2 S1 (P1 GA-blocker) — test plan

| Layer | Tests added | Tooling | Owner |
|---|---|---|---|
| Unit | One regression per P1 finding | `pytest` | Each engineer |
| Property | `hypothesis` strategies for: lockfile round-trip, hash-chain commutativity, evaluator AST, manifest signing payload, money arithmetic (5 properties total — E-44) | `pytest --hypothesis-show-statistics` | QA lead |
| Integration | E-45 three E2E suites: fire→audit→verify, fire→outbox→handler→ack, fork→migrate→replay | `pytest tests/integration/`, `testcontainers` for PG | Integration lead |
| Cross-runtime | E-43 TS↔Python evaluator conformance — 200-input fixture both sides must agree byte-for-byte | `vitest` + `pytest` shared fixture | TS+Py pair |
| Edge cases | E-44: unicode in jtbd_id, year-boundary timezone, concurrent forks of same library, lockfile conflict on simultaneous compose, hash-chain tampering one-byte-flip, outbox+saga crash interaction, in-flight migration | `tests/edge_cases/` | QA lead |
| Observability | `flowforge_fix_id` label on prometheus counter; per-fix dashboard panel | Grafana | Platform |

### 5.3 S2 (Domain content, parallel) — test plan

| Layer | Tests added | Tooling | Owner |
|---|---|---|---|
| Unit | Per-domain `test_bundle_loads.py` smoke that asserts schema validation passes for all JTBDs | `pytest` per domain pkg | Domain SMEs |
| Schema | New schema lint: `data_capture` must contain ≥1 domain-specific field (not just `reference_id` + `notes`) | DSL linter rule | Framework lead |
| Acceptance | Each domain JTBD reviewed by named SME; sign-off recorded in `domain.yaml.signoff` field | Manual | Domain SMEs + product |

### 5.4 S3 (P2 Hardening) — test plan

| Layer | Tests added | Tooling | Owner |
|---|---|---|---|
| Unit | One regression per P2 finding | `pytest` | Each engineer |
| Static | CI grep gate: no `except Exception: pass`, no `f"...{table}..."` SQL, no in-memory defaults without `InMemory` suffix | `flake8` plugin + custom checker | Security lead |
| Integration | Soak test: 24h run with 10 fires/sec, 100 outbox dispatches/sec; assert no chain breaks, no orphan sagas | k6 + grafana | SRE |
| Regression | Run full S0+S1 suite — catch any regressions of P0/P1 invariants from §F-3 mitigation | CI matrix | Test eng |

### 5.5 S4 (P3 Polish) — test plan

| Layer | Tests added | Tooling | Owner |
|---|---|---|---|
| Lint | Add `ruff` rules for `__all__`, dead-code, version pinning | `ruff check` | Engineer |
| Doctest | Per-package `README.md` examples become doctests | `pytest --doctest-modules` | Engineer |
| Doc-drift | CI-time link-checker for `docs/` paths referencing code | `linkchecker` | DocOps |

### 5.6 Observability across all phases

| Signal | Implementation | Phase |
|---|---|---|
| Audit event `FRAMEWORK_FIX_APPLIED` with ticket id | Emitted once per process startup post-fix | S0+ |
| Prometheus `flowforge_audit_chain_breaks_total` | Counter incremented when verify_chain finds a break | S1 |
| Prometheus `flowforge_outbox_dispatch_duration_seconds` | Histogram replacing silent swallow | S0 |
| Tracing span `flowforge.engine.fire` with `instance_id`, `state.from`, `state.to`, `fix_id` attributes | OpenTelemetry | S1 |
| Log structured field `security_review_id` on every P0/P1 ticket commit | git trailer | S0+ |

---

## 6. Effort Estimates per Ticket

Effort buckets: **S** = <1d, **M** = 1–5d, **L** = >5d.

(Full ticket-by-ticket breakdown in §7 below; aggregates here.)

| Phase | S count | M count | L count | Total person-weeks (1S=0.5d, 1M=3d, 1L=8d, 5d/wk) |
|---|---|---|---|---|
| S0 (P0 hotfix) | 4 | 3 | 0 | (4×0.5 + 3×3) / 5 = 2.2 weeks |
| S1 (P1 engineering) | 13 | 12 | 1 | (13×0.5 + 12×3 + 1×8) / 5 = 10.1 weeks |
| S2 (D-01 content E-48b path) | 0 | 0 | 30 | 30×8/5 = 48 weeks (parallelisable; with 6 SMEs = 8 weeks calendar) |
| S2 (D-01 rebrand E-48a path) | 5 | 1 | 0 | (5×0.5 + 1×3) / 5 = 1.1 weeks |
| S3 (P2 hardening) | 19 | 12 | 0 | (19×0.5 + 12×3) / 5 = 9.1 weeks |
| S4 (P3 polish) | 12 | 0 | 0 | 12×0.5 / 5 = 1.2 weeks |
| **Total (engineering, with rebrand)** | 53 | 28 | 1 | **23.7 person-weeks** |
| **Total (with full content E-48b)** | 48 | 28 | 31 | **70.6 person-weeks** |

Calendar: with 4 engineers + 6 domain SMEs in parallel, ~7 weeks (rebrand) or ~10 weeks (full content).

---

## 7. Ticket Map E-32..E-72 (planner pass — superseded by §7 of final plan)

| ID | Title | Sev | File:line refs | Sprint | Effort | Parallel-safe | Agent tier | Maps to findings |
|---|---|---|---|---|---|---|---|---|
| **E-32** | Engine concurrency: per-instance asyncio.Lock + transactional fire boundary | P0/P1 | `engine/fire.py:223-251`, `engine/fire.py:283-288` | S0 | M | No (single-file lock) | opus | C-04, C-01 |
| **E-33** | Audit-chain race fix: PG advisory lock per tenant + chunked verify | P1 | `audit_pg/sink.py:159-199` | S0 (paired with E-32 for shared root cause) | M | No (single PR) | opus | AU-01, AU-02 |
| **E-34** | Crypto rotation: remove HMAC default secret + per-key_id signed key map | P0/P1 | `signing-kms/hmac_dev.py:20-74`, `kms.py:112,216` | S0 | S | Yes | opus | SK-01, SK-02, SK-03 |
| **E-35** | Frozen op registry: replace mutable `_OPS` with build-time-frozen registry | P0 | `expr/evaluator.py:25-79` | S0 | M | Yes | opus | C-06, C-07 |
| **E-36** | Tenancy SQL hardening: bind-param GUC + ContextVar elevation | P0/P2/P3 | `tenancy/single.py:18-46` | S0 | S | Yes | sonnet | T-01, T-02, T-03 |
| **E-37** | Hub trust hardening: explicit signed_at_publish + per-user admin RBAC | P0/P2 | `jtbd_hub/registry.py:309-321,316`, `app.py:115-138`, `trust.py:99-222` | S0 (P0 portion); S3 (RBAC, path) | M | Yes | opus | JH-01, JH-04, JH-05, JH-06 |
| **E-38** | Migration RLS DDL: whitelist table names + sqlalchemy quoted_name | P0 | `r2_jtbd.py:235-290` | S0 | S | Yes | sonnet | J-01 |
| **E-39** | Engine quality + correctness pass: uuid7, guard error surfacing, json safety, dotted prefix | P1/P2/P3 | `engine/fire.py:69,84-91,114-115,189-194`, `__init__.py` | S1 | M | No (touches engine/fire.py) | opus | C-02, C-03, C-05, C-08, C-13 |
| **E-40** | Saga ledger persistence + compensation worker | P1 | `engine/saga.py`, `sqlalchemy/saga_queries.py` | S1 | L | Yes (new module) | opus | C-09, SA-02 |
| **E-41** | FastAPI + WS hardening: signing parity, secure CSRF, WS-native auth, request-scoped hub, transactional fire | P1/P2 | `auth.py:114-118,147-153`, `auth.py` (CookiePrincipal expiry), `ws.py:78,159-168`, `router_runtime.py:181-191` | S1 | M | Yes (per-file) | opus | FA-01, FA-02, FA-03, FA-04, FA-05, FA-06 |
| **E-42** | Outbox hardening: table-name validation, SQLite single-worker, reconnect, utf8 truncation | P1/P2 | `outbox_pg/worker.py:235,289-296,309-365,432,440` | S1 | M | Yes | sonnet | OB-01, OB-02, OB-03, OB-04 |
| **E-43** | TS↔Python expr conformance suite: align unknown-operator + equality semantics | P1 | `js/flowforge-renderer/src/expr.ts:88-99`, `flowforge-core/src/flowforge/expr/evaluator.py` | S1 | M | Yes | sonnet | JS-01, JS-02 |
| **E-44** | Hypothesis property tests: lockfile, hash-chain, evaluator, manifest, money | P1 | new `tests/property/` | S1 | M | Yes | sonnet | IT-01 |
| **E-45** | E2E suite: fire→audit→verify; fire→outbox→ack; fork→migrate→replay | P1 | new `tests/integration/e2e/` | S1 | L | Yes | sonnet | IT-02 |
| **E-46** | Workspace + docs alignment: register all 45 pkgs; README package count; doc paths | P1/P2/P3 | root `pyproject.toml`, `framework/README.md`, `docs/flowforge-evolution.md`, per-pkg READMEs | S1 | S | Yes | haiku | DOC-01, DOC-02, DOC-04, DOC-05, D-05 |
| **E-47** | JTBD intelligence quality: lint perf, recommender fit/transform, NL guard, dead code | P1 | `lint/conflicts.py:144-269`, `ai/recommender.py:171-247`, `ai/nl_to_jtbd.py:101-379`, `dsl/lockfile.py:140-157`, `dsl/spec.py:95-113` | S1 | M | Yes | opus | J-02, J-03, J-04, J-05, J-06, J-07, J-08, J-09 |
| **E-48a** | Domain-library rebrand to "starter scaffolds" | P1 | all 30 `flowforge-jtbd-*` packages, READMEs, `pyproject.toml` `name` field | S2 | S × 30 | Yes | haiku | D-01 (rebrand path) |
| **E-48b** | Domain-library real content authoring (alternative to E-48a) | P1 | all 30 × 5 yaml files | S2 | L × 30 | Yes (per domain) | sonnet (review by SME) | D-01 (real-content path) |
| **E-49** | Per-domain smoke tests: bundle load + schema validation | P2 | per-package `tests/test_smoke.py` | S2 | M | Yes | sonnet | D-04 |
| **E-50** | Domain pkg semver pin to 0.0.1 | P3 | all 30 `pyproject.toml` | S2 | S | Yes | haiku | D-05 |
| **E-51** | Domain pkg `__init__.py` standard: load_bundle helper + `__all__` | P2 | all 30 `__init__.py` | S2 | S × 30 | Yes | haiku | D-03 |
| **E-52** | Documents-S3 path validation + content-type enforcement on presigned PUT | P1/P2 | `documents_s3/port.py:128-138,315-338,37-44` | S3 | M | Yes | sonnet | DS-01, DS-02, DS-03, DS-04 |
| **E-53** | Money rounding + reverse-rate consistency | P2 | `money/static.py:111-203` | S3 | S | Yes | sonnet | M-01, M-02, M-03 |
| **E-54** | Notify transports: specific exception types + cause chaining | P2 | `notify_multichannel/transports.py:171,244,317,389,455,511`, `router.py:134` | S3 | M | Yes | sonnet | NM-02, NM-03 |
| **E-55** | RBAC static path traversal + SpiceDB Zedtoken docs | P2 | `rbac-static/resolver.py:50-55`, `rbac-spicedb/` | S3 | M | Yes | sonnet | RB-01, RB-02 |
| **E-56** | KMS async correctness | P2 | `signing-kms/kms.py:74-90` | S3 | S | Yes | sonnet | SK-04 |
| **E-57** | CLI quality: stub generators, validated cwd, importlib resources, log+chain | P1/P2 | `flowforge_cli/jtbd/generators/`, `commands/tutorial.py:257-299`, `commands/new.py:102-107` | S3 | M | Yes | sonnet | CL-01, CL-02, CL-03, CL-04 |
| **E-58** | JTBD hub counter + rate-verify + trust path portability | P1/P2 | `jtbd_hub/registry.py:340-342`, `trust.py:99,201-222` | S3 | M | Yes | sonnet | JH-02, JH-03 (residual), JH-05, JH-06 |
| **E-59** | JTBD lint cleanup: dead code, mention regex, manifest exception narrowing | P2 | `lint/dependencies.py:245-305`, `db/comments.py:198-210`, `registry/manifest.py:131-134` | S3 | S | Yes | sonnet | J-10, J-11, J-12 |
| **E-60** | Audit-pg correctness: canonical golden bytes test, datetime regex tightening | P2 | `audit_pg/hash_chain.py:103-113`, `sink.py:280-281` | S3 | S | Yes | sonnet | AU-03, AU-04 |
| **E-61** | DSL spec hygiene: Guard.expr validator, snapshot copy-on-write | P2 | `dsl/workflow_def.py:54`, `engine/snapshots.py:33-43` | S3 | S | Yes | sonnet | C-11, C-12 |
| **E-62** | JS designer + renderer hardening: undo+collab versioning, JSON.parse safety, addState type fix | P2 | `js/flowforge-designer/src/store.ts:78-207`, `js/flowforge-renderer/src/fields/JsonField.tsx:47` | S3 | M | Yes | sonnet | JS-04, JS-05, JS-06 |
| **E-63** | JS test coverage: WS reconnect + collab edge cases | P2 | `js/flowforge-integration-tests/` | S3 | M | Yes | sonnet | IT-03 |
| **E-64** | Edge-case test bank: empty, max, unicode, DST, fork-conflict, lockfile-conflict, hash-tamper, outbox+saga crash, in-flight migration | P2 | new `tests/edge_cases/` | S3 | L | Yes | sonnet | IT-04 |
| **E-65** | Doc currency: per-pkg READMEs become doctests; handbook paths corrected | P2 | per-pkg `README.md`, `docs/flowforge-handbook.md` | S3 | M | Yes | haiku | DOC-03, DOC-04 |
| **E-66** | JS designer: undo entry version stamp + integration tests workspace marker | P2/P3 | `js/flowforge-designer/`, `js/package.json` workspace | S3 | S | Yes | sonnet | JS-04 (residual), JS-08 |
| **E-67** | JTBD core polish: __all__ public api, JS large SVG perf | P3 | `flowforge/__init__.py`, `js/flowforge-jtbd-editor/src/JobMap.tsx`, `JobMapAnimation.tsx` | S4 | M | Yes | sonnet | C-13 (residual), JS-07 |
| **E-68** | Tests location convention: pick tests/ vs tests/integration/ | P3 | `framework/tests/` | S4 | S | Yes | haiku | IT-05 |
| **E-69** | E-31 reconciliation: align evolution.md to actual ticket count | P3 | `docs/flowforge-evolution.md` | S4 | S | Yes | haiku | E-31 mismatch |
| **E-70** | Tenancy `in_transaction` assertion residual | P3 | `tenancy/single.py:46` | S4 | S | Yes | haiku | T-03 (residual) |
| **E-71** | Hub admin token deprecation completion | P3 | `jtbd_hub/app.py:115-138` | S4 | S | Yes | haiku | JH-04 (residual) |
| **E-72** | Final sweep: dead code, debug logs, TODO/HACK, version pins consistent | P3 | repo-wide | S4 | S | Yes | haiku | residual P3 polish |

**Total: 41 tickets (E-32 .. E-72).**

---

## 8. Dependency DAG

ASCII representation; arrows are "must complete before".

```
                     [E-46 workspace+docs] (S1, can start anytime)
                          ^
                          |
[E-32 engine concurrency] ----> [E-39 engine quality] ----> [E-67 polish]
       \                              ^                          ^
        \                             |                          |
         +--> [E-40 saga ledger] ----+                           |
              ^                                                  |
              |                                                  |
[E-33 audit-chain race] --> [E-60 audit-pg correctness] -------> |
                                                                 |
[E-34 crypto rotation] --> [E-56 kms async] -------------------> |
                                                                 |
[E-35 frozen op registry] --> [E-43 ts↔py conformance] --------> |
                                                                 |
[E-36 tenancy] --> [E-70 in_tx assert] ------------------------> |
                                                                 |
[E-37 hub trust]  --> [E-58 hub counter+verify] --> [E-71 admin] >|
                                                                 |
[E-38 migration RLS] (independent) ---------------------------> [final sweep E-72]
                                                                 ^
[E-41 fastapi/ws] (parallel to E-32; independent files) -------->|
                                                                 |
[E-42 outbox hardening] (parallel) ----------------------------->|
                                                                 |
[E-44 hypothesis] (parallel; needs S0 done for invariants) ---->|
                                                                 |
[E-45 e2e] (needs E-32, E-33, E-40 done) ----------------------->|
                                                                 |
[E-47 jtbd intelligence] (parallel; independent) -------------->|
                                                                 |
[E-48a OR E-48b domain content] (parallel from week 2) -------->|
        --> [E-49 smoke tests] --> [E-50 semver] --> [E-51 init] |
                                                                 |
[S3 P2 sprint: E-52..E-66] (after S1 green) ------------------->|
                                                                 |
[S4 P3: E-67..E-72] (after S3 green) -------------------------->[release 1.0]
```

**Critical path:** E-32 → E-40 → E-45 → S3 → S4. Estimated 10 weeks calendar with full content track, 7 weeks with rebrand.

**Parallel lanes (no shared file):**
- Lane A (engine): E-32 → E-39 → E-67
- Lane B (audit): E-33 → E-60
- Lane C (crypto): E-34 → E-56
- Lane D (registry): E-35 → E-43
- Lane E (tenancy+migration): E-36, E-38, E-70
- Lane F (hub): E-37 → E-58 → E-71
- Lane G (http/ws): E-41
- Lane H (outbox): E-42
- Lane I (saga): E-40
- Lane J (jtbd intel): E-47
- Lane K (testing): E-44, E-45
- Lane L (content): E-48a/b → E-49 → E-50 → E-51
- Lane M (docs): E-46

---

## 9. Risk register (top 5 from pre-mortem)

| # | Risk | Likelihood | Impact | Mitigation owner |
|---|---|---|---|---|
| R-1 | engine/fire.py merge conflicts (F-1) | High (5 PRs same file) | Medium (re-work) | Engine EPIC owner |
| R-2 | Security fix breaks downstream (F-2) | Medium | High (rollback) | Security lead + UMS integration tester |
| R-3 | P2 cleanup regresses P0 invariants (F-3) | Medium | High (silent re-introduction) | CI ratchet (`@invariant_p0` tag) |
| R-4 | D-01 content sprint slips, E-48b path doubles calendar | High (30 SMEs) | Medium (delay GA messaging) | Pre-commit to E-48a (rebrand) as fallback by week 4 |
| R-5 | Hypothesis tests find latent bugs that block S1 close | Medium | Medium (scope creep) | Triage to S3 unless P0 severity |

---

## 10. Open questions for architect

1. Is the "P0 hotfix in week 1" timeline realistic given that two of the P0s (E-32 engine concurrency, E-35 frozen registry) are M-effort each and on critical path? (We classify as M but architect should sanity-check.)
2. Should E-37 (hub trust) split into "P0 trust gate fix" (S0) + "P2 hub admin RBAC" (S3), as proposed, OR ship together to minimise hub-pkg PR count?
3. Is the rebrand E-48a path (1.1 weeks) acceptable from a product-promise perspective, given the framework was sold as "30 working domain libraries"? If not, E-48b path locks the team for 8+ calendar weeks on content.
4. C-09 (saga ledger persistence) is L-effort and on critical path. Is it actually a P1, or could it ship as P2 if compensation is "best-effort" in the interim?
5. Should the fix-id observability be a hard blocking requirement (every fix must emit `FRAMEWORK_FIX_APPLIED`) or only on P0/P1?

---

*End of v0 plan. Awaiting architect review.*
