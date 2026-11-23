"""
Scenario outcomes (predictive engine, phase 2): an exact, scorable answer for
every day, so that scenario probabilities can later be checked.

For the close of day i, with horizon H days and a band of k "typical moves":
  move    = k x daily volatility x sqrt(H)   (daily volatility: EWMA of daily
            log returns, known at day i; floor `min_move`)
  target  = close x (1 + move)               bullish barrier
  stop    = close x (1 - move)               bearish barrier
Then, walking forward over the next H daily CLOSES:
  "bull"   a close reaches the target first
  "bear"   a close reaches the stop first
  "range"  neither within H days
Closes (not intraday highs/lows) avoid "which came first inside one candle".

Each outcome also records the days until it was decided, and the largest
rise and fall (on closes) during the window. An outcome is only known once
it is decided (the hit day, or day i+H for "range"); near the end of the
history a target or stop already reached counts, the rest have no outcome
yet (None). Windows never cross a gap in the data.
"""

import math
from dataclasses import dataclass

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting import features as price
from src.backtesting.market import Market


@dataclass(frozen=True)
class Outcome:
    index: int
    kind: str  # "bull", "bear" or "range"
    move_pct: float  # barrier distance used (both sides)
    target: float
    stop: float
    days: int  # days until decided
    decided_index: int  # candle at whose close the outcome is known
    max_rise_pct: float
    max_fall_pct: float


def candle_volatility(market: Market) -> list[float | None]:
    """Typical move of ONE candle of the market's timeframe (EWMA of log returns)."""
    yearly = price.ewma_vol(market)
    periods = 365.0 * 24 / TIMEFRAME_HOURS[market.timeframe]
    return [None if v is None else v / math.sqrt(periods) for v in yearly]


def daily_volatility(market: Market) -> list[float | None]:
    return candle_volatility(market)  # kept for the daily callers


def default_min_move(timeframe: str) -> float:
    """Smallest barrier: 3% for a daily horizon, scaled for other timeframes."""
    return 0.03 * math.sqrt(TIMEFRAME_HOURS[timeframe] / 24)


def outcomes(market: Market, horizon: int = 30, k: float = 1.0, min_move: float | None = None) -> list[Outcome | None]:
    """`horizon` in candles of the market's timeframe (days on the daily chart)."""
    if min_move is None:
        min_move = default_min_move(market.timeframe)
    c = market.candles
    n = len(c)
    vol = candle_volatility(market)
    out: list[Outcome | None] = [None] * n
    for i in range(n):
        if vol[i] is None or i + 1 >= n:
            continue
        move = max(min_move, k * vol[i] * math.sqrt(horizon))
        start = c[i].close
        target, stop = start * (1 + move), start * (1 - move)
        kind = decided = None
        hi = lo = start
        for j in range(i + 1, min(i + horizon, n - 1) + 1):
            if not market.consecutive[j]:
                break  # a gap: this window cannot be judged
            x = c[j].close
            hi, lo = max(hi, x), min(lo, x)
            if x >= target:
                kind, decided = "bull", j
                break
            if x <= stop:
                kind, decided = "bear", j
                break
        else:
            if i + horizon <= n - 1:
                kind, decided = "range", i + horizon
        if kind is None:
            continue  # not decided yet at the end of the data, or broken by a gap
        out[i] = Outcome(i, kind, move * 100, target, stop, decided - i, decided,
                         (hi / start - 1) * 100, (lo / start - 1) * 100)
    return out


@dataclass(frozen=True)
class BaseRates:
    n: int
    bull: float
    bear: float
    range: float
    median_days: dict  # kind -> median days until decided

    @staticmethod
    def of(items: list[Outcome]) -> "BaseRates | None":
        if not items:
            return None
        n = len(items)
        days = {}
        for kind in ("bull", "bear", "range"):
            d = sorted(o.days for o in items if o.kind == kind)
            days[kind] = d[len(d) // 2] if d else None
        return BaseRates(
            n,
            sum(o.kind == "bull" for o in items) / n,
            sum(o.kind == "bear" for o in items) / n,
            sum(o.kind == "range" for o in items) / n,
            days,
        )


def base_rates_by(outcome_list: list[Outcome | None], groups: list) -> dict:
    """Base rates per group value (e.g. the structure trend of each day)."""
    buckets: dict = {}
    for o, g in zip(outcome_list, groups):
        if o is not None and g is not None:
            buckets.setdefault(g, []).append(o)
    return {g: BaseRates.of(items) for g, items in buckets.items()}
