# flowforge-money

Immutable `Money` value type, pluggable FX conversion, and locale-aware formatting for the flowforge framework.

Part of [flowforge](https://github.com/nyimbi/ums/tree/main/framework) — a portable workflow framework with audit-trail, multi-tenancy, and pluggable adapters.

## Install

```bash
uv pip install flowforge-money
# or
pip install flowforge-money
```

## What it does

`flowforge-money` provides the `Money` value type and the `flowforge.ports.MoneyPort` implementation used when workflow steps need currency arithmetic or FX conversion.

`Money` is immutable and stores amounts as `decimal.Decimal` quantised to 6 decimal places internally. Addition, subtraction, and multiplication keep `ROUND_HALF_UP`; division uses `ROUND_HALF_EVEN` (banker's rounding) throughout, matching the IFRS/GAAP rule for currency allocation. Same-currency arithmetic is enforced at the operator level — adding USD to EUR raises `ValueError` immediately.

`StaticMoneyPort` is the concrete `MoneyPort` implementation. It wraps any `RateProvider` and exposes `convert(amount, from_currency, to_currency, at)` returning `(converted_amount, rate_used)`. The rate snapshot is returned alongside the value so workflow replay can pin the exact converted amount without re-querying a live FX feed. `StaticRateProvider` ships as the default — fixed rates registered at construction time, suitable for tests and offline use.

`format_money` delegates to Babel for locale-aware formatting (decimal separators, grouping, symbol placement, fraction digits per locale and currency).

## Quick start

```python
from decimal import Decimal
from datetime import datetime, timezone
from flowforge_money import Money, StaticMoneyPort, StaticRateProvider
from flowforge_money import format_money

# Basic arithmetic.
price = Money(Decimal("99.99"), "USD")
tax = Money(Decimal("8.50"), "USD")
total = price + tax
display = total.rounded(2)  # Money('108.490000', 'USD') -> Money('108.49', 'USD')

# FX conversion via a static rate table.
rates = StaticRateProvider({"USD": {"KES": Decimal("130")}})
port = StaticMoneyPort(provider=rates)

converted, rate_used = await port.convert(
	Decimal("100.00"), "USD", "KES", datetime.now(timezone.utc)
)
# converted == Decimal('13000.000000'), rate_used == Decimal('130')

# Locale-aware formatting.
print(format_money(Decimal("1234.50"), "USD", "en_US"))  # '$1,234.50'
print(format_money(Decimal("1234.50"), "EUR", "de_DE"))  # '1.234,50\xa0€'
```

## Public API

- `Money(amount: Decimal, currency: str)` — immutable value type; `amount` must be `Decimal`, `currency` must be a 3-letter ISO-4217 code.
  - `.amount -> Decimal` — raw internal amount (6 decimal places).
  - `.currency -> str` — ISO-4217 code (uppercased).
  - `.rounded(places: int = 2) -> Money` — return a copy at the requested scale using banker's rounding.
  - Arithmetic: `+`, `-`, `*`, `/`, `-` (negation), `abs`; comparison: `==`, `<`, `<=`, `>`, `>=`.
  - Hashable; equality checks both amount and currency.
- `RateProvider` — runtime-checkable protocol: `get_rate(from_currency, to_currency, at) -> Decimal`.
- `StaticRateProvider(rates: dict[str, dict[str, Decimal]])` — fixed-rate provider; reverse rates derived automatically; same-currency always returns `Decimal("1")`.
  - `.register(from_currency, to_currency, rate)` — add or overwrite a pair at runtime.
- `StaticMoneyPort(provider: RateProvider | None)` — concrete `MoneyPort`.
  - `async convert(amount, from_currency, to_currency, at) -> tuple[Decimal, Decimal]` — returns `(converted, rate_used)`.
  - `async format(amount, currency, locale) -> str` — delegates to `format_money`.
- `format_money(amount, currency, locale, *, currency_digits, format_type) -> str` — Babel-backed locale formatting.

## Configuration

No environment variables. Pass a `RateProvider` to `StaticMoneyPort` at construction time. For live FX rates implement `RateProvider.get_rate` against your data source and pass the instance to `StaticMoneyPort(provider=your_provider)`.

Wire `StaticMoneyPort` into the engine via `flowforge.config`:

```python
from flowforge import config
from flowforge_money import StaticMoneyPort, StaticRateProvider
from decimal import Decimal

config.money = StaticMoneyPort(
	provider=StaticRateProvider({"USD": {"EUR": Decimal("0.92")}})
)
```

## Audit-2026 hardening

- **E-53 (M-01)** — Division and `rounded()` use `ROUND_HALF_EVEN` (banker's rounding), eliminating the systematic upward bias of `ROUND_HALF_UP` on tie cases. Matches IFRS/GAAP requirements for currency allocation and interest splits.
- **E-53 (M-02)** — `__hash__` and `__eq__` are consistent: two `Money` instances are equal if and only if both `amount` and `currency` match; `hash` is derived from the same pair. This satisfies the Python data model invariant that equal objects have equal hashes.
- **E-53 (M-03)** — `StaticRateProvider` derives reverse rates as `1 / forward_rate` when only the forward direction is registered, ensuring `get_rate("KES", "USD")` is consistent with `get_rate("USD", "KES")` without requiring both directions to be registered explicitly.

## Compatibility

- Python 3.11+
- Pydantic v2
- `babel` (for `format_money`)
- `flowforge` (core)

## License

Apache-2.0 — see `LICENSE`.

## See also

- [`flowforge`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-core) — ports, DSL, two-phase fire engine
- [`flowforge-fastapi`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-fastapi) — HTTP adapter; wire `config.money` before mounting routers
- [`flowforge-sqlalchemy`](https://github.com/nyimbi/ums/tree/main/framework/python/flowforge-sqlalchemy) — durable storage adapter
- [audit-fix-plan](https://github.com/nyimbi/ums/blob/main/framework/docs/audit-fix-plan.md) for the security hardening rationale
