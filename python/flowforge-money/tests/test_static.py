"""Tests for Money, StaticRateProvider, and StaticMoneyPort."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from flowforge.ports import MoneyPort
from flowforge_money import Money, StaticMoneyPort, StaticRateProvider


NOW = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Money value type
# ---------------------------------------------------------------------------


def test_money_creation() -> None:
	m = Money(Decimal("100.00"), "USD")
	assert m.amount == Decimal("100.000000")
	assert m.currency == "USD"


def test_money_requires_decimal() -> None:
	with pytest.raises(TypeError):
		Money(100.0, "USD")  # type: ignore[arg-type]


def test_money_requires_three_letter_code() -> None:
	with pytest.raises(ValueError):
		Money(Decimal("1"), "US")
	with pytest.raises(ValueError):
		Money(Decimal("1"), "")


def test_money_currency_uppercased() -> None:
	m = Money(Decimal("1"), "usd")
	assert m.currency == "USD"


def test_money_addition() -> None:
	a = Money(Decimal("10.50"), "USD")
	b = Money(Decimal("4.50"), "USD")
	assert (a + b).amount == Decimal("15.000000")


def test_money_subtraction() -> None:
	a = Money(Decimal("20.00"), "USD")
	b = Money(Decimal("5.25"), "USD")
	result = a - b
	assert result.amount == Decimal("14.750000")


def test_money_addition_different_currency_raises() -> None:
	with pytest.raises(ValueError, match="different currencies"):
		Money(Decimal("10"), "USD") + Money(Decimal("10"), "EUR")


def test_money_multiply_by_decimal() -> None:
	m = Money(Decimal("10.00"), "USD")
	result = m * Decimal("3")
	assert result.amount == Decimal("30.000000")


def test_money_multiply_by_int() -> None:
	m = Money(Decimal("10.00"), "USD")
	assert (m * 4).amount == Decimal("40.000000")


def test_money_rmul() -> None:
	m = Money(Decimal("10.00"), "USD")
	assert (Decimal("2") * m).amount == Decimal("20.000000")


def test_money_multiply_by_float_raises() -> None:
	m = Money(Decimal("10.00"), "USD")
	with pytest.raises(TypeError):
		m * 1.5  # type: ignore[operator]


def test_money_division() -> None:
	m = Money(Decimal("30.00"), "USD")
	assert (m / Decimal("3")).amount == Decimal("10.000000")


def test_money_division_by_int() -> None:
	m = Money(Decimal("30.00"), "USD")
	assert (m / 2).amount == Decimal("15.000000")


def test_money_negation() -> None:
	m = Money(Decimal("5.00"), "USD")
	assert (-m).amount == Decimal("-5.000000")


def test_money_abs() -> None:
	m = Money(Decimal("-7.50"), "USD")
	assert abs(m).amount == Decimal("7.500000")


def test_money_comparison_eq() -> None:
	assert Money(Decimal("10"), "USD") == Money(Decimal("10"), "USD")
	assert Money(Decimal("10"), "USD") != Money(Decimal("10"), "EUR")
	assert Money(Decimal("10"), "USD") != Money(Decimal("11"), "USD")


def test_money_comparison_ordering() -> None:
	a = Money(Decimal("5"), "USD")
	b = Money(Decimal("10"), "USD")
	assert a < b
	assert a <= b
	assert b > a
	assert b >= a


def test_money_comparison_different_currency_raises() -> None:
	a = Money(Decimal("5"), "USD")
	b = Money(Decimal("5"), "EUR")
	with pytest.raises(ValueError):
		_ = a < b


def test_money_repr() -> None:
	m = Money(Decimal("12.5"), "USD")
	assert "12.500000" in repr(m)
	assert "USD" in repr(m)


def test_money_hash() -> None:
	m1 = Money(Decimal("10"), "USD")
	m2 = Money(Decimal("10"), "USD")
	assert hash(m1) == hash(m2)
	assert m1 in {m2}


def test_money_rounded() -> None:
	m = Money(Decimal("10.555"), "USD")
	r = m.rounded(2)
	assert r.amount == Decimal("10.56")
	assert r.currency == "USD"


# ---------------------------------------------------------------------------
# StaticRateProvider
# ---------------------------------------------------------------------------


def test_static_provider_direct_rate() -> None:
	p = StaticRateProvider({"USD": {"KES": Decimal("130")}})
	rate = p.get_rate("USD", "KES", NOW)
	assert rate == Decimal("130")


def test_static_provider_reverse_rate() -> None:
	p = StaticRateProvider({"USD": {"KES": Decimal("130")}})
	rate = p.get_rate("KES", "USD", NOW)
	assert rate == Decimal(1) / Decimal("130")


def test_static_provider_same_currency() -> None:
	p = StaticRateProvider()
	assert p.get_rate("USD", "USD", NOW) == Decimal("1")


def test_static_provider_missing_pair_raises() -> None:
	p = StaticRateProvider()
	with pytest.raises(ValueError, match="No rate registered"):
		p.get_rate("USD", "JPY", NOW)


def test_static_provider_register() -> None:
	p = StaticRateProvider()
	p.register("GBP", "EUR", Decimal("1.15"))
	assert p.get_rate("GBP", "EUR", NOW) == Decimal("1.15")


def test_static_provider_replay_determinism() -> None:
	"""Same (from, to, at) always yields the same rate — replay-safe."""
	p = StaticRateProvider({"USD": {"EUR": Decimal("0.92")}})
	t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
	t2 = datetime(2025, 6, 1, tzinfo=timezone.utc)
	assert p.get_rate("USD", "EUR", t1) == p.get_rate("USD", "EUR", t2)


def test_static_provider_case_insensitive() -> None:
	p = StaticRateProvider({"usd": {"kes": Decimal("130")}})
	assert p.get_rate("USD", "KES", NOW) == Decimal("130")
	assert p.get_rate("usd", "kes", NOW) == Decimal("130")


# ---------------------------------------------------------------------------
# StaticMoneyPort — satisfies MoneyPort protocol
# ---------------------------------------------------------------------------


def test_satisfies_money_port_protocol() -> None:
	port = StaticMoneyPort(StaticRateProvider({"USD": {"KES": Decimal("130")}}))
	assert isinstance(port, MoneyPort)


async def test_convert_returns_amount_and_rate() -> None:
	p = StaticRateProvider({"USD": {"KES": Decimal("130")}})
	port = StaticMoneyPort(p)
	converted, rate = await port.convert(Decimal("100"), "USD", "KES", NOW)
	assert rate == Decimal("130")
	assert converted == Decimal("13000.000000")


async def test_convert_same_currency() -> None:
	port = StaticMoneyPort()
	converted, rate = await port.convert(Decimal("50.25"), "USD", "USD", NOW)
	assert rate == Decimal("1")
	assert converted == Decimal("50.250000")


async def test_convert_replay_determinism() -> None:
	"""Same at-timestamp produces same result — required for workflow replay."""
	p = StaticRateProvider({"USD": {"EUR": Decimal("0.92")}})
	port = StaticMoneyPort(p)
	at = datetime(2024, 3, 1, tzinfo=timezone.utc)
	r1 = await port.convert(Decimal("200"), "USD", "EUR", at)
	r2 = await port.convert(Decimal("200"), "USD", "EUR", at)
	assert r1 == r2


async def test_convert_missing_rate_raises() -> None:
	port = StaticMoneyPort()
	with pytest.raises(ValueError):
		await port.convert(Decimal("10"), "USD", "JPY", NOW)


async def test_port_format_delegates_to_babel() -> None:
	port = StaticMoneyPort()
	result = await port.format(Decimal("1234.50"), "USD", "en_US")
	assert "$" in result
	assert "1,234" in result
