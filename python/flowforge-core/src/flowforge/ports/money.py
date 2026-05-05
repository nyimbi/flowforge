"""MoneyPort — FX conversion + locale-aware formatting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class MoneyPort(Protocol):
	"""Currency operations.

	Conversions return ``(amount_converted, rate_used)`` so replays can
	pin the rate snapshot — same pattern as calendar snapshots, see
	portability §11 R11.
	"""

	async def convert(
		self,
		amount: Decimal,
		from_currency: str,
		to_currency: str,
		at: datetime,
	) -> tuple[Decimal, Decimal]:
		"""Convert *amount* from *from_currency* to *to_currency* at *at*."""

	async def format(self, amount: Decimal, currency: str, locale: str = "en") -> str:
		"""Locale-aware string formatting (Babel-compatible)."""
