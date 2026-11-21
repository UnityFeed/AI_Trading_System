"""
Chart data for the interactive chart: candles plus every indicator for
one timeframe, sent to the browser in chunks (newest first, older chunks
loaded while scrolling back).

All values come from the continuous history and the same indicator code
as the backtests, so the chart shows exactly what the strategy sees.
Candles that contain an hour filled in from another exchange are marked
(`filled`), so they can be drawn differently.
"""

from bisect import bisect_left
from dataclasses import dataclass

from src.analysis.primary_history import ContinuousHistory
from src.analysis.technical_indicators import calculate_indicators
from src.analysis.timeframes import aggregate_hourly_candles, period_start


INDICATORS = (
    "ema_20", "ema_50", "ema_200",
    "bb_upper", "bb_middle", "bb_lower",
    "rsi_14", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20",
)


@dataclass
class TimeframeSeries:
    timeframe: str
    times: list[int]  # unix seconds, candle start (UTC)
    rows: list[list]  # [time, open, high, low, close, volume, filled]
    indicators: dict[str, list]  # name -> values aligned with rows (None = not warmed up)


def build_series(history: ContinuousHistory, timeframe: str) -> TimeframeSeries:
    candles = aggregate_hourly_candles(history.candles, timeframe).candles
    rows = calculate_indicators(candles, timeframe)
    filled = history.periods_with_substitutes(timeframe)

    times = [int(c.timestamp.timestamp()) for c in candles]
    data = [
        [t, c.open, c.high, c.low, c.close, round(c.volume, 4), c.timestamp in filled]
        for t, c in zip(times, candles)
    ]
    indicators = {
        name: [
            None if row.values.get(name) is None else round(row.values[name], 4)
            for row in rows
        ]
        for name in INDICATORS
    }
    return TimeframeSeries(timeframe, times, data, indicators)


def chunk(series: TimeframeSeries, before: int | None, limit: int) -> dict:
    """The `limit` candles before `before` (or the newest ones), oldest first."""

    end = len(series.times) if before is None else bisect_left(series.times, before)
    start = max(0, end - limit)
    return {
        "timeframe": series.timeframe,
        "candles": series.rows[start:end],
        "indicators": {name: values[start:end] for name, values in series.indicators.items()},
        "has_more": start > 0,
    }


def trade_markers(fills, timeframe: str) -> list[dict]:
    """Paper-trade fills as chart markers on the candle that contains them."""

    return [
        {
            "time": int(period_start(fill.filled_at, timeframe).timestamp()),
            "side": fill.side,
            "price": round(fill.price, 2),
        }
        for fill in fills
    ]
