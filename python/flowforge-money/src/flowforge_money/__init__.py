"""flowforge-money — Money type, FX conversion, and locale-aware formatting.

Public API::

    from flowforge_money import Money, StaticMoneyPort, StaticRateProvider
    from flowforge_money.format import format_money
"""

from flowforge_money.format import format_money
from flowforge_money.static import Money, RateProvider, StaticMoneyPort, StaticRateProvider

__all__ = [
	"Money",
	"RateProvider",
	"StaticMoneyPort",
	"StaticRateProvider",
	"format_money",
]
