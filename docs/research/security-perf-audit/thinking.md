# Audit Notes and Rationale

This file captures the audit reasoning at an engineering-summary level. It does not include private chain-of-thought; it records the evidence path, ranking rationale, and assumptions used to produce `README.md`.

## Method

1. Ran the exact grep commands requested in the mission.
2. Used the codebase memory index to locate `flowforge.engine.fire.fire`.
3. Read the `fire()` implementation, `_fire_locked()`, expression evaluator, expression operators, FastAPI auth/dashboard/runtime/WS code, JTBD pgvector store, JTBD LLM provider protocol, and relevant tests.
4. Added focused scans for actual dynamic execution calls, escaping, assertion-based validation, broad exception swallowing, HMAC compare-digest usage, SQL construction, and blocking sleep calls.
5. Ranked findings by exploitability, privilege impact, production likelihood, and blast radius.

## Ranking Rationale

### Dashboard XSS

Ranked HIGH because:

- The dashboard is an operator-facing surface.
- It renders database-backed workflow/audit/task values.
- Query parameters are reflected into HTML attribute values.
- No escaping helper was found in the dashboard code.

This can become either stored XSS or reflected XSS. The fix is straightforward and should be prioritized.

### Unknown expression operators

Ranked HIGH because:

- Guards drive workflow authorization and business-state transitions.
- Unknown operator-shaped dictionaries are intentionally treated as literals.
- Non-empty dictionaries are truthy in Python.
- Existing tests lock in that unknown operators are not flagged.

This may be an intended cross-runtime compatibility behavior for general expressions, but it is unsafe for guard/effect validation. The recommended repair is to keep object literals explicit while making guard/effect operator positions strict.

### pgvector identifier interpolation

Ranked MEDIUM because:

- It depends on whether schema/table/index names are trusted host configuration or influenced by tenants/plugins.
- It executes SQL text directly once configured.
- `assert` validation disappears with optimized Python.

The fix should be done before tenant-specific schema names or plugin-provided storage configuration become part of the production surface.

### Dashboard error masking

Ranked MEDIUM because:

- It can hide database outages and schema drift.
- The health endpoint can still return `"status": "ok"` after failures.
- This is less directly exploitable than XSS, but it undermines operations and incident response.

### Manual-review task failure

Ranked MEDIUM because:

- A workflow may enter a state that depends on human action.
- If task creation fails, only a warning is logged.
- The appropriate fix depends on product semantics, so the report recommends deciding whether the task is required or best-effort.

## Non-Findings

- Dynamic Python execution: the broad grep had many substring hits, but the focused scan found no actual `eval(`, `exec(`, `__import__`, `subprocess`, or `os.system` call sites in the audited source roots.
- Timing attacks in scanned HMAC paths: FastAPI session cookies, CSRF, and dev signing use `hmac.compare_digest`.
- Blocking sleeps in audited source roots: the source-root sleep scan found no `asyncio.sleep` or `time.sleep` hot-path calls; the broader `python/` scan found test sleeps and outbox worker polling outside the audited core package set.
- Direct SQL in `flowforge-core`: the requested core SQL grep found only saga documentation references.

## Assumptions and Limits

- This was a source audit, not a deployed environment assessment.
- I did not run a browser exploit PoC for dashboard XSS because the mission requested documentation output, not remediation or exploit tests.
- I did not run load tests; performance findings are static hot-path observations.
- I did not modify production code.
- Existing untracked work outside `docs/research/security-perf-audit/` was left untouched.
