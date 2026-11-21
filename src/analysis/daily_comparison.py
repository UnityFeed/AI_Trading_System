"""
Compare daily candles built from our hourly data with the daily candles
the exchange itself publishes.

Both sides must come from the same exchange: this checks that our hourly
data and our aggregation reproduce the exchange's own daily numbers. It
is not a comparison between exchanges.
"""

from dataclasses import dataclass
from datetime import datetime

from src.data_collection.market_data import MarketData


PRICE_FIELDS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class DayDifference:
    timestamp: datetime
    derived: MarketData
    reference: MarketData
    price_diff_pct: dict[str, float]  # per OHLC field, derived vs reference
    volume_diff_pct: float | None  # None when the reference volume is 0

    @property
    def max_price_diff_pct(self) -> float:
        return max(abs(value) for value in self.price_diff_pct.values())


@dataclass(frozen=True)
class DailyComparison:
    exchange: str
    matched: list[DayDifference]
    derived_only: list[datetime]
    reference_only: list[datetime]

    def days_above(self, threshold_pct: float) -> list[DayDifference]:
        return [
            day for day in self.matched
            if day.max_price_diff_pct > threshold_pct
        ]

    def worst_days(self, count: int) -> list[DayDifference]:
        return sorted(
            self.matched,
            key=lambda day: day.max_price_diff_pct,
            reverse=True,
        )[:count]


def _pct(derived_value: float, reference_value: float) -> float:
    return (derived_value / reference_value - 1.0) * 100.0


def compare_daily_candles(
    derived: list[MarketData],
    reference: list[MarketData],
) -> DailyComparison:

    exchanges = {candle.exchange.lower() for candle in derived + reference}

    if len(exchanges) > 1:
        raise ValueError(
            "Compare daily candles of one exchange at a time, found: "
            + ", ".join(sorted(exchanges))
        )

    exchange = exchanges.pop() if exchanges else ""

    derived_by_day = {candle.timestamp: candle for candle in derived}
    reference_by_day = {candle.timestamp: candle for candle in reference}

    if len(derived_by_day) != len(derived):
        raise ValueError("Duplicate days in derived candles.")

    if len(reference_by_day) != len(reference):
        raise ValueError("Duplicate days in reference candles.")

    matched = []

    for day in sorted(set(derived_by_day) & set(reference_by_day)):

        ours = derived_by_day[day]
        theirs = reference_by_day[day]

        price_diff = {
            field: _pct(getattr(ours, field), getattr(theirs, field))
            for field in PRICE_FIELDS
        }

        volume_diff = (
            _pct(ours.volume, theirs.volume) if theirs.volume > 0 else None
        )

        matched.append(
            DayDifference(
                timestamp=day,
                derived=ours,
                reference=theirs,
                price_diff_pct=price_diff,
                volume_diff_pct=volume_diff,
            )
        )

    return DailyComparison(
        exchange=exchange,
        matched=matched,
        derived_only=sorted(set(derived_by_day) - set(reference_by_day)),
        reference_only=sorted(set(reference_by_day) - set(derived_by_day)),
    )
