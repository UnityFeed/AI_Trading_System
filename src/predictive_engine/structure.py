"""
Market structure recognition (predictive engine, phase 1).

Everything here is CAUSAL: a swing point only exists from the candle that
confirms it, so the result at candle i never depends on later candles.

Pivots (swing points)
  A pivot high at candle k has a high above the highs of the `left` candles
  before it and at least as high as the `right` candles after it (a pivot low:
  the same with lows). It needs those `right` later candles, so it becomes
  KNOWN only at the close of candle k + right (its confirmation). Pivots never
  cross a gap in the data. When two highs (or two lows) follow each other
  without the other kind in between, the more extreme one is the swing.

Swing labels
  Each confirmed swing high is HH (higher high) or LH (lower high) compared
  with the previous swing high; each swing low HL (higher low) or LL.

Trend state and events (decided at each close, using only known swings)
  BOS up    the close breaks above the last swing high while the trend is
            already up (Break Of Structure: the trend continues)
  CHoCH up  the close breaks above the last swing high while the trend was
            down (Change Of Character: possible reversal)
  (and the same downwards below the last swing low)
  The first break of all just sets the trend (BOS).
  Sweep     the high goes above the last swing high but the candle CLOSES back
            below it (or the low below the last swing low and closes back
            above): stops were taken but the level held ("liquidity sweep").
  Each swing level is broken (or swept) at most once.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.data_collection.market_data import MarketData


@dataclass(frozen=True)
class Pivot:
    index: int  # candle of the swing point itself
    time: datetime
    price: float
    kind: str  # "high" or "low"
    confirmed_index: int  # candle at whose close it becomes known
    confirmed_time: datetime  # close time of that candle
    label: str = ""  # HH / LH / HL / LL (empty for the first of its kind)


@dataclass(frozen=True)
class StructureEvent:
    index: int
    time: datetime  # close time of the candle (when it is known)
    kind: str  # "BOS", "CHoCH" or "sweep"
    direction: str  # "up" or "down"
    level: float  # the swing price that was broken or swept
    swing_time: datetime  # when that swing point was


@dataclass
class Structure:
    timeframe: str
    pivots: list[Pivot] = field(default_factory=list)  # alternating swings, in confirmation order
    events: list[StructureEvent] = field(default_factory=list)
    trend: list[str] = field(default_factory=list)  # per candle: "up", "down" or "none"
    swing_high: list[float | None] = field(default_factory=list)  # last known swing high per candle
    swing_low: list[float | None] = field(default_factory=list)


def _consecutive(candles: list[MarketData], timeframe: str) -> list[bool]:
    step = timedelta(hours=TIMEFRAME_HOURS[timeframe])
    return [False] + [b.timestamp - a.timestamp == step for a, b in zip(candles, candles[1:])]


def raw_pivots(candles: list[MarketData], timeframe: str, left: int = 3, right: int = 3) -> list[Pivot]:
    """Every pivot high and low, ordered by confirmation (unlabelled, not yet alternating)."""
    n = len(candles)
    cons = _consecutive(candles, timeframe)
    period = timedelta(hours=TIMEFRAME_HOURS[timeframe])
    out = []
    for k in range(left, n - right):
        if not all(cons[k - left + 1:k + right + 1]):
            continue  # the window crosses a gap
        c = candles[k]
        before = candles[k - left:k]
        after = candles[k + 1:k + right + 1]
        confirm = k + right
        when = candles[confirm].timestamp + period
        if all(c.high > x.high for x in before) and all(c.high >= x.high for x in after):
            out.append(Pivot(k, c.timestamp, c.high, "high", confirm, when))
        if all(c.low < x.low for x in before) and all(c.low <= x.low for x in after):
            out.append(Pivot(k, c.timestamp, c.low, "low", confirm, when))
    out.sort(key=lambda p: (p.confirmed_index, p.index))
    return out


def analyse(candles: list[MarketData], timeframe: str, left: int = 3, right: int = 3) -> Structure:
    """Swings, labels, trend per candle and structure events, all causal."""
    result = Structure(timeframe)
    period = timedelta(hours=TIMEFRAME_HOURS[timeframe])
    by_confirmation: dict[int, list[Pivot]] = {}
    for p in raw_pivots(candles, timeframe, left, right):
        by_confirmation.setdefault(p.confirmed_index, []).append(p)

    swings: list[Pivot] = []
    last_high = last_low = None  # the swing levels that can still be broken
    prev_high = prev_low = None  # for HH/LH and HL/LL labels
    trend = "none"

    def add(p: Pivot) -> None:
        nonlocal last_high, last_low, prev_high, prev_low
        if swings and swings[-1].kind == p.kind:
            # two of a kind in a row: keep the more extreme one
            keep_new = p.price > swings[-1].price if p.kind == "high" else p.price < swings[-1].price
            if not keep_new:
                return
            swings.pop()
            # compare the replacement with the swing before the one it replaces
            earlier = [q for q in swings if q.kind == p.kind]
            if p.kind == "high":
                prev_high = earlier[-1] if earlier else None
            else:
                prev_low = earlier[-1] if earlier else None
        if p.kind == "high":
            label = "" if prev_high is None else ("HH" if p.price > prev_high.price else "LH")
            p = Pivot(p.index, p.time, p.price, p.kind, p.confirmed_index, p.confirmed_time, label)
            prev_high = last_high = p
        else:
            label = "" if prev_low is None else ("HL" if p.price > prev_low.price else "LL")
            p = Pivot(p.index, p.time, p.price, p.kind, p.confirmed_index, p.confirmed_time, label)
            prev_low = last_low = p
        swings.append(p)

    for i, c in enumerate(candles):
        for p in by_confirmation.get(i, []):
            add(p)
        when = c.timestamp + period
        if last_high is not None and last_high.confirmed_index < i:  # breakable from the next candle
            if c.close > last_high.price:
                kind = "CHoCH" if trend == "down" else "BOS"
                result.events.append(StructureEvent(i, when, kind, "up", last_high.price, last_high.time))
                trend, last_high = "up", None
            elif c.high > last_high.price:
                result.events.append(StructureEvent(i, when, "sweep", "up", last_high.price, last_high.time))
                last_high = None
        if last_low is not None and last_low.confirmed_index < i:
            if c.close < last_low.price:
                kind = "CHoCH" if trend == "up" else "BOS"
                result.events.append(StructureEvent(i, when, kind, "down", last_low.price, last_low.time))
                trend, last_low = "down", None
            elif c.low < last_low.price:
                result.events.append(StructureEvent(i, when, "sweep", "down", last_low.price, last_low.time))
                last_low = None
        result.trend.append(trend)
        result.swing_high.append(prev_high.price if prev_high else None)
        result.swing_low.append(prev_low.price if prev_low else None)

    result.pivots = swings
    return result
