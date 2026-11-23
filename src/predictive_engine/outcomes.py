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
it is decided (the hit day, or day i+H for "range"); the last days of the
history have no outcome yet (None). Windows never cross a gap in the data.
"""

import math
from dataclasses import dataclass

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


def daily_volatility(market: Market) -> list[float | None]:
    yearly = price.ewma_vol(market)
    return [None if v is None else v / math.sqrt(365) for v in yearly]


def outcomes(market: Market, horizon: int = 30, k: float = 1.0, min_move: float = 0.03) -> list[Outcome | None]:
    if market.timeframe != "1d":
        raise ValueError("Scenario outcomes are defined on daily candles.")
    c = market.candles
    n = len(c)
    vol = daily_volatility(market)
    out: list[Outcome | None] = [None] * n
    for i in range(n):
        if vol[i] is None or i + horizon >= n:
            continue
        if not all(market.consecutive[i + 1:i + horizon + 1]):
            continue
        move = max(min_move, k * vol[i] * math.sqrt(horizon))
        start = c[i].close
        target, stop = start * (1 + move), start * (1 - move)
        kind, decided = "range", i + horizon
        hi = lo = start
        for j in range(i + 1, i + horizon + 1):
            x = c[j].close
            hi, lo = max(hi, x), min(lo, x)
            if x >= target:
                kind, decided = "bull", j
                break
            if x <= stop:
                kind, decided = "bear", j
                break
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
