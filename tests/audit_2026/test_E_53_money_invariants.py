"""E-53 — money rounding + reverse-rate + hash/eq invariants.

Audit findings (audit-fix-plan §4.3 M-01, M-02, M-03; §7 E-53):
- M-01 (P2): division uses explicit rounding mode; SOX-compliant banker's
  rounding (ROUND_HALF_EVEN) documented.
- M-02 (P2): hash/eq invariant — `a == b` implies `hash(a) == hash(b)`;
  property test ≥1000 cases.
- M-03 (P2): reverse-rate round-trip consistency —
  ``convert(convert(m, A→B), B→A) ≈ m`` within Decimal-precision tolerance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN

import pytest


# ---------------------------------------------------------------------------
# M-01 — banker's rounding on division
# ---------------------------------------------------------------------------


def test_M_01_truediv_banker_rounding_documented() -> None:
	"""Money exposes a class-level rounding mode for division and it is
	`ROUND_HALF_EVEN` (SOX-compliant banker's rounding)."""

	from flowforge_money.static import Money

	# E-53 / M-01: explicit rounding mode is part of the public contract.
	assert hasattr(Money, "_DIV_ROUNDING")
	assert Money._DIV_ROUNDING is ROUND_HALF_EVEN


def test_M_01_rounded_actually_quantises_to_requested_places() -> None:
	"""``.rounded(n)`` returns a Money whose Decimal exponent matches the
	requested places — the constructor re-quantise to ``_PREC`` must NOT
	fight the explicit narrowing.

	Pre-fix bug (worker-eng-4 caught during E-65 doctest review):
	``Money(Decimal('1.23')).rounded(2)`` returned a 6-decimal Money
	because the Money constructor itself re-quantises every input back
	to ``_PREC = 0.000001``. ``.rounded()`` was effectively a no-op for
	display.

	Acceptance: for every common display scale (0, 2, 4) and a few
	currencies (USD/JPY/BHD), ``.rounded(n)._amount.as_tuple().exponent
	== -n``.
	"""

	from flowforge_money.static import Money

	cases = [
		(Decimal("1.23456789"), "USD", 2, Decimal("1.23")),
		(Decimal("1.23456789"), "USD", 4, Decimal("1.2346")),
		(Decimal("1.5"), "JPY", 0, Decimal("2")),  # JPY has 0-decimal display
		(Decimal("1.4999999"), "BHD", 3, Decimal("1.500")),  # BHD has 3-decimal display
		(Decimal("1000000.12345"), "USD", 2, Decimal("1000000.12")),
	]
	for amount, ccy, places, expected in cases:
		m = Money(amount, ccy)
		r = m.rounded(places)
		# Display scale is exactly the requested places.
		assert r.amount.as_tuple().exponent == -places, (
			f".rounded({places}) on {amount} {ccy} produced exponent "
			f"{r.amount.as_tuple().exponent} not {-places}"
		)
		# Numerical value matches the expected quantisation.
		assert r.amount == expected, (
			f"rounded({places}) on {amount} {ccy}: expected {expected}, got {r.amount}"
		)


def test_M_01_rounded_preserves_currency() -> None:
	"""``.rounded()`` preserves the currency attribute."""

	from flowforge_money.static import Money

	m = Money(Decimal("1.23456"), "EUR")
	r = m.rounded(2)
	assert r.currency == "EUR"


def test_M_01_rounded_is_idempotent() -> None:
	"""``m.rounded(n).rounded(n) == m.rounded(n)`` (idempotent)."""

	from flowforge_money.static import Money

	m = Money(Decimal("1.23456789"), "USD")
	once = m.rounded(2)
	twice = once.rounded(2)
	assert once == twice
	assert once.amount.as_tuple().exponent == -2
	assert twice.amount.as_tuple().exponent == -2


def test_M_01_truediv_uses_banker_rounding_at_quantise_boundary() -> None:
	"""Division produces a 0.5-ULP tie that resolves to the even
	neighbour (banker's rounding), not to nearest away (HALF_UP).

	Constructor pre-quantises with HALF_UP, so to exercise the division
	rounding mode we need amounts that *divide* into a tie at _PREC.
	"""

	from flowforge_money.static import Money

	# 0.000001 / 2 = 0.0000005 → tie. HALF_EVEN → 0 (even neighbour).
	# HALF_UP would give 0.000001.
	m = Money(Decimal("0.000001"), "USD")
	q = m / Decimal("2")
	assert q.amount == Decimal("0.000000"), f"expected banker's rounding to 0, got {q.amount}"

	# 0.000003 / 2 = 0.0000015 → tie. HALF_EVEN → 0.000002 (even ULP).
	# HALF_UP would give 0.000002 too in this case (next even is up).
	m2 = Money(Decimal("0.000003"), "USD")
	q2 = m2 / Decimal("2")
	assert q2.amount == Decimal("0.000002")

	# 0.000005 / 2 = 0.0000025 → tie. HALF_EVEN → 0.000002 (even
	# neighbour is below). HALF_UP would give 0.000003. This is the
	# distinguishing case that locks in HALF_EVEN.
	m3 = Money(Decimal("0.000005"), "USD")
	q3 = m3 / Decimal("2")
	assert q3.amount == Decimal("0.000002"), f"expected banker's rounding to 0.000002, got {q3.amount}"


# ---------------------------------------------------------------------------
# M-02 — hash/eq invariant (1000-case property test)
# ---------------------------------------------------------------------------


def test_M_02_hash_eq_invariant_1000_cases() -> None:
	"""For any pair of Money objects: a == b ⇒ hash(a) == hash(b).

	1000 randomly-generated pairs.
	"""

	import random

	from flowforge_money.static import Money

	rng = random.Random(0xE53)  # deterministic seed
	currencies = ("USD", "EUR", "GBP", "KES", "JPY", "ZAR")

	violations: list[tuple[Money, Money]] = []
	for _ in range(1000):
		# Build two Money objects that *could* be equal: same currency,
		# amounts that are mathematically equal under quantisation.
		ccy = rng.choice(currencies)
		whole = rng.randint(-1_000_000, 1_000_000)
		# Trailing-zero variants of the same amount must hash identically.
		a = Money(Decimal(f"{whole}.0"), ccy)
		b = Money(Decimal(f"{whole}.000000"), ccy)
		if a == b and hash(a) != hash(b):
			violations.append((a, b))
		# Different-currency pair: must NOT compare equal.
		other_ccy = rng.choice([c for c in currencies if c != ccy])
		c = Money(Decimal(f"{whole}.0"), other_ccy)
		assert a != c

	assert violations == [], f"hash/eq invariant broken on {len(violations)} pairs"


def test_M_02_hash_stable_across_construction_paths() -> None:
	"""Money built via different but equal Decimal literals must hash identically."""

	from flowforge_money.static import Money

	a = Money(Decimal("1"), "USD")
	b = Money(Decimal("1.0"), "USD")
	c = Money(Decimal("1.000000"), "USD")
	d = Money(Decimal("1E0"), "USD")

	assert a == b == c == d
	assert hash(a) == hash(b) == hash(c) == hash(d)


def test_M_02_hash_distinct_for_different_currencies() -> None:
	"""Different currency, same amount → not equal, ideally distinct hash
	(guard the not-equal case; hash collisions are technically allowed
	but a weak hash is a smell)."""

	from flowforge_money.static import Money

	a = Money(Decimal("1.0"), "USD")
	b = Money(Decimal("1.0"), "EUR")
	assert a != b


# ---------------------------------------------------------------------------
# M-03 — reverse-rate round-trip
# ---------------------------------------------------------------------------


def test_M_03_reverse_rate_round_trip_within_tolerance() -> None:
	"""``convert(convert(m, A→B), B→A) ≈ m`` within tolerance derived
	from Decimal precision."""

	from flowforge_money.static import StaticMoneyPort, StaticRateProvider

	rates = {
		"USD": {
			"EUR": Decimal("0.92"),
			"GBP": Decimal("0.79"),
			"KES": Decimal("130"),
			"JPY": Decimal("149.5"),
		}
	}
	port = StaticMoneyPort(StaticRateProvider(rates))
	now = datetime.now(timezone.utc)

	async def _go() -> None:
		amounts = [
			Decimal("1"),
			Decimal("100"),
			Decimal("12345.6789"),
			Decimal("0.01"),
			Decimal("1000000"),
		]
		pairs = [("USD", "EUR"), ("USD", "GBP"), ("USD", "KES"), ("USD", "JPY")]

		# Tolerance: 1 ULP at the quantise scale, scaled by the magnitude
		# of the FX rate (the larger the rate, the more rounding
		# accumulates on the back-trip).
		base_ulp = Decimal("0.000001")

		for amt in amounts:
			for a, b in pairs:
				converted_b, rate_ab = await port.convert(amt, a, b, now)
				converted_back, rate_ba = await port.convert(converted_b, b, a, now)
				# Magnitude-aware tolerance; large round trips lose ~rate ULPs.
				tol = base_ulp * (abs(rate_ab) + abs(rate_ba)) * 2
				assert abs(converted_back - amt) <= max(tol, base_ulp), (
					f"reverse-rate inconsistent: {amt} {a} → {b} → {a} = {converted_back} "
					f"(rates {rate_ab}, {rate_ba}, tol={tol})"
				)

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_go())
	finally:
		loop.close()


def test_M_03_explicit_reverse_rate_overrides_derived() -> None:
	"""When both A→B and B→A are explicitly registered, both are used
	and round-trip consistency is exact for amounts representable in
	0.000001 precision."""

	from flowforge_money.static import StaticMoneyPort, StaticRateProvider

	provider = StaticRateProvider(
		{"USD": {"EUR": Decimal("0.5")}, "EUR": {"USD": Decimal("2")}}
	)
	port = StaticMoneyPort(provider)
	now = datetime.now(timezone.utc)

	async def _go() -> None:
		amount = Decimal("100")
		converted, _ = await port.convert(amount, "USD", "EUR", now)
		assert converted == Decimal("50.000000")
		back, _ = await port.convert(converted, "EUR", "USD", now)
		# 50 * 2 = 100; quantised to 0.000001.
		assert back == Decimal("100.000000")

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_go())
	finally:
		loop.close()


def test_M_03_same_currency_passthrough_is_exact() -> None:
	"""Same-currency conversion uses rate=1 and is exact."""

	from flowforge_money.static import StaticMoneyPort, StaticRateProvider

	port = StaticMoneyPort(StaticRateProvider({}))
	now = datetime.now(timezone.utc)

	async def _go() -> None:
		amt = Decimal("12345.6789")
		converted, rate = await port.convert(amt, "USD", "USD", now)
		assert rate == Decimal("1")
		# Quantised to 6dp.
		assert converted == amt.quantize(Decimal("0.000001"))

	loop = asyncio.new_event_loop()
	try:
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_go())
	finally:
		loop.close()
