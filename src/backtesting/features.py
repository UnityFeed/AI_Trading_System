"""
Extra price features for the graded-exposure strategies (roadmap 9c), on
the candles of one backtest Market.

Same rules as the indicators: a value at candle i only uses candles up to
and including i (known at its close); rolling windows restart at every gap
(a candle that is not exactly one period after the previous one); values
that are not warmed up yet are None.

- sma(n):            simple average of the last n closes
- ret(n):            close / close n candles ago - 1
- prior_high(n):     highest high of the n candles BEFORE i (breakout level)
- prior_low(n):      lowest low of the n candles BEFORE i
- ewma_vol(lam):     volatility of log returns, exponentially weighted
                     (RiskMetrics, lambda 0.94), as a yearly figure
"""

import math
from collections import deque

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting.market import Market


def _runs(market: Market) -> list[range]:
    """Index ranges of consecutive candles."""
    runs, start = [], 0
    for i in range(1, len(market.candles)):
        if not market.consecutive[i]:
            runs.append(range(start, i))
            start = i
    if market.candles:
        runs.append(range(start, len(market.candles)))
    return runs


def sma(market: Market, n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(market.candles)
    for run in _runs(market):
        window: deque[float] = deque()
        total = 0.0
        for i in run:
            close = market.candles[i].close
            window.append(close)
            total += close
            if len(window) > n:
                total -= window.popleft()
            if len(window) == n:
                out[i] = total / n
    return out


def ret(market: Market, n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(market.candles)
    for run in _runs(market):
        for i in run:
            if i - n >= run.start:
                out[i] = market.candles[i].close / market.candles[i - n].close - 1.0
    return out


def _prior_extreme(market: Market, n: int, high: bool) -> list[float | None]:
    out: list[float | None] = [None] * len(market.candles)
    for run in _runs(market):
        for i in run:
            if i - n >= run.start:
                values = [
                    (c.high if high else c.low) for c in market.candles[i - n:i]
                ]
                out[i] = max(values) if high else min(values)
    return out


def prior_high(market: Market, n: int) -> list[float | None]:
    return _prior_extreme(market, n, high=True)


def prior_low(market: Market, n: int) -> list[float | None]:
    return _prior_extreme(market, n, high=False)


def ewma_vol(market: Market, lam: float = 0.94, warmup: int = 30) -> list[float | None]:
    """
    Yearly volatility: sqrt(periods per year x EWMA of squared log returns).
    The average is seeded with the mean square of the first `warmup` returns
    of a run, and is None until then.
    """
    periods_per_year = 365.0 * 24 / TIMEFRAME_HOURS[market.timeframe]
    out: list[float | None] = [None] * len(market.candles)
    for run in _runs(market):
        seed: list[float] = []
        variance = None
        for i in run:
            if i == run.start:
                continue
            r = math.log(market.candles[i].close / market.candles[i - 1].close)
            if variance is None:
                seed.append(r * r)
                if len(seed) == warmup:
                    variance = sum(seed) / warmup
                else:
                    continue
            else:
                variance = lam * variance + (1 - lam) * r * r
            out[i] = math.sqrt(variance * periods_per_year)
    return out
