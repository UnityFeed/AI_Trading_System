"""
Everything a backtest needs for one timeframe, prepared once:
candles, indicator rows, and on which candles an order may be filled.

Fills happen at the OPEN of a candle. An open is only tradeable when the
primary exchange really traded at that moment:
- not when the candle's first hour was filled in from another exchange
  (the primary exchange was down), and
- not at the first primary-exchange hour after such a stretch, because
  Kraken's first trade after maintenance prints at a stale price.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.analysis.primary_history import ContinuousHistory
from src.analysis.technical_indicators import (
    IndicatorRow,
    IndicatorSettings,
    IndicatorTable,
    indicator_table,
)
from src.analysis.timeframes import TIMEFRAME_HOURS
from src.data_collection.market_data import MarketData


@dataclass(frozen=True)
class Market:
    timeframe: str
    candles: list[MarketData]
    rows: list[IndicatorRow]
    tradeable: list[bool]  # may an order fill at candles[i].open?
    consecutive: list[bool]  # is candles[i] exactly one period after candles[i-1]?

    def index_range(self, start: datetime, end: datetime) -> range:
        """Indexes of candles with start <= timestamp < end."""
        first = next(
            (i for i, c in enumerate(self.candles) if c.timestamp >= start),
            len(self.candles),
        )
        last = next(
            (i for i, c in enumerate(self.candles) if c.timestamp >= end),
            len(self.candles),
        )
        return range(first, last)


def untradeable_hours(history: ContinuousHistory) -> set[datetime]:
    """Hours whose open must not be used for a fill."""

    blocked = set(history.substituted_hours())

    for change in history.source_changes:
        came_back = (
            history.sources[change.timestamp]
            == history.primary_by_hour[change.timestamp]
        )
        previous_was_filled = (
            change.timestamp - timedelta(hours=1)
        ) in blocked

        if came_back and previous_was_filled:
            blocked.add(change.timestamp)

    return blocked


def build_market(
    history: ContinuousHistory,
    timeframe: str,
    settings: IndicatorSettings = IndicatorSettings(),
    table: IndicatorTable | None = None,
) -> Market:
    """`table` (from indicator_table) skips recomputing the indicators."""

    candles, rows = table or indicator_table(history.candles, timeframe, settings)
    blocked = untradeable_hours(history)
    step = timedelta(hours=TIMEFRAME_HOURS[timeframe])

    # A candle's open is the open of its first hour.
    tradeable = [candle.timestamp not in blocked for candle in candles]
    consecutive = [False] + [
        b.timestamp - a.timestamp == step for a, b in zip(candles, candles[1:])
    ]

    return Market(timeframe, candles, rows, tradeable, consecutive)
