# Audit Sources

## Requested Commands

### 1. Dynamic execution broad grep

Command:

```bash
grep -r 'eval\|exec\|__import__\|subprocess\|os\.system' python/flowforge-core/src/ --include='*.py' -l 2>&1
```

Output:

```text
python/flowforge-core/src/flowforge/expr/__init__.py
python/flowforge-core/src/flowforge/expr/ops/__init__.py
python/flowforge-core/src/flowforge/expr/evaluator.py
python/flowforge-core/src/flowforge/replay/simulator.py
python/flowforge-core/src/flowforge/replay/fault.py
python/flowforge-core/src/flowforge/dmn/models.py
python/flowforge-core/src/flowforge/dmn/__init__.py
python/flowforge-core/src/flowforge/dmn/evaluator.py
python/flowforge-core/src/flowforge/engine/saga.py
python/flowforge-core/src/flowforge/engine/fire.py
python/flowforge-core/src/flowforge/engine/dynamic_fork.py
python/flowforge-core/src/flowforge/engine/sla_scheduler.py
python/flowforge-core/src/flowforge/ports/documents.py
python/flowforge-core/src/flowforge/dsl/workflow_def.py
```

Interpretation: broad substring matches. A focused actual-call scan found no executable dynamic-code call sites in audited source roots.

Focused command:

```bash
grep -rn 'eval(\|exec(\|__import__\|subprocess\|os\.system' python/flowforge-core/src/ python/flowforge-fastapi/src/ python/flowforge-jtbd/src/ --include='*.py' 2>&1
```

Output:

```text
python/flowforge-core/src/flowforge/dmn/evaluator.py:6:The evaluator is intentionally safe: it never calls ``eval()``, never
```

### 2. Core SQL grep

Command:

```bash
grep -r 'sql\|SELECT\|INSERT\|UPDATE\|DELETE' python/flowforge-core/src/ --include='*.py' -n 2>&1 | head -30
```

Output:

```text
python/flowforge-core/src/flowforge/engine/saga.py:5::mod:`flowforge_sqlalchemy.saga_queries.SagaQueries`.
python/flowforge-core/src/flowforge/engine/saga.py:66:	"""The subset of ``flowforge_sqlalchemy.saga_queries.SagaQueries`` that
```

### 3. HMAC/timing grep

Command:

```bash
grep -r 'hmac\|compare_digest\|timing' python/ --include='*.py' -l 2>&1
```

Output:

```text
python/flowforge-jtbd-hub/src/flowforge_jtbd_hub/app.py
python/flowforge-notify-multichannel/tests/test_transports.py
python/flowforge-notify-multichannel/src/flowforge_notify_multichannel/transports.py
python/flowforge-signing-kms/tests/test_kms.py
python/flowforge-signing-kms/tests/test_hmac.py
python/flowforge-signing-kms/src/flowforge_signing_kms/__init__.py
python/flowforge-signing-kms/src/flowforge_signing_kms/hmac_dev.py
python/flowforge-fastapi/tests/test_router_runtime.py
python/flowforge-fastapi/src/flowforge_fastapi/auth.py
python/flowforge-connectors/src/flowforge_connectors/github.py
python/flowforge-connectors/src/flowforge_connectors/stripe.py
python/flowforge-jtbd/tests/test_registry.py
python/flowforge-jtbd/tests/unit/test_E_47_acceptance.py
python/flowforge-jtbd/tests/unit/test_lint_conflicts.py
python/flowforge-jtbd/src/flowforge_jtbd/lint/conflicts.py
python/flowforge-jtbd/src/flowforge_jtbd/registry/manifest.py
python/flowforge-cli/tests/test_jtbd_conflicts.py
python/flowforge-cli/src/flowforge_cli/jtbd/transforms.py
python/flowforge-cli/src/flowforge_cli/jtbd/lint/__init__.py
python/flowforge-cli/src/flowforge_cli/jtbd/lint/conflicts.py
python/flowforge-cli/src/flowforge_cli/jtbd/generators/sla_loadtest.py
python/flowforge-cli/src/flowforge_cli/jtbd/generators/lineage.py
```

Focused compare-digest command:

```bash
grep -rn 'compare_digest' python/flowforge-jtbd/src/ python/flowforge-core/src/ python/flowforge-fastapi/src/ python/flowforge-signing-kms/src/ --include='*.py' 2>&1
```

Output:

```text
python/flowforge-fastapi/src/flowforge_fastapi/auth.py:248:		if not hmac.compare_digest(sig, expected):
python/flowforge-fastapi/src/flowforge_fastapi/auth.py:334:	if not cookie or not header or not hmac.compare_digest(cookie, header):
python/flowforge-signing-kms/src/flowforge_signing_kms/hmac_dev.py:209:        return hmac.compare_digest(expected, bytes(signature))
```

### 4. TODO/FIXME/stub grep

Command:

```bash
grep -rn 'TODO\|FIXME\|HACK\|XXX\|STUB\|NotImplemented\|raise NotImplementedError' python/flowforge-core/src/ python/flowforge-fastapi/src/ python/flowforge-jtbd/src/ --include='*.py' 2>&1 | head -50
```

Output:

```text
python/flowforge-jtbd/src/flowforge_jtbd/ports/llm.py:39:	Adapters that lack a capability raise :class:`NotImplementedError`
```

Full command without `head` produced the same single hit.

### 5. Core `pass`/ellipsis grep

Command:

```bash
grep -rn 'pass$\|\.\.\.  *$' python/flowforge-core/src/ --include='*.py' 2>&1 | head -30
```

Output: no output.

### 6. `fire()` location and read

Codebase memory identified:

```text
python/flowforge-core/src/flowforge/engine/fire.py:347-452 flowforge.engine.fire.fire
python/flowforge-core/src/flowforge/engine/fire.py:455-863 flowforge.engine.fire._fire_locked
```

Key references:

- `python/flowforge-core/src/flowforge/engine/fire.py:180-191` transition matching scans.
- `python/flowforge-core/src/flowforge/engine/fire.py:194-210` guard evaluation.
- `python/flowforge-core/src/flowforge/engine/fire.py:347-452` public `fire()`.
- `python/flowforge-core/src/flowforge/engine/fire.py:636-664` token-fire audit/outbox dispatch handling.
- `python/flowforge-core/src/flowforge/engine/fire.py:693-832` primary fire planning, mutation, audit, outbox, rollback.
- `python/flowforge-core/src/flowforge/engine/fire.py:836-850` manual-review task creation.

### 7. Expression directory and evaluator

Command:

```bash
find python/flowforge-core/src/flowforge/expr -maxdepth 3 -type f -name '*.py' | sort
```

Output:

```text
python/flowforge-core/src/flowforge/expr/__init__.py
python/flowforge-core/src/flowforge/expr/evaluator.py
python/flowforge-core/src/flowforge/expr/ops/__init__.py
```

Key references:

- `python/flowforge-core/src/flowforge/expr/__init__.py:1-18` expression module contract.
- `python/flowforge-core/src/flowforge/expr/evaluator.py:201-207` operator-call detection.
- `python/flowforge-core/src/flowforge/expr/evaluator.py:233-263` evaluator execution.
- `python/flowforge-core/src/flowforge/expr/evaluator.py:266-304` arity walker and unknown-op behavior.
- `python/flowforge-core/src/flowforge/expr/ops/__init__.py:1-141` built-in operator catalogue and registration.

### 8. Sleep/blocking grep

Command:

```bash
grep -rn 'asyncio.sleep\|time.sleep\|blocking' python/ --include='*.py' 2>&1 | head -20
```

Output:

```text
python/flowforge-audit-pg/tests/test_sink.py:5:re-run against the live Postgres database to verify the DELETE-blocking
python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:5:* Append-only table ``ff_audit_events`` with a DELETE-blocking PG trigger
python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:11:* SQLite fallback for tests (DELETE-blocking trigger replaced by a Python
python/flowforge-audit-pg/src/flowforge_audit_pg/sink.py:165:	"""Create ``ff_audit_events`` and install the DELETE-blocking trigger (PG only)."""
python/flowforge-signing-kms/src/flowforge_signing_kms/kms.py:191:		E-56 / SK-04: the blocking ``boto3`` client call is dispatched
python/flowforge-signing-kms/src/flowforge_signing_kms/kms.py:235:		E-56 / SK-04: blocking ``boto3`` call dispatched via
python/flowforge-signing-kms/src/flowforge_signing_kms/kms.py:334:		E-56 / SK-04: blocking ``google-cloud-kms`` call dispatched via
python/flowforge-signing-kms/src/flowforge_signing_kms/kms.py:381:		E-56 / SK-04: blocking gRPC call dispatched via
python/flowforge-outbox-pg/tests/test_worker.py:564:        await asyncio.sleep(0.2)
python/flowforge-outbox-pg/tests/test_worker.py:661:        await asyncio.sleep(0.05)
python/flowforge-outbox-pg/src/flowforge_outbox_pg/worker.py:469:            await asyncio.sleep(poll_interval_seconds)
python/flowforge-tenancy/tests/test_resolvers.py:180:				await asyncio.sleep(0)
python/flowforge-tenancy/tests/test_resolvers.py:186:			await asyncio.sleep(0)
python/flowforge-tenancy/tests/test_resolvers.py:211:			await asyncio.sleep(0)
python/flowforge-tenancy/tests/test_resolvers.py:218:		await asyncio.sleep(0)
python/flowforge-core/tests/unit/test_fault_injector.py:219:def test_multiple_specs_first_blocking_wins() -> None:
python/flowforge-core/tests/unit/test_fault_injector.py:227:	# First blocking spec wins; only one fault logged.
python/flowforge-core/tests/unit/test_fault_injector.py:246:def test_blocking_fault_emits_audit_event() -> None:
python/flowforge-core/src/flowforge/replay/fault.py:233:	def _blocking_mode(self, specs: list[FaultSpec]) -> FaultSpec | None:
python/flowforge-core/src/flowforge/replay/fault.py:234:		"""Return the first blocking-mode spec, if any."""
```

Focused audited-root command:

```bash
grep -rn 'asyncio.sleep\|time.sleep\|blocking' python/flowforge-core/src/ python/flowforge-fastapi/src/ python/flowforge-jtbd/src/ --include='*.py' 2>&1
```

Output:

```text
python/flowforge-core/src/flowforge/replay/fault.py:233:	def _blocking_mode(self, specs: list[FaultSpec]) -> FaultSpec | None:
python/flowforge-core/src/flowforge/replay/fault.py:234:		"""Return the first blocking-mode spec, if any."""
python/flowforge-core/src/flowforge/replay/fault.py:280:		blocking = self._blocking_mode(active)
python/flowforge-core/src/flowforge/replay/fault.py:281:		if blocking:
python/flowforge-core/src/flowforge/replay/fault.py:282:			mode = blocking.mode
python/flowforge-core/src/flowforge/ports/analytics.py:33:	Implementations MUST be non-blocking on the request hot path —
```

## Additional Evidence

### Dashboard escaping

Command:

```bash
grep -rn 'html.escape\|markupsafe\|escape(' python/flowforge-fastapi/src/ python/flowforge-fastapi/tests --include='*.py' 2>&1
```

Output: no output.

Relevant files:

- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:51-112`
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:135-410`
- `python/flowforge-fastapi/tests/test_dashboard.py:1-108`

Dashboard tests are smoke tests only; they do not cover escaping.

### Assertion-based validation

Command:

```bash
grep -rn '^\s*assert ' python/flowforge-core/src/ python/flowforge-fastapi/src/ python/flowforge-jtbd/src/ --include='*.py' 2>&1 | head -120
```

Key pgvector hits:

```text
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:101:		assert self.dim >= 1, "vector dim must be >= 1"
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:102:		assert self.schema, "schema must be non-empty"
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:103:		assert self.table, "table must be non-empty"
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:104:		assert self.ivfflat_lists >= 1, "ivfflat lists must be >= 1"
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:155:		assert index_name, "index_name must be non-empty"
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:213:		assert jtbd_id, "jtbd_id must be non-empty"
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:214:		assert len(vector) == self.spec.dim, (
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:244:		assert len(query_vector) == self.spec.dim, (
python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:248:		assert top_k >= 1, "top_k must be >= 1"
```

### SQL construction outside core

Relevant files:

- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:135-157`
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:163-201`
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:228-251`
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:287-310`
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:339-344`
- `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py:376-390`
- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:106-156`
- `python/flowforge-jtbd/src/flowforge_jtbd/ai/pgvector_store.py:219-227`

### LLM prompt-injection guard

Relevant file:

- `python/flowforge-jtbd/src/flowforge_jtbd/ai/nl_to_jtbd.py:187-224`

### LLM provider stub inventory

Relevant file:

- `python/flowforge-jtbd/src/flowforge_jtbd/ports/llm.py:30-76`
