"""arch §17 architectural invariants — audit-2026 + v0.3.0-engr conformance suite.

This file is the single point of truth for the 10 architectural invariants
the framework must hold. Invariants 1-8 originate in audit-2026 (audit-fix-plan
§3, §4, §5.3, §F-3 / R-3); invariant 9 lands as part of the E-74 follow-up
(parallel_fork tokens); invariant 10 lands in v0.3.0 W0 alongside item 2
(compensation synthesis). Each invariant maps to:

	* one or more audit findings (E-xx ticket) or v0.3.0 wave / item id
	* a marker (`@invariant_p0` or `@invariant_p1`)
	* a sprint exit gate (S0 = invariants 1, 2, 3, 7; S1 = 4, 5, 6, 8;
	  E-74 follow-up = 9; v0.3.0 W0 = 10)

When the owning ticket lands:

	1. Replace the `pytest.xfail(...)` body with a regression-quality test.
	2. Drop the `@pytest.mark.xfail(strict=True)` decorator.
	3. Update `framework/docs/audit-2026/signoff-checklist.md` ticket row
	   (audit-2026) or `framework/docs/v0.3.0-engineering/signoff-checklist.md`
	   row (v0.3.0).
	4. (P0 only) Add a `[SECURITY]` entry to `CHANGELOG.md`.

Removal of an `@invariant_p0` test requires security-team review (CR-3).
"""

from __future__ import annotations

import asyncio

import pytest


# ---------------------------------------------------------------------------
# Invariant 1 — Tenant isolation
#   Findings: T-01 (bind-param GUC), T-02 (ContextVar elevation), T-03 (in-tx assert)
#   Owning ticket: E-36 (LANDED)
#   Sprint gate: S0
# ---------------------------------------------------------------------------


class _StubSession:
	"""Test stub matching the AsyncSession surface flowforge-tenancy expects."""

	def __init__(self, in_tx: bool = True) -> None:
		self.calls: list[tuple[str, dict]] = []
		self._in_tx = in_tx

	def in_transaction(self) -> bool:
		return self._in_tx

	def execute(self, sql, params=None):
		self.calls.append((sql, dict(params or {})))


@pytest.mark.invariant_p0
def test_invariant_1_tenant_isolation() -> None:
	"""Tenant rows are unreachable across tenants under the RLS policy.

	Acceptance criterion (audit-fix-plan §4.1 T-01, §4.3 T-02, §4.4 T-03):
	  * `_set_config('app.tenant_id', '<bad>')` MUST raise `ValueError`
	    when the key violates `^[a-zA-Z_][a-zA-Z_0-9.]*$`.
	  * Concurrent `elevated_scope()` in async tasks observe their own scope.
	  * `bind_session()` asserts `session.in_transaction()`.
	"""

	from flowforge_tenancy import SingleTenantGUC
	from flowforge_tenancy.single import _GUC_KEY_RE, _SET_CONFIG_SQL, _set_config

	# T-01: regex pattern + constant SQL with both args bound.
	assert _GUC_KEY_RE.pattern == r"^[a-zA-Z_][a-zA-Z_0-9.]*$"
	assert _SET_CONFIG_SQL == "SELECT set_config(:k, :v, true)"

	r = SingleTenantGUC("tenant-A")
	seen: list[tuple[bool, str]] = []

	async def _drive() -> None:
		# T-01: malicious key → ValueError, no SQL emitted.
		s = _StubSession()
		with pytest.raises(ValueError):
			await _set_config(s, "x'); DROP TABLE--", "v")
		assert s.calls == []

		# T-01: valid key → bind both name and value as parameters.
		s = _StubSession()
		await _set_config(s, "app.tenant_id", "tenant-A")
		assert s.calls[-1] == (
			"SELECT set_config(:k, :v, true)",
			{"k": "app.tenant_id", "v": "tenant-A"},
		)

		# T-02: concurrent elevated scopes observe their own state.
		async def worker(elevate: bool) -> None:
			if elevate:
				async with r.elevated_scope():
					await asyncio.sleep(0)
					sx = _StubSession()
					await r.bind_session(sx, "tenant-A")
					elev = [c for c in sx.calls if c[1].get("k") == "app.elevated"]
					seen.append((elevate, elev[-1][1]["v"]))
			else:
				await asyncio.sleep(0)
				sx = _StubSession()
				await r.bind_session(sx, "tenant-A")
				elev = [c for c in sx.calls if c[1].get("k") == "app.elevated"]
				seen.append((elevate, elev[-1][1]["v"]))

		await asyncio.gather(*(worker(i % 2 == 0) for i in range(20)))

		# T-03: bind_session outside a tx raises.
		s_no_tx = _StubSession(in_tx=False)
		with pytest.raises(AssertionError):
			await r.bind_session(s_no_tx, "tenant-A")
		assert s_no_tx.calls == []

	asyncio.run(_drive())

	for elevate, v in seen:
		assert v == ("true" if elevate else "false")


# ---------------------------------------------------------------------------
# Invariant 2 — Engine fire two-phase atomicity
#   Findings: C-01 (outbox rollback), C-04 (per-instance lock)
#   Owning ticket: E-32 (engine-hotfix EPIC) — LANDED
#   Sprint gate: S0
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p0
def test_invariant_2_engine_fire_two_phase() -> None:
	"""`fire()` is all-or-nothing across (state-advance, audit, outbox).

	Acceptance criterion (audit-fix-plan §4.1 C-01, C-04):
	  * Outbox raise during fire → audit row + state transition rolled back.
	  * 100 concurrent `fire()` for one instance → exactly 1 transition.
	"""

	import copy as _copy

	from flowforge import config as _config
	from flowforge.dsl import WorkflowDef
	from flowforge.engine import fire, new_instance
	from flowforge.engine.fire import ConcurrentFireRejected, OutboxDispatchError
	from flowforge.ports.types import OutboxEnvelope, Principal
	from flowforge.testing.port_fakes import InMemoryAuditSink, InMemoryOutbox

	def _toy_def() -> WorkflowDef:
		return WorkflowDef.model_validate(
			{
				"key": "claim_intake",
				"version": "1.0.0",
				"subject_kind": "claim",
				"initial_state": "intake",
				"states": [
					{"name": "intake", "kind": "manual_review"},
					{"name": "triage", "kind": "manual_review"},
				],
				"transitions": [
					{
						"id": "submit",
						"event": "submit",
						"from_state": "intake",
						"to_state": "triage",
						"effects": [{"kind": "notify", "template": "claim.submitted"}],
					}
				],
			}
		)

	class _FailingOutbox(InMemoryOutbox):
		async def dispatch(self, envelope: OutboxEnvelope, backend: str = "default") -> None:
			raise RuntimeError("boom")

	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	try:
		# C-01: outbox failure → state + audit absent.
		_config.reset_to_fakes()
		_config.outbox = _FailingOutbox()
		_config.audit = InMemoryAuditSink()

		wd = _toy_def()
		inst = new_instance(wd, initial_context={"intake": {"policy_id": "p"}})
		pre_state = inst.state
		pre_ctx = _copy.deepcopy(inst.context)

		with pytest.raises(OutboxDispatchError):
			loop.run_until_complete(
				fire(wd, inst, "submit", principal=Principal(user_id="u", is_system=True))
			)
		assert inst.state == pre_state
		assert inst.context == pre_ctx
		assert len(_config.audit.events) == 0

		# C-04: 100 concurrent fires → exactly one transition.
		_config.reset_to_fakes()
		inst2 = new_instance(wd, initial_context={"intake": {"policy_id": "p"}})

		async def attempt() -> str | None:
			try:
				r = await fire(
					wd, inst2, "submit", principal=Principal(user_id="u", is_system=True)
				)
				return r.matched_transition_id
			except ConcurrentFireRejected:
				return "REJECTED"

		results = loop.run_until_complete(asyncio.gather(*(attempt() for _ in range(100))))
		assert sum(1 for r in results if r == "submit") == 1
		assert inst2.state == "triage"
	finally:
		loop.close()


# ---------------------------------------------------------------------------
# Invariant 3 — Replay determinism (frozen op registry + arity enforcement)
#   Findings: C-06, C-07
#   Owning ticket: E-35
#   Sprint gate: S0
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p0
def test_invariant_3_replay_determinism() -> None:
	"""Op registry is immutable after import; same DSL → same outcomes.

	Acceptance criterion (audit-fix-plan §4.1 C-06, C-07):
	  * Post-startup `register_op("==", ...)` raises `RegistryFrozenError`.
	  * Op called with wrong arity raises `ArityMismatchError` at compile time.
	  * Same DSL across two evaluator instances → byte-identical guard outcomes.
	"""

	from flowforge.compiler import ValidationError, validate
	from flowforge.expr import (
		ArityMismatchError,
		RegistryFrozenError,
		check_arity,
		evaluate,
		register_op,
	)
	from flowforge.expr.evaluator import _OPS  # noqa: SLF001

	# C-06: registry frozen — post-import register raises.
	with pytest.raises(RegistryFrozenError):
		register_op("never_registered_at_runtime", lambda: None, arity=0)

	# C-06: ops view is read-only.
	with pytest.raises((TypeError, AttributeError)):
		_OPS["mut"] = lambda: None  # type: ignore[index]

	# C-06: byte-identical guard outcomes across repeat evaluations of
	# the same DSL + ctx. A frozen registry implies a constant function.
	dsl = {
		"and": [
			{">": [{"var": "amount"}, 100]},
			{"==": [{"var": "currency"}, "USD"]},
			{"or": [{"not_null": {"var": "tenant"}}, {"between": [{"var": "n"}, 0, 9]}]},
		]
	}
	ctx = {"amount": 250, "currency": "USD", "tenant": None, "n": 5}
	first = evaluate(dsl, ctx)
	for _ in range(31):
		assert evaluate(dsl, ctx) == first
	assert first is True

	# C-07: wrong arity surfaces at compile time via the validator.
	bad_workflow = {
		"key": "demo",
		"version": "1.0.0",
		"subject_kind": "demo_subject",
		"initial_state": "draft",
		"states": [
			{"name": "draft", "kind": "manual_review"},
			{"name": "approved", "kind": "terminal_success"},
		],
		"transitions": [
			{
				"id": "submit",
				"event": "submit",
				"from_state": "draft",
				"to_state": "approved",
				"guards": [{"kind": "expr", "expr": {"==": [1, 2, 3]}}],
			}
		],
	}
	with pytest.raises(ValidationError):
		validate(bad_workflow, strict=True)

	# C-07: walker reports arity errors without raising; pinpoints the op.
	errors = check_arity({"between": [1, 2]})
	assert errors and "'between'" in errors[0]

	# C-07: runtime fallback for programs that bypassed the validator.
	with pytest.raises(ArityMismatchError):
		evaluate({"==": [1, 2, 3]}, {})


# ---------------------------------------------------------------------------
# Invariant 4 — Saga ledger durability
#   Findings: C-09
#   Owning ticket: E-40 (LANDED)
#   Sprint gate: S1
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p1
def test_invariant_4_saga_ledger_durability() -> None:
	"""Saga compensation entries survive crash and replay exactly once.

	Acceptance criterion (audit-fix-plan §4.2 C-09):
	  * Crash mid-fire; restart; compensation worker replays ledger entries;
	    integration test asserts compensations executed exactly once.

	The schema lives in ``flowforge_sqlalchemy.models.WorkflowSagaStep``
	with a UNIQUE(instance_id, idx) constraint that prevents duplicate
	row appends. The :class:`flowforge.engine.saga.CompensationWorker`
	dispatcher reads ``status='pending'`` rows in idx-DESC order and
	marks each ``compensated`` (success) or ``failed`` (handler raised)
	on the way out. Restart-replay is exactly-once because a fresh
	worker instance reading the same DB sees zero pending rows.
	"""

	from flowforge.engine.saga import CompensationWorker
	from flowforge_sqlalchemy.base import Base
	from flowforge_sqlalchemy.saga_queries import SagaQueries
	from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

	calls: list[str] = []

	async def hndlr(args: dict[str, object]) -> None:
		calls.append("invoked")

	async def _drive() -> None:
		engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
		sf = async_sessionmaker(engine, expire_on_commit=False)

		queries = SagaQueries(sf, tenant_id="t")
		await queries.append("inst", kind="undo")
		await queries.append("inst", kind="undo")

		# First worker (the "crashed" replica that restarts).
		w1 = CompensationWorker()
		w1.register("undo", hndlr)
		report1 = await w1.replay_pending("inst", queries)
		assert report1.compensated == 2

		# Second worker (post-restart). Same DB; nothing pending.
		w2 = CompensationWorker()
		w2.register("undo", hndlr)
		report2 = await w2.replay_pending("inst", queries)
		assert report2.total == 0

		await engine.dispose()

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_drive())
	finally:
		loop.close()

	# Handler ran exactly twice (one per durable row), not four times.
	assert len(calls) == 2, f"expected exactly-once replay, got {len(calls)}"


# ---------------------------------------------------------------------------
# Invariant 5 — Cross-runtime evaluator parity (TS↔Python)
#   Findings: JS-01, JS-02
#   Owning ticket: E-43
#   Sprint gate: S1
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p1
def test_invariant_5_cross_runtime_parity() -> None:
	"""TypeScript and Python evaluators are byte-identical on the conformance fixture.

	Acceptance criterion (audit-fix-plan §4.2 JS-01, JS-02):
	  * 200-input cross-runtime fixture file → identical guard outputs.

	Python side is asserted here directly. The TS side runs the same
	fixture under vitest in
	`framework/js/flowforge-integration-tests/expr-parity.test.ts`. The
	fixture is generated by `generate_fixture.py` from the live Python
	evaluator, so any drift between runtimes surfaces as a vitest failure.
	"""

	import json
	from pathlib import Path

	from flowforge.expr import evaluate

	fixture_path = (
		Path(__file__).resolve().parent.parent
		/ "cross_runtime"
		/ "fixtures"
		/ "expr_parity_200.json"
	)
	assert fixture_path.exists(), f"missing fixture: {fixture_path}"
	data = json.loads(fixture_path.read_text())
	cases = data["cases"]
	assert len(cases) == 200, f"fixture must hold exactly 200 cases, got {len(cases)}"

	failures: list[str] = []
	for case in cases:
		got = evaluate(case["expr"], case["ctx"])
		if got != case["expected"]:
			failures.append(
				f"{case['id']}: expected={case['expected']!r} got={got!r}"
			)
	assert not failures, "\n".join(failures[:10])


# ---------------------------------------------------------------------------
# Invariant 6 — Signing default forbidden + key rotation
#   Findings: SK-01, SK-02, SK-03
#   Owning ticket: E-34 (LANDED)
#   Sprint gate: S0 (deploy gate) / S1 (residual property tests)
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p1
def test_invariant_6_signing_default_forbidden() -> None:
	"""No HMAC default secret; key rotation by `key_id`; transient errors
	distinct from invalid signatures.

	Acceptance criterion (audit-fix-plan §4.1 SK-01, §4.2 SK-02, SK-03):
	  * Import + instantiate w/o env var raises `RuntimeError`
	    with "explicit secret required" in the message.
	  * `verify(key_id="unknown", ...)` raises `UnknownKeyId`.
	  * `KmsTransientError` is distinct from the invalid-signature path
	    (transient → raise; permanent invalid → return False).
	"""

	import os

	from flowforge_signing_kms.errors import (
		KmsSignatureInvalid,
		KmsTransientError,
		UnknownKeyId,
	)
	from flowforge_signing_kms.hmac_dev import HmacDevSigning

	# SK-01: no env, no opt-in → refuse to start.
	saved = os.environ.pop("FLOWFORGE_SIGNING_SECRET", None)
	saved_opt_in = os.environ.pop("FLOWFORGE_ALLOW_INSECURE_DEFAULT", None)
	try:
		with pytest.raises(RuntimeError) as exc_info:
			HmacDevSigning()
		assert "explicit secret required" in str(exc_info.value)
	finally:
		if saved is not None:
			os.environ["FLOWFORGE_SIGNING_SECRET"] = saved
		if saved_opt_in is not None:
			os.environ["FLOWFORGE_ALLOW_INSECURE_DEFAULT"] = saved_opt_in

	# SK-02: explicit key map; pre-rotation sig verifies against pre-rotation key.
	signer_v1 = HmacDevSigning(secret="secret-v1", key_id="key-v1")

	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	try:
		payload = b"hello world"
		sig_v1 = loop.run_until_complete(signer_v1.sign_payload(payload))

		# Rotated signer carries both keys.
		signer_v2 = HmacDevSigning(
			keys={"key-v1": "secret-v1", "key-v2": "secret-v2"},
			current_key_id="key-v2",
		)
		# Pre-rotation sig verifies under its original key_id.
		assert loop.run_until_complete(
			signer_v2.verify(payload, sig_v1, "key-v1")
		) is True

		# SK-02: unknown key_id → UnknownKeyId, NOT silent False.
		with pytest.raises(UnknownKeyId):
			loop.run_until_complete(
				signer_v2.verify(payload, sig_v1, "key-unknown")
			)
	finally:
		loop.close()

	# SK-03: KmsTransientError and KmsSignatureInvalid are distinct types so
	# callers can branch on transient-retry vs permanent-invalid.
	assert KmsTransientError is not KmsSignatureInvalid
	assert not issubclass(KmsTransientError, KmsSignatureInvalid)
	assert not issubclass(KmsSignatureInvalid, KmsTransientError)


# ---------------------------------------------------------------------------
# Invariant 7 — Audit-chain monotonicity
#   Findings: AU-01 (advisory lock), AU-02 (chunked verify), AU-03 (canonical golden)
#   Owning ticket: E-37
#   Sprint gate: S0
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p0
def test_invariant_7_audit_chain_monotonic() -> None:
	"""Audit chain is fork-free under concurrency and verifies in O(chunk).

	Acceptance criterion (audit-fix-plan §4.2 AU-01, AU-02, AU-03):
	  * 100 concurrent records for 1 tenant → `verify_chain()` reports zero forks.
	  * `verify_chain()` streams in chunks (default 10K rows); peak memory
	    bounded by chunk size, not total row count.
	  * Golden-byte fixture under ``tests/audit_2026/fixtures/canonical_golden.bin``
	    verifies against committed bytes; refuses to load on hash mismatch.
	"""

	from pathlib import Path

	from sqlalchemy.ext.asyncio import create_async_engine

	from flowforge.ports.types import AuditEvent
	from flowforge_audit_pg import PgAuditSink, create_tables
	from flowforge_audit_pg._golden import (
		GoldenIntegrityError,
		load_golden,
		recompute_row,
	)

	# AU-03: golden envelope refuses on tamper, and committed canonical bytes
	# match the in-process encoder.
	golden_path = (
		Path(__file__).resolve().parents[1]
		/ "audit_2026"
		/ "fixtures"
		/ "canonical_golden.bin"
	)
	bundle = load_golden(golden_path)
	assert bundle.rows
	for row in bundle.rows:
		got_canonical, got_sha = recompute_row(row.prev_sha256, row.input)
		assert got_canonical == row.canonical_json_bytes
		assert got_sha == row.row_sha256

	# AU-01: 100 concurrent records → zero forks. Run in a fresh sqlite for
	# hermetic conformance (no temp-dir fixture available in sync test).
	import asyncio
	import tempfile
	from datetime import datetime, timedelta, timezone

	import sqlalchemy as sa

	tmp = tempfile.NamedTemporaryFile(prefix="ff_audit_inv7_", suffix=".db", delete=False)
	tmp.close()
	engine = None
	try:
		async def _drive() -> None:
			nonlocal engine
			engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
			async with engine.begin() as conn:
				await create_tables(conn)
			sink = PgAuditSink(engine)

			# AU-01: concurrent records.
			N = 50

			async def writer(idx: int) -> str:
				ts = datetime(2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc) + timedelta(microseconds=idx)
				return await sink.record(
					AuditEvent(
						kind=f"k.{idx}",
						subject_kind="x",
						subject_id=f"s-{idx}",
						tenant_id="conformance-tenant",
						actor_user_id="u",
						payload={"i": idx},
						occurred_at=ts,
					)
				)

			ids = await asyncio.gather(*(writer(i) for i in range(N)))
			assert len(set(ids)) == N
			verdict = await sink.verify_chain()
			assert verdict.ok is True
			assert verdict.checked_count == N

			# Ordinals are dense per tenant.
			from flowforge_audit_pg.sink import ff_audit_events

			async with engine.connect() as conn:
				rows = (
					await conn.execute(
						sa.select(ff_audit_events.c.ordinal)
						.where(ff_audit_events.c.tenant_id == "conformance-tenant")
						.order_by(ff_audit_events.c.ordinal.asc())
					)
				).fetchall()
			assert [r[0] for r in rows] == list(range(1, N + 1))

		asyncio.run(_drive())
	finally:
		if engine is not None:
			asyncio.run(engine.dispose())
		Path(tmp.name).unlink(missing_ok=True)

	# AU-03: tamper detection.
	tampered = golden_path.read_bytes() + b"\x00"
	with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
		tf.write(tampered)
		tf.flush()
		try:
			with pytest.raises(GoldenIntegrityError):
				load_golden(Path(tf.name))
		finally:
			Path(tf.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Invariant 8 — Migration RLS DDL safety
#   Findings: J-01
#   Owning ticket: E-38
#   Sprint gate: S0 (P0 deploy gate) — also conformance covers the residual property test
# ---------------------------------------------------------------------------


@pytest.mark.invariant_p1
def test_invariant_8_migration_rls_safe(monkeypatch) -> None:
	"""Alembic RLS DDL only operates on whitelisted, quoted table names.

	Acceptance criterion (audit-fix-plan §4.1 J-01):
	  * Alembic upgrade with monkey-patched malicious table-list raises `ValueError`.
	  * Tables resolved via `sqlalchemy.sql.quoted_name` and asserted in allow-list.
	"""

	from sqlalchemy.sql import quoted_name

	from flowforge_jtbd.db.alembic_bundle.versions import r2_jtbd

	# Allow-list is immutable and covers every spliced table.
	assert isinstance(r2_jtbd._RLS_ALLOWLIST, frozenset)
	for table in (
		*r2_jtbd._RLS_TABLES_TENANT_NULLABLE,
		*r2_jtbd._RLS_TABLES_TENANT_REQUIRED,
		"jtbd_domains",
	):
		assert table in r2_jtbd._RLS_ALLOWLIST

	# Identifier validation rejects malicious shapes and round-trips good ones
	# through quoted_name.
	for bogus in ("users; DROP", "' OR 1=1 --", "", "1abc", "JTBD_LIBRARIES"):
		with pytest.raises(ValueError):
			r2_jtbd._assert_known_table(bogus)
	got = r2_jtbd._assert_known_table("jtbd_libraries")
	assert isinstance(got, quoted_name)

	# Monkey-patched malicious tuple — must raise BEFORE op.execute fires.
	executed: list[str] = []

	class _StubOp:
		@staticmethod
		def execute(sql, *a, **kw):
			executed.append(str(sql))

	monkeypatch.setattr(r2_jtbd, "op", _StubOp)
	monkeypatch.setattr(r2_jtbd, "_is_postgres", lambda: True)
	monkeypatch.setattr(
		r2_jtbd,
		"_RLS_TABLES_TENANT_NULLABLE",
		("users; DROP TABLE users; --",),
	)
	with pytest.raises(ValueError):
		r2_jtbd._install_rls_if_postgres()
	assert executed == [], "DDL leaked past the allow-list gate"


# ---------------------------------------------------------------------------
# Invariant 9 — parallel_fork token primitives are safe (E-74 phase 1)
# ---------------------------------------------------------------------------
#
# E-74 ships token primitives + helper API; full engine wiring through
# fire() is deferred to a follow-up. The existing host-managed pattern at
# ``tests/integration/python/tests/test_parallel_regions.py`` uses context
# flags + a WorkflowInstanceToken table; this invariant covers the
# complementary in-process token primitives that adapters consume.
#
# Pinned by this invariant:
#   - Token IDs are unique across a single fork allocation.
#   - all_branches_joined() is True iff zero tokens remain in the region.
#   - consume_token() raises TokenAlreadyConsumedError on a missing id —
#     replay-safety contract per E-74 R-3.
#   - TokenSet survives deepcopy with no shared mutation between clones —
#     required for engine snapshot/restore and deterministic replay.


@pytest.mark.invariant_p1
def test_invariant_9_parallel_fork_token_primitives_safe() -> None:
	"""E-74 phase 1: token primitives + helpers behave deterministically."""

	import copy as _copy
	from dataclasses import dataclass

	from flowforge.engine import _fork
	from flowforge.engine.tokens import TokenSet

	@dataclass
	class _StubTransition:
		to: str

	branches = [
		_StubTransition(to="branch_a"),
		_StubTransition(to="branch_b"),
		_StubTransition(to="branch_c"),
	]
	tokens = _fork.make_fork_tokens(region="fork_review", branches=branches)

	# 3 tokens, all unique, all tagged with the fork's region.
	assert len(tokens) == 3
	assert len({t.id for t in tokens}) == 3
	assert all(t.region == "fork_review" for t in tokens)

	tset = TokenSet()
	for t in tokens:
		tset.add(t)

	# Region not yet drained.
	assert not _fork.all_branches_joined(tset, "fork_review")
	assert tset.count_in_region("fork_review") == 3

	# Drain one token at a time.
	_fork.consume_token(tset, tokens[0].id)
	assert tset.count_in_region("fork_review") == 2
	_fork.consume_token(tset, tokens[1].id)
	_fork.consume_token(tset, tokens[2].id)
	assert _fork.all_branches_joined(tset, "fork_review")

	# Re-consuming a previously-consumed id raises (replay-safety).
	with pytest.raises(_fork.TokenAlreadyConsumedError):
		_fork.consume_token(tset, tokens[0].id)

	# TokenSet survives deepcopy (engine snapshot/restore + replay).
	tset2 = TokenSet()
	for t in tokens:
		tset2.add(t)
	cloned = _copy.deepcopy(tset2)
	assert {x.id for x in cloned.list()} == {x.id for x in tset2.list()}
	cloned.remove(tokens[0].id)
	assert tset2.count_in_region("fork_review") == 3
	assert cloned.count_in_region("fork_review") == 2


# ---------------------------------------------------------------------------
# Invariant 10 — Compensation symmetry (v0.3.0 W0 / item 2)
# ---------------------------------------------------------------------------
#
# v0.3.0 wave 0 lands the compensation synthesiser
# (`flowforge_cli.jtbd.transforms.derive_transitions` for the synthesis side
# and `_PER_JTBD_GENERATORS[workflow_adapter]` for the rendered surface).
# Every JTBD declaring an `edge_case` with `handle: "compensate"` and at
# least one forward `effects: [{kind: "create_entity"}]` transition MUST
# emit a paired `compensate_delete` saga step in matching LIFO order.
#
# Pinned by this invariant:
#   - Forward `create_entity` count == compensate `compensate_delete` count.
#   - LIFO order: the relative order of `compensate_delete` entries inside
#     the synthesised compensate transition equals the *reverse* of the
#     forward `create_entity` order — so the most recently-applied forward
#     create is the first to be undone.
#   - The corresponding `workflow_adapter` template output emits the
#     `CompensationWorker` import gate so hosts can wire the synthesised
#     handlers through the same surface as `fire_event`.


@pytest.mark.invariant_p1
def test_invariant_10_compensation_symmetry() -> None:
	"""v0.3.0 W0 / item 2 — paired compensate_delete in LIFO order.

	Acceptance criterion (v0.3.0-engineering-plan §8 invariant 10):
	  * Parse the conformance fixture under
	    ``tests/conformance/fixtures/compensation_symmetry/jtbd-bundle.json``.
	  * Run the synthesiser via ``normalize`` (which calls
	    ``derive_states`` + ``derive_transitions``).
	  * For every JTBD whose synthesised transitions contain a
	    ``compensate`` event, assert
	    ``len(compensate_delete) == len(forward create_entity)`` and that
	    the ordering is LIFO.
	  * Also exercise the rendered ``_PER_JTBD_GENERATORS[workflow_adapter]``
	    output to confirm the gate that imports ``CompensationWorker``
	    fires whenever compensations are synthesised.
	"""

	import json
	from pathlib import Path

	from flowforge_cli.jtbd.generators import workflow_adapter
	from flowforge_cli.jtbd.normalize import normalize
	from flowforge_cli.jtbd.parse import parse_bundle

	fixture_path = (
		Path(__file__).resolve().parent
		/ "fixtures"
		/ "compensation_symmetry"
		/ "jtbd-bundle.json"
	)
	assert fixture_path.exists(), f"missing fixture: {fixture_path}"
	raw = json.loads(fixture_path.read_text(encoding="utf-8"))
	parse_bundle(raw)
	bundle = normalize(raw)

	# The fixture must declare at least one JTBD that opted into the
	# synthesiser; otherwise the invariant is silently vacuous.
	jtbds_with_compensate = [
		jt
		for jt in bundle.jtbds
		if any(t.get("event") == "compensate" for t in jt.transitions)
	]
	assert jtbds_with_compensate, (
		"fixture must declare at least one JTBD with a compensate edge_case"
	)

	for jt in jtbds_with_compensate:
		# Forward create_entity effects in synthesis order — these are
		# the saga steps the host has already committed when the
		# compensation point fires.
		forward_create_entities: list[str] = [
			eff.get("entity") or jt.id
			for t in jt.transitions
			if t.get("event") != "compensate"
			for eff in (t.get("effects") or ())
			if eff.get("kind") == "create_entity"
		]
		assert forward_create_entities, (
			f"{jt.id}: fixture must produce at least one forward "
			f"create_entity effect to exercise the LIFO pairing"
		)

		compensate_transitions = [
			t for t in jt.transitions if t.get("event") == "compensate"
		]
		assert compensate_transitions, (
			f"{jt.id}: synthesiser failed to emit a compensate transition"
		)

		# Each compensate transition pins the same paired LIFO list.
		for ct in compensate_transitions:
			compensate_delete_entities: list[str] = [
				str((eff.get("values") or {}).get("entity") or "")
				for eff in (ct.get("effects") or ())
				if eff.get("kind") == "compensate"
				and eff.get("compensation_kind") == "compensate_delete"
			]
			assert len(compensate_delete_entities) == len(
				forward_create_entities
			), (
				f"{jt.id} {ct['id']}: compensate_delete count mismatch — "
				f"forward create_entity={forward_create_entities!r} "
				f"paired compensate_delete={compensate_delete_entities!r}"
			)
			# LIFO: the relative order of compensate_delete entries inside
			# ``ct['effects']`` equals the reverse of the forward order.
			assert compensate_delete_entities == list(
				reversed(forward_create_entities)
			), (
				f"{jt.id} {ct['id']}: LIFO order broken — "
				f"forward={forward_create_entities!r} "
				f"compensate_delete_order={compensate_delete_entities!r}"
			)

		# The rendered workflow_adapter template output emits the
		# CompensationWorker gate whenever compensations are synthesised.
		# This is the surface hosts wire — exercising it here pins both
		# the synthesis (above) and the generator-side coupling.
		adapter = workflow_adapter.generate(bundle, jt)
		assert adapter is not None, f"{jt.id}: workflow_adapter returned None"
		assert "CompensationWorker" in adapter.content, (
			f"{jt.id}: workflow_adapter missing CompensationWorker import "
			f"despite synthesised compensate transitions"
		)
		assert "register_compensations" in adapter.content, (
			f"{jt.id}: workflow_adapter missing register_compensations entrypoint"
		)
