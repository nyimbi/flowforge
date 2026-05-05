"""Locale-aware money formatting via Babel.

The public entry-point is :func:`format_money`. It delegates to
``babel.numbers.format_currency``, which handles decimal separators,
grouping, symbol placement, and number of fraction digits per locale/currency.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal


def format_money(
	amount: Decimal,
	currency: str,
	locale: str = "en",
	*,
	currency_digits: bool = True,
	format_type: Literal["name", "standard", "accounting"] = "standard",
) -> str:
	"""Format *amount* as a locale-aware currency string.

	Args:
		amount:          The decimal amount to format.
		currency:        ISO-4217 currency code (e.g. ``"USD"``, ``"KES"``).
		locale:          BCP-47 locale tag (e.g. ``"en"``, ``"en_US"``,
		                 ``"sw_KE"``, ``"de_DE"``).
		currency_digits: When ``True`` (default), Babel uses the currency's
		                 standard decimal precision.  Set to ``False`` to
		                 suppress fractional digits.
		format_type:     Babel format type — ``"standard"`` (default) or
		                 ``"accounting"``.

	Returns:
		A formatted string such as ``"$1,234.56"`` or ``"KES 1,234.56"``.

	Raises:
		babel.core.UnknownLocaleError: if *locale* is not recognized by Babel.
		ValueError: if *currency* is not a valid ISO-4217 code.

	Example::

		>>> from decimal import Decimal
		>>> format_money(Decimal("1234.5"), "USD", "en_US")
		'$1,234.50'
		>>> format_money(Decimal("1234.5"), "EUR", "de_DE")
		'1.234,50\\xa0€'
	"""
	from babel.numbers import format_currency  # type: ignore[import-untyped]

	return format_currency(
		amount,
		currency.upper(),
		locale=locale,
		currency_digits=currency_digits,
		format_type=format_type,
	)
