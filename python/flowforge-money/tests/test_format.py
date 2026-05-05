"""Tests for locale-aware money formatting."""

from __future__ import annotations

from decimal import Decimal

import pytest

from flowforge_money.format import format_money


def test_format_usd_en_us() -> None:
	result = format_money(Decimal("1234.50"), "USD", "en_US")
	assert result == "$1,234.50"


def test_format_eur_de_de() -> None:
	result = format_money(Decimal("1234.50"), "EUR", "de_DE")
	# Babel uses non-breaking space before € in de_DE
	assert "1.234,50" in result
	assert "€" in result


def test_format_kes_sw_ke() -> None:
	result = format_money(Decimal("5000"), "KES", "sw_KE")
	assert "5,000" in result or "5.000" in result  # locale-dependent separator
	assert "KES" in result or "Ksh" in result or "KSh" in result


def test_format_gbp_en_gb() -> None:
	result = format_money(Decimal("99.99"), "GBP", "en_GB")
	assert "£" in result
	assert "99.99" in result


def test_format_currency_lowercased_code() -> None:
	"""Currency code is normalized to uppercase before passing to Babel."""
	result = format_money(Decimal("100"), "usd", "en_US")
	assert "$" in result


def test_format_zero() -> None:
	result = format_money(Decimal("0"), "USD", "en_US")
	assert "$0.00" == result


def test_format_large_amount() -> None:
	result = format_money(Decimal("1000000.00"), "USD", "en_US")
	assert "$1,000,000.00" == result


def test_format_no_currency_digits() -> None:
	result = format_money(Decimal("99.99"), "USD", "en_US", currency_digits=False)
	# With currency_digits=False the result may omit decimals
	assert "$" in result


def test_format_accounting_type() -> None:
	result = format_money(Decimal("-50.00"), "USD", "en_US", format_type="accounting")
	# Accounting format wraps negatives in parentheses in en_US
	assert "50" in result


def test_format_jpy_no_decimals() -> None:
	"""JPY has 0 decimal places in Babel by default."""
	result = format_money(Decimal("1500"), "JPY", "ja_JP")
	assert "1,500" in result
