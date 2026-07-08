# flowforge Core Python Security and Performance Audit

Date: 2026-07-08

Scope:

- `python/flowforge-core/src/`
- `python/flowforge-fastapi/src/`
- `python/flowforge-jtbd/src/`
- Related signing evidence from `python/flowforge-signing-kms/src/` where the required HMAC scan pointed there.

This is a source audit, not a full exploit or load-test run. `sources.md` contains the requested command evidence and the main file/line references.

## Executive Summary

No CRITICAL findings were identified.

The highest-risk issues are:

- HIGH: FastAPI dashboard HTML is rendered with raw f-strings and unescaped database/query values, creating stored and reflected XSS risk.
- HIGH: Unknown expression operators are treated as literal dictionaries; in guard evaluation those dictionaries are truthy, so an operator typo can accidentally pass a guard.
- MEDIUM: JTBD pgvector DDL/DML interpolates schema/table/index identifiers while validating them only with `assert`, which is unsafe under `python -O` and unsafe for configurable identifiers.
- MEDIUM: Dashboard database errors are swallowed and converted into empty/default results, including health responses that can still return `"status": "ok"`.

Positive controls observed:

- No actual `eval(`, `exec(`, `__import__`, `subprocess`, or `os.system` call sites were found in the audited core/FastAPI/JTBD roots.
- Session-cookie HMAC verification, CSRF token comparison, and dev HMAC signing use `hmac.compare_digest`.
- The core expression operator registry is frozen after module initialization and arity is checked for known operators.
- The core `fire()` path has explicit rollback handling for audit/outbox dispatch failures.

## Security Findings

### HIGH - S-01: Dashboard HTML rendering is not escaped

Evidence:

- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:51-85` builds the whole page with f-strings.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:99-106` injects table headers and cells directly into HTML.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:268-272` reflects `def_key` and `state` query parameters into input `value` attributes.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:305` embeds JSON/context text directly in a `<pre>`.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:321-331` renders instance fields directly into HTML.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:404-406` reflects `subject` into an input `value` attribute.
- A focused grep for `html.escape`, `markupsafe`, or `escape(` in FastAPI dashboard code returned no matches.

Risk:

Dashboard values come from workflow instances, audit events, task notes, actor IDs, and request query strings. If an attacker can influence any of those values, the operations dashboard can execute attacker-controlled JavaScript in a privileged operator's browser. The issue includes stored XSS through database rows and reflected XSS through dashboard filters.

Recommended fix:

- Replace f-string HTML construction with an autoescaping template engine, or escape every text and attribute context with `html.escape(..., quote=True)`.
- Keep intentional HTML fragments as typed/sanitized fragments only; do not pass arbitrary row cells through `_table`.
- Add regression tests that insert `<script>`, `" onfocus=...`, and `&<>"'` payloads in `def_key`, `state`, `context`, task `note`, audit `kind`, and query parameters.

### HIGH - S-02: Unknown expression operators can become truthy guards

Evidence:

- `python/flowforge-core/src/flowforge/expr/evaluator.py:201-207` treats only known operator keys and `var` as operator calls.
- `python/flowforge-core/src/flowforge/expr/evaluator.py:236-239` returns non-operator dictionaries as literals.
- `python/flowforge-core/src/flowforge/expr/evaluator.py:270-272` documents that unknown op keys are not flagged.
- `python/flowforge-core/src/flowforge/engine/fire.py:204-210` runs `bool(result)` for guard results.
- `python/flowforge-core/tests/unit/test_expr_evaluator.py:293-298` verifies unknown operators are not flagged by `check_arity`.
- `python/flowforge-core/tests/unit/test_expr_evaluator.py:107` verifies an unknown single-key expression evaluates back to a dictionary.

Risk:

A guard such as `{"greater_than": [{"var": "context.amount"}, 1000]}` where `greater_than` is not registered evaluates to a non-empty dict. `bool(non_empty_dict)` is `True`, so the guard passes. This can bypass business, approval, or permission gates when a DSL author mistypes an operator or when imported DSL contains an unsupported operator.

Recommended fix:

- In guard and effect expression validation, reject unknown single-key operator-shaped dictionaries unless they are explicitly marked as object literals.
- Add a stricter evaluation mode for guards/effects, for example `evaluate(..., strict_ops=True)`, and use it from `fire()` and the compiler validator.
- Add regression tests proving unknown guard operators fail validation and cannot pass a transition.

### MEDIUM - S-03: pgvector SQL identifiers are interpolated and only assert-validated

Evidence:

- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:100-104` validates `TableSpec` fields with `assert`.
- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:106-156` interpolates `schema`, `table`, and `index_name` into DDL.
- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:180-188` accepts `schema` and `table` via `from_extras`.
- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:219-227` interpolates the qualified table into DML.
- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:213-248` validates `jtbd_id`, vector dimension, and `top_k` with `assert`.

Risk:

If schema/table/index names ever come from tenant, environment, request, or plugin configuration, a malicious identifier can alter DDL/DML. Even when values are trusted, `assert` checks disappear under optimized Python, turning validation failures into malformed or dangerous SQL execution.

Recommended fix:

- Replace `assert` with explicit `ValueError`/`TypeError`.
- Validate identifiers with a conservative regex such as `^[A-Za-z_][A-Za-z0-9_]*$`.
- Prefer SQLAlchemy identifier quoting/`quoted_name`/dialect `IdentifierPreparer` for schema, table, and index names.
- Add tests for invalid identifiers and run them with `PYTHONOPTIMIZE=1`.

### LOW - S-04: Legacy session cookies without `exp` remain accepted

Evidence:

- `python/flowforge-fastapi/src/flowforge_fastapi/auth.py:247-252` verifies session-cookie HMAC with `hmac.compare_digest`.
- `python/flowforge-fastapi/src/flowforge_fastapi/auth.py:261-263` explicitly keeps cookies with no `exp` valid for backward compatibility.
- `python/flowforge-fastapi/src/flowforge_fastapi/auth.py:264-271` rejects only when `exp` exists and is expired.

Risk:

This is not a timing issue; compare-digest usage is correct. The residual issue is session lifetime. If any pre-expiration cookies are still accepted in production, they can remain valid indefinitely unless the signing secret is rotated.

Recommended fix:

- Add a migration cutoff and reject no-`exp` cookies after that date.
- Optionally require `iat` plus a maximum legacy age during the migration window.
- Document the operational secret-rotation step needed to invalidate old cookies.

### LOW - S-05: JTBD prompt-injection guard is heuristic

Evidence:

- `python/flowforge-jtbd/src/flowforge_jtbd/ai/nl_to_jtbd.py:187-224` strips a small token list and rejects a small regex list.

Risk:

This is useful baseline validation, but direct regex markers do not cover indirect prompt injection, multilingual instruction override, encoded text, or hostile content inside bundle context. The downstream model output is validated, which reduces impact, but the guard should not be treated as complete security coverage.

Recommended fix:

- Treat this as defense-in-depth, not the primary control.
- Keep strict structured output validation, schema allow-lists, and provenance/audit logging.
- Add tests for encoded, multiline, and indirect injection samples.

## Performance Findings

### MEDIUM - P-01: Dashboard request handlers make multiple serial database round trips

Evidence:

- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:163-175` health runs three scalar queries serially.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:181-201` overview runs four scalar queries plus a recent-events query serially.

Impact:

Every dashboard load pays cumulative DB latency and connection/session overhead. Health checks can also become more expensive than necessary under monitoring frequency.

Recommended fix:

- Combine counts into one aggregate query where practical.
- Add a short TTL cache for dashboard summary counts.
- Keep recent events separately paginated and indexed by `created_at`.

### MEDIUM - P-02: `fire()` holds the per-instance gate while awaiting ports

Evidence:

- `python/flowforge-core/src/flowforge/engine/fire.py:803-814` records audits and dispatches outbox envelopes sequentially before releasing the `fire()` gate.
- `python/flowforge-core/src/flowforge/engine/fire.py:836-850` awaits task creation after mutation.
- `python/flowforge-core/src/flowforge/engine/fire.py:797-801` documents that durable hosts should use transactional adapters with `dispatch_ports=False`.

Impact:

Slow audit, outbox, or task adapters block subsequent events for the same instance. The serialization is correct for consistency, but direct-dispatch mode is not suitable for high-throughput production paths.

Recommended fix:

- Make transactional outbox mode the production default in host wiring.
- Add batch port APIs such as `record_many` and `dispatch_many`, or gather independent non-transactional sends with bounded concurrency where ordering is not required.
- Emit metrics for time spent in guard evaluation, effect planning, audit dispatch, outbox dispatch, and task creation separately.

### MEDIUM - P-03: Transition matching is O(number of transitions) per fire

Evidence:

- `python/flowforge-core/src/flowforge/engine/fire.py:180-184` scans all transitions for primary-state fires.
- `python/flowforge-core/src/flowforge/engine/fire.py:187-191` scans all transitions for token fires.

Impact:

For large generated workflows, every event repeatedly scans the whole transition list. This is cheap for small workflows but avoidable in core hot paths.

Recommended fix:

- Build a compiled transition index keyed by `(from_state, event)` at workflow validation/registration time.
- Cache state definitions by name so fork/join lookups do not scan `wd.states`.

### LOW - P-04: pgvector HNSW recall checks run serially

Evidence:

- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:410-419` loops over golden queries and awaits each `search` one at a time.

Impact:

Index switch validation can be slow for large golden sets.

Recommended fix:

- Use bounded async concurrency for golden queries.
- Record per-query recall and latency so failed swaps identify the weak cases.

### LOW - P-05: WebSocket hub fan-out is linear and drops on full queues

Evidence:

- `python/flowforge-fastapi/src/flowforge_fastapi/ws.py:78-93` copies subscribers, then loops through each queue with `put_nowait`.

Impact:

This is acceptable for an in-process test/demo hub, but large subscriber counts or slow clients lead to drops and per-publish O(N) work on the request path.

Recommended fix:

- Keep this hub for local/test use.
- For production multi-host or high-subscriber use, publish through a broker-backed adapter and keep request handlers off direct fan-out.

## Missing Error Handling and Correctness Findings

### MEDIUM - C-01: Dashboard database errors are hidden as empty/default results

Evidence:

- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:135-145` catches any query exception, logs it, and returns `[]`.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:147-157` catches any scalar exception, logs it, and returns `default`.
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:163-175` returns `"status": "ok"` even though its inputs can be defaulted after database errors.

Impact:

Operators can see apparently healthy dashboards with zero counts during a database outage or schema mismatch. This hides incidents and can break monitoring.

Recommended fix:

- For `/health`, return `503` when required queries fail.
- For HTML pages, show an explicit error banner instead of silently empty tables.
- Emit a metric for dashboard query failures.

### MEDIUM - C-02: Manual-review task creation failure does not fail the transition

Evidence:

- `python/flowforge-core/src/flowforge/engine/fire.py:836-850` catches `TaskTrackerPort.create_task()` exceptions and only logs a warning.

Impact:

An instance can enter a `manual_review` state without creating the task that operators need to act on it.

Recommended fix:

- Decide whether manual-review task creation is required or best-effort.
- If required, roll back the transition or emit a durable compensating alert.
- If best-effort, emit a metric and expose a reconciliation job that finds manual-review states without tasks.

### LOW - C-03: LLM provider capabilities are protocol-only stubs

Evidence:

- `python/flowforge-jtbd/src/flowforge_jtbd/ports/llm.py:39-41` documents that adapters may raise `NotImplementedError`.
- `python/flowforge-jtbd/src/flowforge_jtbd/ports/llm.py:44-76` declares protocol methods with ellipsis bodies.

Impact:

This is not a production stub by itself; it is a protocol. The inventory is still worth tracking because callers must feature-test capabilities before invocation as the docstring says.

Recommended fix:

- Keep explicit feature detection in all LLM callers.
- Add tests for adapters that lack `embed` or `stream_chat`.

## Stub/TODO Inventory

Requested scans found:

- `TODO/FIXME/HACK/XXX/STUB/NotImplemented/raise NotImplementedError` in audited roots: one hit, `python/flowforge-jtbd/src/flowforge_jtbd/ports/llm.py:39`, documenting `NotImplementedError` for unsupported LLM capabilities.
- `pass` or ellipsis in `python/flowforge-core/src/`: no hits.
- Full audited-root `pass`/ellipsis scan: no hits in source roots because protocol ellipses are not followed by the exact spacing pattern used by the command.

Interpretation:

- No obvious unfinished core/FastAPI production code paths were found by these scans.
- The LLM provider item is a protocol contract, not an implementation stub.

## Recommended Fixes in Priority Order

1. Fix dashboard XSS: introduce autoescaping or centralized escaping, then add regression tests for reflected and stored payloads.
2. Make expression validation strict for guard/effect operator dictionaries so unknown operators cannot evaluate as truthy literals.
3. Fix pgvector identifier handling and replace production `assert` validation with explicit exceptions.
4. Change dashboard DB error handling so health returns failure on DB/schema errors and HTML pages show explicit error states.
5. Decide and enforce the manual-review task failure contract.
6. Move production host wiring to transactional outbox mode by default and add timing metrics around `fire()` port dispatch.
7. Add compiled transition/state indexes for large workflows.
8. Add a session-cookie no-`exp` cutoff and rotate secrets after the migration window.
9. Treat JTBD prompt-injection filtering as defense-in-depth and expand tests around indirect/encoded attacks.
