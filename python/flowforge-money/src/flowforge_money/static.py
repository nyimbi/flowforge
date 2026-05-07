"""StaticRateProvider — fixed-rate FX provider for tests and offline use.

Also contains ``Money``, the core value type, and ``StaticMoneyPort``,
a concrete :class:`flowforge.ports.MoneyPort` implementation backed by a
pluggable :class:`RateProvider`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Rate provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class RateProvider(Protocol):
	"""Pluggable FX rate source.

	Implementations must be deterministic for the same ``(from_currency,
	to_currency, at)`` triple so workflow replays always compute the same
	converted amount.
	"""

	def get_rate(
		self,
		from_currency: str,
		to_currency: str,
		at: datetime,
	) -> Decimal:
		"""Return the exchange rate for *from_currency* → *to_currency* at *at*.

		Raise :class:`ValueError` if the pair is not supported.
		"""
		...


# ---------------------------------------------------------------------------
# Money value type
# ---------------------------------------------------------------------------


class Money:
	"""Immutable money value with an ISO-4217 currency code.

	Arithmetic uses :class:`decimal.Decimal` throughout; floats are never
	used internally. Internal storage is quantised to ``_PREC`` (6 decimal
	places) so multiplication / FX conversion don't lose sub-cent precision
	mid-pipeline; call :meth:`rounded` to clip to a desired display scale.

	Examples::

		>>> from decimal import Decimal
		>>> m = Money(Decimal("12.50"), "USD")
		>>> m + Money(Decimal("7.50"), "USD")
		Money('20.000000', 'USD')
		>>> m * Decimal("2")
		Money('25.000000', 'USD')
		>>> m.currency
		'USD'
	"""

	# Precision for intermediate arithmetic (6 decimal places — sub-cent
	# precision survives FX conversion + rounding pipelines).
	_PREC = Decimal("0.000001")

	# E-53 / M-01: SOX/IFRS-compliant banker's rounding for division.
	#
	# Banker's rounding (ROUND_HALF_EVEN) avoids the systematic upward bias
	# of ROUND_HALF_UP on tie cases. Over a population of fractional
	# allocations (interest, FX residuals, tax splits) banker's rounding
	# is unbiased: ties to .5 round to the nearest even neighbour, so
	# ~half round up and ~half round down. This is the rule mandated by
	# IEEE 754 for binary floats and is the default in IFRS / GAAP
	# accounting standards for currency division.
	#
	# Addition / subtraction / multiplication don't introduce new
	# fractional residue at the _PREC boundary, so they keep
	# ROUND_HALF_UP (which agrees with HALF_EVEN on every non-tie case).
	# Division is the one operator where the choice is observable.
	_DIV_ROUNDING = ROUND_HALF_EVEN

	def __init__(self, amount: Decimal, currency: str) -> None:
		if not isinstance(amount, Decimal):
			raise TypeError(f"amount must be Decimal, got {type(amount).__name__}")
		if not currency or len(currency) != 3:
			raise ValueError(f"currency must be a 3-letter ISO-4217 code, got {currency!r}")
		self._amount = amount.quantize(self._PREC, rounding=ROUND_HALF_UP)
		self._currency = currency.upper()

	@property
	def amount(self) -> Decimal:
		"""Raw decimal amount."""
		return self._amount

	@property
	def currency(self) -> str:
		"""ISO-4217 currency code (uppercased)."""
		return self._currency

	# ------------------------------------------------------------------ ops

	def _check_same_currency(self, other: "Money") -> None:
		if self._currency != other._currency:
			raise ValueError(
				f"Cannot operate on different currencies: {self._currency} vs {other._currency}"
			)

	def __add__(self, other: "Money") -> "Money":
		self._check_same_currency(other)
		return Money(self._amount + other._amount, self._currency)

	def __sub__(self, other: "Money") -> "Money":
		self._check_same_currency(other)
		return Money(self._amount - other._amount, self._currency)

	def __mul__(self, factor: Decimal | int) -> "Money":
		if isinstance(factor, int):
			factor = Decimal(factor)
		if not isinstance(factor, Decimal):
			raise TypeError(f"factor must be Decimal or int, got {type(factor).__name__}")
		return Money(self._amount * factor, self._currency)

	def __rmul__(self, factor: Decimal | int) -> "Money":
		return self.__mul__(factor)

	def __truediv__(self, divisor: Decimal | int) -> "Money":
		"""Divide *self* by *divisor*, returning a new :class:`Money`.

		E-53 / M-01: the division result is explicitly quantised with
		:attr:`_DIV_ROUNDING` (``ROUND_HALF_EVEN`` — banker's rounding)
		before the new Money is constructed, so a tie at the
		``_PREC`` boundary rounds to the nearest even neighbour rather
		than up. This avoids the cumulative upward bias that
		``ROUND_HALF_UP`` would introduce across many allocations and is
		the rule mandated by IFRS / GAAP for currency division.
		"""

		if isinstance(divisor, int):
			divisor = Decimal(divisor)
		if not isinstance(divisor, Decimal):
			raise TypeError(f"divisor must be Decimal or int, got {type(divisor).__name__}")
		# Pre-quantise with banker's rounding so the result lands on a
		# _PREC boundary unambiguously; Money.__init__ then re-quantises
		# (a no-op at this point) without changing the value.
		raw = self._amount / divisor
		quantised = raw.quantize(self._PREC, rounding=self._DIV_ROUNDING)
		return Money(quantised, self._currency)

	def __neg__(self) -> "Money":
		return Money(-self._amount, self._currency)

	def __abs__(self) -> "Money":
		return Money(abs(self._amount), self._currency)

	def __eq__(self, other: object) -> bool:
		if not isinstance(other, Money):
			return NotImplemented
		return self._currency == other._currency and self._amount == other._amount

	def __lt__(self, other: "Money") -> bool:
		self._check_same_currency(other)
		return self._amount < other._amount

	def __le__(self, other: "Money") -> bool:
		self._check_same_currency(other)
		return self._amount <= other._amount

	def __gt__(self, other: "Money") -> bool:
		self._check_same_currency(other)
		return self._amount > other._amount

	def __ge__(self, other: "Money") -> bool:
		self._check_same_currency(other)
		return self._amount >= other._amount

	def __repr__(self) -> str:
		return f"Money({str(self._amount)!r}, {self._currency!r})"

	def __hash__(self) -> int:
		return hash((self._amount, self._currency))

	@classmethod
	def _from_quantised(cls, amount: Decimal, currency: str) -> "Money":
		"""Internal constructor that bypasses :meth:`__init__`'s
		``_PREC`` re-quantise.

		E-53 / M-01 follow-up (worker-eng-4 caught during E-65 doctest
		review): the public constructor unconditionally quantises every
		input back to ``_PREC`` (6 decimals), so ``.rounded(n)`` was a
		no-op for display purposes. This factory builds Money with the
		amount already at the caller's intended scale and skips the
		re-quantise.

		Callers MUST quantise the input before calling this. The factory
		does not validate the scale; it trusts the caller.
		"""

		obj = cls.__new__(cls)
		object.__setattr__(obj, "_amount", amount)
		object.__setattr__(obj, "_currency", currency.upper())
		return obj

	def rounded(self, places: int = 2) -> "Money":
		"""Return a copy quantised to *places* decimal places.

		E-53 / M-01: the rounding mode is :attr:`_DIV_ROUNDING` (banker's
		rounding) so display-side narrowing matches the SOX/IFRS rule
		applied by division. The result's Decimal exponent is exactly
		``-places`` — the public constructor's ``_PREC`` re-quantise is
		bypassed via :meth:`_from_quantised` so a request for 2-decimal
		display does not silently re-expand to 6.
		"""

		assert places >= 0, f"places must be non-negative, got {places}"
		quant = Decimal(10) ** -places
		quantised = self._amount.quantize(quant, rounding=self._DIV_ROUNDING)
		return type(self)._from_quantised(quantised, self._currency)


# ---------------------------------------------------------------------------
# Static / fixed-rate provider (for tests and offline use)
# ---------------------------------------------------------------------------


class StaticRateProvider:
	"""Fixed-rate FX provider — same rate regardless of timestamp.

	Rates are stored as ``{(from, to): rate}``; reverse rates are
	derived automatically (1/rate) unless explicitly registered.

	Replay-deterministic: identical ``(from, to, at)`` always yields the
	same :class:`~decimal.Decimal`.

	Example::

		>>> from decimal import Decimal
		>>> from datetime import datetime, timezone
		>>> p = StaticRateProvider({"USD": {"KES": Decimal("130")}})
		>>> p.get_rate("USD", "KES", datetime.now(timezone.utc))
		Decimal('130')
	"""

	def __init__(self, rates: dict[str, dict[str, Decimal]] | None = None) -> None:
		self._rates: dict[tuple[str, str], Decimal] = {}
		for from_ccy, targets in (rates or {}).items():
			for to_ccy, rate in targets.items():
				self._rates[(from_ccy.upper(), to_ccy.upper())] = rate

	def register(self, from_currency: str, to_currency: str, rate: Decimal) -> None:
		"""Register or overwrite a rate pair."""
		self._rates[(from_currency.upper(), to_currency.upper())] = rate

	def get_rate(
		self,
		from_currency: str,
		to_currency: str,
		at: datetime,
	) -> Decimal:
		"""Return the stored rate; ``at`` is intentionally ignored (fixed rates)."""
		key = (from_currency.upper(), to_currency.upper())
		if key in self._rates:
			return self._rates[key]
		# Try reverse
		rev = (to_currency.upper(), from_currency.upper())
		if rev in self._rates:
			return Decimal("1") / self._rates[rev]
		# Same-currency passthrough
		if from_currency.upper() == to_currency.upper():
			return Decimal("1")
		raise ValueError(
			f"No rate registered for {from_currency} -> {to_currency}"
		)


# ---------------------------------------------------------------------------
# MoneyPort implementation
# ---------------------------------------------------------------------------


class StaticMoneyPort:
	"""Concrete :class:`flowforge.ports.MoneyPort` backed by a :class:`RateProvider`.

	Conversion returns ``(converted_amount, rate_used)`` so the rate snapshot
	can be stored alongside the workflow token for replay determinism.

	Args:
		provider: Any object satisfying the :class:`RateProvider` protocol.
		          Defaults to a :class:`StaticRateProvider` with no rates
		          (only same-currency conversions will succeed).
	"""

	def __init__(self, provider: RateProvider | None = None) -> None:
		self._provider: RateProvider = provider or StaticRateProvider()

	async def convert(
		self,
		amount: Decimal,
		from_currency: str,
		to_currency: str,
		at: datetime,
	) -> tuple[Decimal, Decimal]:
		"""Convert *amount* and return ``(converted, rate_used)``.

		The rate snapshot is included so replays can pin the value exactly.
		"""
		rate = self._provider.get_rate(from_currency, to_currency, at)
		converted = (amount * rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
		return converted, rate

	async def format(self, amount: Decimal, currency: str, locale: str = "en") -> str:
		"""Delegate to :func:`flowforge_money.format.format_money`."""
		from flowforge_money.format import format_money

		return format_money(amount, currency, locale)
