"""E-44 / IT-01 — Hypothesis property suite (5 properties).

Audit reference: framework/docs/audit-fix-plan.md §7 E-44, §9 R-5.

Properties shipped:

1. **Lockfile round-trip** — ``JtbdLockfile.canonical_body()`` is
   byte-stable across encode/decode and pin-order permutation.

2. **Audit hash-chain monotonicity** — concatenating canonical rows
   forms a strict-monotonic sha256 chain (sha[i] != sha[i-1] when row
   contents differ; the chain reproduces deterministically).

3. **Evaluator literal passthrough** — evaluating a JSON literal in
   the DSL returns the same literal value (no DSL-to-eval drift).

4. **Manifest signing-payload stability** — ``JtbdManifest.signing_payload()``
   is byte-identical across ``model_dump(mode='json') →
   model_validate(...)`` round-trips and across field-construction
   reordering (the hub re-parses manifests on the wire).

5. **Money arithmetic** — addition associative and commutative;
   hash/eq invariant; ``Money(a, c) + Money(b, c) == Money(b, c) + Money(a, c)``;
   ``a == b`` implies ``hash(a) == hash(b)``.

R-5 mitigation (CR-3): the suite runs with a tight deadline + bounded
``max_examples`` so latent-bug spikes are budget-bounded; if any
property fails on ``main`` the offending property is xfailed and the
finding goes back to the architect for in-scope/defer triage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import HealthCheck, given, settings, strategies as st


# ---------------------------------------------------------------------------
# Property 1 — Lockfile canonical body is permutation-stable
# ---------------------------------------------------------------------------


_id_strat = st.text(
	alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
	min_size=3,
	max_size=24,
).filter(lambda s: s[0].isalpha())

_semver_strat = st.tuples(
	st.integers(0, 9), st.integers(0, 99), st.integers(0, 99)
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}")

_sha_strat = st.binary(min_size=32, max_size=32).map(
	lambda b: "sha256:" + b.hex()
)


@st.composite
def _pin(draw) -> dict:
	return {
		"jtbd_id": draw(_id_strat),
		"version": draw(_semver_strat),
		"spec_hash": draw(_sha_strat),
		"source": draw(st.sampled_from(["local", "jtbd-hub", "git", "filesystem"])),
		"source_ref": draw(st.one_of(st.none(), st.text(min_size=0, max_size=24))),
	}


@st.composite
def _unique_pins(draw) -> list[dict]:
	pins = draw(st.lists(_pin(), min_size=1, max_size=8, unique_by=lambda p: p["jtbd_id"]))
	return pins


@settings(max_examples=80, deadline=2000, suppress_health_check=[HealthCheck.too_slow])
@given(pins=_unique_pins(), perm_seed=st.integers(0, 1_000_000))
def test_property_1_lockfile_canonical_body_permutation_stable(
	pins: list[dict], perm_seed: int
) -> None:
	"""Same pin set in any order → same canonical_body bytes + same body_hash."""
	from flowforge_jtbd.dsl.lockfile import JtbdLockfile

	# Construct a baseline + a permutation of the pins.
	import random

	rng = random.Random(perm_seed)
	pins_perm = list(pins)
	rng.shuffle(pins_perm)

	a = JtbdLockfile(
		composition_id="comp_1",
		project_package="org_example_pack",
		pins=pins,
	)
	b = JtbdLockfile(
		composition_id="comp_1",
		project_package="org_example_pack",
		pins=pins_perm,
	)
	# Canonical body is order-insensitive — pins are sorted in canonical_body().
	assert a.canonical_body() == b.canonical_body()
	# Therefore body_hash is identical.
	assert a.compute_body_hash() == b.compute_body_hash()


# ---------------------------------------------------------------------------
# Property 2 — Audit hash-chain monotonicity (deterministic + collision-resistant)
# ---------------------------------------------------------------------------


@st.composite
def _audit_row_dict(draw) -> dict:
	return {
		"tenant_id": draw(st.one_of(st.none(), _id_strat)),
		"actor_user_id": draw(st.one_of(st.none(), _id_strat)),
		"kind": draw(_id_strat),
		"subject_kind": draw(_id_strat),
		"subject_id": draw(_id_strat),
		"occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
		"payload": {"i": draw(st.integers(min_value=0, max_value=10_000))},
	}


@settings(max_examples=80, deadline=2000)
@given(rows=st.lists(_audit_row_dict(), min_size=2, max_size=10))
def test_property_2_audit_hash_chain_deterministic(rows: list[dict]) -> None:
	"""``compute_row_sha`` is deterministic; chain reconstructs identically twice."""
	from flowforge_audit_pg.hash_chain import compute_row_sha

	def _build(rs: list[dict]) -> list[str]:
		out: list[str] = []
		prev: str | None = None
		for r in rs:
			cur = compute_row_sha(prev, r)
			out.append(cur)
			prev = cur
		return out

	a = _build(rows)
	b = _build(rows)
	assert a == b
	# Strict-monotonic: row i depends on row i-1, so distinct rows must
	# emit distinct sha (collision is astronomically unlikely with sha256).
	assert len(set(a)) == len(a)


# ---------------------------------------------------------------------------
# Property 3 — Evaluator literal passthrough
# ---------------------------------------------------------------------------


_literal_strat = st.one_of(
	st.integers(-1_000, 1_000),
	st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
	st.text(max_size=24),
	st.booleans(),
	st.none(),
	st.lists(
		st.integers(-1_000, 1_000), min_size=0, max_size=4
	),  # already evaluated lists pass through
)


@settings(max_examples=200, deadline=1000)
@given(value=_literal_strat)
def test_property_3_evaluator_literal_passthrough(value) -> None:
	"""``evaluate(literal, ctx) == literal`` — DSL doesn't mutate plain values."""
	from flowforge.expr.evaluator import evaluate

	# Literals (non-dict, non-{var,...} shapes) pass through untouched.
	got = evaluate(value, {})
	# Floats can be exactly equal here because we don't go through any
	# arithmetic op — pure passthrough.
	assert got == value


# ---------------------------------------------------------------------------
# Property 4 — Manifest signing-payload stability across round-trip
# ---------------------------------------------------------------------------


@st.composite
def _manifest_kwargs(draw) -> dict:
	# Kwargs that yield a valid JtbdManifest; signature/key_id excluded
	# because they're stripped from signing_payload anyway.
	kwargs: dict = {
		"name": draw(_id_strat),
		"version": draw(_semver_strat),
	}
	if draw(st.booleans()):
		kwargs["description"] = draw(st.text(max_size=64))
	if draw(st.booleans()):
		kwargs["author"] = draw(st.text(max_size=32))
	if draw(st.booleans()):
		kwargs["spec_hash"] = draw(_sha_strat)
	if draw(st.booleans()):
		kwargs["bundle_hash"] = draw(_sha_strat)
	if draw(st.booleans()):
		kwargs["published_at"] = datetime(
			draw(st.integers(2020, 2030)),
			draw(st.integers(1, 12)),
			draw(st.integers(1, 28)),
			tzinfo=timezone.utc,
		)
	if draw(st.booleans()):
		kwargs["tags"] = draw(
			st.lists(st.text(max_size=8), min_size=0, max_size=4, unique=True)
		)
	return kwargs


@settings(max_examples=80, deadline=2000)
@given(kwargs=_manifest_kwargs())
def test_property_4_manifest_signing_payload_round_trip_stable(kwargs: dict) -> None:
	"""``signing_payload()`` is byte-identical across model_dump→model_validate."""
	from flowforge_jtbd.registry.manifest import JtbdManifest

	a = JtbdManifest(**kwargs)
	# JSON round-trip: dump to plain JSON, parse, reconstruct.
	dumped = a.model_dump(mode="json")
	b = JtbdManifest.model_validate(dumped)
	assert a.signing_payload() == b.signing_payload()

	# Field-construction reordering: build kwargs in another order.
	reordered = dict(reversed(list(kwargs.items())))
	c = JtbdManifest(**reordered)
	assert a.signing_payload() == c.signing_payload()

	# Adding signature/key_id MUST NOT change the signing payload.
	signed = a.with_signature("base64-fake==", "hmac-v1")
	assert a.signing_payload() == signed.signing_payload()


# ---------------------------------------------------------------------------
# Property 5 — Money arithmetic invariants
# ---------------------------------------------------------------------------


_currency_strat = st.sampled_from(["USD", "EUR", "GBP", "KES", "JPY"])

_amount_strat = st.decimals(
	min_value=Decimal("-1000000"),
	max_value=Decimal("1000000"),
	allow_nan=False,
	allow_infinity=False,
	places=4,
)


@settings(max_examples=200, deadline=1000)
@given(a=_amount_strat, b=_amount_strat, c=_amount_strat, ccy=_currency_strat)
def test_property_5_money_addition_associative_commutative(
	a: Decimal, b: Decimal, c: Decimal, ccy: str
) -> None:
	from flowforge_money.static import Money

	x = Money(a, ccy)
	y = Money(b, ccy)
	z = Money(c, ccy)
	# Associativity: (x + y) + z == x + (y + z)
	assert (x + y) + z == x + (y + z)
	# Commutativity: x + y == y + x
	assert x + y == y + x


@settings(max_examples=200, deadline=1000)
@given(a=_amount_strat, b=_amount_strat, ccy=_currency_strat)
def test_property_5_money_hash_eq_invariant(
	a: Decimal, b: Decimal, ccy: str
) -> None:
	"""``a == b`` ⇒ ``hash(a) == hash(b)`` (Money instance equality)."""
	from flowforge_money.static import Money

	x = Money(a, ccy)
	# Construct a separate equal-valued Money — distinct instance.
	y = Money(Decimal(str(a)), ccy)
	assert x == y
	assert hash(x) == hash(y)
	# Inequality is hash-permitted-collision but should usually differ:
	if a != b:
		# Money(a) and Money(b) compare unequal; same currency.
		alt = Money(b, ccy)
		assert (x == alt) == (a == b)
