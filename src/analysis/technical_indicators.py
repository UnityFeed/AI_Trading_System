"""
Technical indicators for any timeframe (1h, 4h, 1d).

How gaps and look-ahead are handled:
- Candles are first split into runs of consecutive periods
  (split_into_runs). Every indicator starts from scratch at the start of
  each run, so no value is ever calculated across a missing period, and
  nothing is carried over between exchanges.
- A value at time T only uses candles up to and including T. The candle
  at T is complete (its period has closed), so the value is known at the
  END of period T. Anything acting on it (a signal, a backtest fill) must
  happen in a later period.
- Until an indicator has seen enough candles in the current run its value
  is None ("not warmed up yet"), never a guess.

Definitions (the usual textbook ones):
- SMA(n): average of the last n closes.
- EMA(n): starts as the SMA of the first n closes, then
  EMA = previous EMA + k * (close - previous EMA), with k = 2 / (n + 1).
- RSI(n), Wilder: the first average gain/loss is the simple average of the
  first n close-to-close changes; after that
  average = (previous average * (n - 1) + current) / n.
  RSI = 100 - 100 / (1 + average gain / average loss); 100 when there were
  no losses, 50 when there was no movement at all.
- MACD(12, 26, 9): MACD line = EMA(12) - EMA(26); signal = EMA(9) of the
  MACD line; histogram = MACD line - signal.
- Bollinger(20, 2): middle = SMA(20); upper/lower = middle +/- 2 x the
  population standard deviation of the same 20 closes;
  width = (upper - lower) / middle.
- ATR(n), Wilder: true range = max(high - low, |high - previous close|,
  |low - previous close|) (high - low for the first candle of a run);
  the first ATR is the average of the first n true ranges, then
  ATR = (previous ATR * (n - 1) + true range) / n.
- Volume: volume SMA(n) of the last n volumes including the current one;
  relative volume = current volume / average volume of the n candles
  BEFORE it (so a spike is not diluted by itself).
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from src.analysis.timeframes import aggregate_hourly_candles, split_into_runs
from src.data_collection.market_data import MarketData


Series = list[float | None]


# ---------------------------------------------------------------------------
# Building blocks. Each takes the values of ONE run of consecutive candles
# and returns a list of the same length (None where not warmed up).
# ---------------------------------------------------------------------------

def _check_period(period: int) -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("Indicator periods must be positive integers.")


def sma_series(values: list[float], period: int) -> Series:

    _check_period(period)
    result: Series = [None] * len(values)
    window_sum = 0.0

    for i, value in enumerate(values):
        window_sum += value

        if i >= period:
            window_sum -= values[i - period]

        if i >= period - 1:
            result[i] = window_sum / period

    return result


def ema_series(values: Series, period: int) -> Series:
    """
    EMA seeded with the SMA of the first `period` values. Leading None
    values are skipped (used for the MACD signal line); the EMA starts at
    the first real value.
    """

    _check_period(period)
    result: Series = [None] * len(values)
    k = 2.0 / (period + 1)

    first = next(
        (i for i, value in enumerate(values) if value is not None), None
    )

    if first is None:
        return result

    seed_end = first + period - 1

    if seed_end >= len(values):
        return result

    window = values[first:seed_end + 1]

    if any(value is None for value in window):
        raise ValueError("EMA input has a gap after its first value.")

    ema = sum(window) / period
    result[seed_end] = ema

    for i in range(seed_end + 1, len(values)):
        if values[i] is None:
            raise ValueError("EMA input has a gap after its first value.")

        ema += k * (values[i] - ema)
        result[i] = ema

    return result


def rsi_series(closes: list[float], period: int = 14) -> Series:

    _check_period(period)
    result: Series = [None] * len(closes)

    if len(closes) <= period:
        return result

    gains = []
    losses = []

    for previous, close in zip(closes, closes[1:]):
        change = close - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    def rsi(gain: float, loss: float) -> float:
        if loss == 0:
            return 50.0 if gain == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + gain / loss)

    # gains[j] is the change INTO candle j + 1.
    result[period] = rsi(average_gain, average_loss)

    for j in range(period, len(gains)):
        average_gain = (average_gain * (period - 1) + gains[j]) / period
        average_loss = (average_loss * (period - 1) + losses[j]) / period
        result[j + 1] = rsi(average_gain, average_loss)

    return result


def macd_series(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[Series, Series, Series]:

    if fast >= slow:
        raise ValueError("The fast MACD period must be shorter than the slow.")

    fast_ema = ema_series(closes, fast)
    slow_ema = ema_series(closes, slow)

    line: Series = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_ema, slow_ema)
    ]
    signal_line = ema_series(line, signal)
    histogram: Series = [
        m - s if m is not None and s is not None else None
        for m, s in zip(line, signal_line)
    ]

    return line, signal_line, histogram


def bollinger_series(
    closes: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[Series, Series, Series, Series]:

    _check_period(period)
    middle = sma_series(closes, period)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    width: Series = [None] * len(closes)

    ready = [i for i, mean in enumerate(middle) if mean is not None]
    if ready:
        # population standard deviation of each window, computed for all windows at once (numpy)
        windows = sliding_window_view(np.asarray(closes, dtype=np.float64), period)[np.asarray(ready) - period + 1]
        means = np.asarray([middle[i] for i in ready])
        stds = np.sqrt(((windows - means[:, None]) ** 2).sum(axis=1) / period).tolist()
        for i, mean, std in zip(ready, means.tolist(), stds):
            upper[i] = mean + num_std * std
            lower[i] = mean - num_std * std
            width[i] = (upper[i] - lower[i]) / mean

    return middle, upper, lower, width


def atr_series(candles: list[MarketData], period: int = 14) -> Series:

    _check_period(period)
    result: Series = [None] * len(candles)
    true_ranges = []

    for i, candle in enumerate(candles):
        if i == 0:
            true_ranges.append(candle.high - candle.low)
        else:
            previous_close = candles[i - 1].close
            true_ranges.append(max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            ))

    if len(candles) < period:
        return result

    atr = sum(true_ranges[:period]) / period
    result[period - 1] = atr

    for i in range(period, len(candles)):
        atr = (atr * (period - 1) + true_ranges[i]) / period
        result[i] = atr

    return result


def relative_volume_series(volumes: list[float], period: int = 20) -> Series:

    _check_period(period)
    result: Series = [None] * len(volumes)

    for i in range(period, len(volumes)):
        average = sum(volumes[i - period:i]) / period

        if average > 0:
            result[i] = volumes[i] / average

    return result


# ---------------------------------------------------------------------------
# Indicator table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorSettings:
    ema_periods: tuple[int, ...] = (20, 50, 200)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    atr_period: int = 14
    volume_period: int = 20


@dataclass(frozen=True)
class IndicatorRow:
    exchange: str
    symbol: str
    timeframe: str
    timestamp: datetime  # period start; values are known at period end
    close: float
    values: dict[str, float | None]

    def is_complete(self) -> bool:
        """True once every indicator has warmed up."""
        return all(value is not None for value in self.values.values())


def calculate_indicators(
    candles: list[MarketData],
    timeframe: str,
    settings: IndicatorSettings = IndicatorSettings(),
) -> list[IndicatorRow]:
    """
    Calculate all indicators for candles of one exchange, symbol and
    timeframe. Returns one row per candle, oldest first.

    Value names: ema_<n>, rsi_<n>, macd, macd_signal, macd_hist,
    bb_middle, bb_upper, bb_lower, bb_width, atr_<n>,
    volume_sma_<n>, relative_volume_<n>.
    """

    rows = []

    for run in split_into_runs(candles, timeframe):

        closes = [candle.close for candle in run]
        volumes = [candle.volume for candle in run]

        columns: dict[str, Series] = {}

        for period in settings.ema_periods:
            columns[f"ema_{period}"] = ema_series(closes, period)

        columns[f"rsi_{settings.rsi_period}"] = rsi_series(
            closes, settings.rsi_period
        )

        (
            columns["macd"],
            columns["macd_signal"],
            columns["macd_hist"],
        ) = macd_series(
            closes,
            settings.macd_fast,
            settings.macd_slow,
            settings.macd_signal,
        )

        (
            columns["bb_middle"],
            columns["bb_upper"],
            columns["bb_lower"],
            columns["bb_width"],
        ) = bollinger_series(
            closes, settings.bollinger_period, settings.bollinger_std
        )

        columns[f"atr_{settings.atr_period}"] = atr_series(
            run, settings.atr_period
        )

        columns[f"volume_sma_{settings.volume_period}"] = sma_series(
            volumes, settings.volume_period
        )
        columns[f"relative_volume_{settings.volume_period}"] = (
            relative_volume_series(volumes, settings.volume_period)
        )

        for i, candle in enumerate(run):
            rows.append(
                IndicatorRow(
                    exchange=candle.exchange,
                    symbol=candle.symbol,
                    timeframe=timeframe,
                    timestamp=candle.timestamp,
                    close=candle.close,
                    values={
                        name: series[i] for name, series in columns.items()
                    },
                )
            )

    return rows


# Candles and indicator rows of one timeframe, computed once and shared by
# the chart, the overview and the backtests.
IndicatorTable = tuple[list[MarketData], list[IndicatorRow]]


def indicator_table(
    hourly_candles: list[MarketData],
    timeframe: str,
    settings: IndicatorSettings = IndicatorSettings(),
) -> IndicatorTable:
    candles = aggregate_hourly_candles(hourly_candles, timeframe).candles
    return candles, calculate_indicators(candles, timeframe, settings)


def indicator_tables(
    hourly_candles: list[MarketData],
    timeframes: tuple[str, ...] = ("1h", "4h", "1d"),
) -> dict[str, IndicatorTable]:
    return {tf: indicator_table(hourly_candles, tf) for tf in timeframes}
