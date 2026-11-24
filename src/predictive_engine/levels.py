"""
Price levels and market regime (predictive engine, phase 6 tools), all
known at a given candle's close (only swings CONFIRMED by then are used):

support_resistance(pivots, price, at_index)
  Zones where the price turned more than once: confirmed swing highs and
  lows within `tolerance` (default 1.5%) of each other are merged into one
  zone; the more turns, the stronger. Zones are reported as support (below
  the price) or resistance (above it).

fibonacci(pivots, at_index)
  Retracement (0.236 ... 0.786) and extension (1.272 ... 2.618) levels of the
  last confirmed swing: from the last swing low to the last swing high (an
  up-move) or the reverse (a down-move).

adx(candles)
  Average Directional Index (Wilder, 14): trend strength. With volatility it
  gives the regime: trending (ADX >= 25), ranging (ADX < 20), in between.
"""

from bisect import bisect_left
from dataclasses import dataclass

from src.data_collection.market_data import MarketData
from src.predictive_engine.structure import Pivot


RETRACEMENTS = (0.236, 0.382, 0.5, 0.618, 0.786)
EXTENSIONS = (1.272, 1.414, 1.618, 2.0, 2.618)


@dataclass(frozen=True)
class Zone:
    low: float
    high: float
    touches: int
    kind: str  # "support" or "resistance" (relative to the price it was built for)
    last_touch_index: int

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2


def zone_clusters(known: list[Pivot], tolerance: float = 0.015, min_touches: int = 2) -> list[tuple]:
    """Clusters of swing prices within `tolerance`: (low, high, touches, mid, last index), lowest first."""
    clusters: list[list[Pivot]] = []
    sums: list[float] = []  # running sum per cluster (same result as summing again, much faster)
    for p in sorted(known, key=lambda q: q.price):
        if clusters and p.price <= clusters[-1][0].price * (1 + tolerance) and \
                p.price <= sums[-1] / len(clusters[-1]) * (1 + tolerance):
            clusters[-1].append(p)
            sums[-1] += p.price
        else:
            clusters.append([p])
            sums.append(0.0 + p.price)
    out = []
    for c in clusters:
        if len(c) < min_touches:
            continue
        low, high = min(p.price for p in c), max(p.price for p in c)
        out.append((low, high, len(c), (low + high) / 2, max(p.index for p in c)))
    return out


def support_resistance(pivots: list[Pivot], price: float, at_index: int, tolerance: float = 0.015,
                       min_touches: int = 2, lookback: int | None = None) -> list[Zone]:
    known = [p for p in pivots if p.confirmed_index <= at_index
             and (lookback is None or p.index >= at_index - lookback)]
    return [Zone(low, high, touches, "support" if mid < price else "resistance", last)
            for low, high, touches, mid, last in zone_clusters(known, tolerance, min_touches)]


def nearest_levels_over_time(candles: list, timeframe: str, lookback: int | None, max_swings: int | None = None):
    """
    For every candle: (distance to the nearest support below, distance to the
    nearest resistance above, position inside the last Fibonacci swing), from
    the swings KNOWN at its close. Zones are rebuilt only when the known swings
    in the window change. Same values as calling support_resistance/fibonacci
    per candle.
    """
    from src.predictive_engine.patterns import swings_known_over_time

    version = 0
    cache_key, clusters = None, []
    for i, known, changed in swings_known_over_time(candles, timeframe):
        version += changed
        recent = known if max_swings is None else known[-max_swings:]
        start = 0
        if lookback is not None:  # swings are in time order: skip those before the window
            start = bisect_left([p.index for p in recent], i - lookback) if recent and recent[0].index < i - lookback else 0
        key = (version, len(known), start)
        if key != cache_key:
            clusters = zone_clusters(recent[start:])
            cache_key = key
        price = candles[i].close
        below = [high for low, high, _, mid, _ in clusters if mid < price]
        above = [low for low, high, _, mid, _ in clusters if mid >= price]
        support = price / max(below) - 1 if below else None
        resistance = min(above) / price - 1 if above else None
        fib = fibonacci(recent, i)
        position = (price - fib.start) / (fib.end - fib.start) if fib and fib.end != fib.start else None
        yield i, support, resistance, position


def _mean(items: list[Pivot]) -> float:
    return sum(p.price for p in items) / len(items)


@dataclass(frozen=True)
class FibLevels:
    direction: str  # "up" (low -> high) or "down" (high -> low)
    start: float
    end: float
    start_index: int
    end_index: int
    retracements: dict  # ratio -> price
    extensions: dict

    def all_levels(self) -> list[tuple[str, float]]:
        return [(f"{r:g}", p) for r, p in self.retracements.items()] + \
               [(f"{e:g}", p) for e, p in self.extensions.items()]


def fibonacci(pivots: list[Pivot], at_index: int) -> FibLevels | None:
    known = [p for p in pivots if p.confirmed_index <= at_index]
    if len(known) < 2:
        return None
    a, b = known[-2], known[-1]
    if a.kind == b.kind:
        return None
    move = b.price - a.price
    direction = "up" if move > 0 else "down"
    # retracement: back from the end toward the start; extension: beyond the end, measured from the start
    retr = {r: b.price - move * r for r in RETRACEMENTS}
    ext = {e: a.price + move * e for e in EXTENSIONS}
    return FibLevels(direction, a.price, b.price, a.index, b.index, retr, ext)


def adx(candles: list[MarketData], period: int = 14) -> list[float | None]:
    """Wilder's ADX; None until warmed up (about 2 x period candles)."""
    n = len(candles)
    out: list[float | None] = [None] * n
    tr_s = plus_s = minus_s = None
    dx_values: list[float] = []
    adx_value = None
    for i in range(1, n):
        c, p = candles[i], candles[i - 1]
        up, down = c.high - p.high, p.low - c.low
        plus_dm = up if up > down and up > 0 else 0.0
        minus_dm = down if down > up and down > 0 else 0.0
        tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        if tr_s is None:
            if i < period:
                continue
            window = range(i - period + 1, i + 1)
            tr_s = sum(_true_range(candles, k) for k in window)
            plus_s = sum(_dm(candles, k)[0] for k in window)
            minus_s = sum(_dm(candles, k)[1] for k in window)
        else:
            tr_s = tr_s - tr_s / period + tr
            plus_s = plus_s - plus_s / period + plus_dm
            minus_s = minus_s - minus_s / period + minus_dm
        if tr_s <= 0:
            continue
        plus_di, minus_di = 100 * plus_s / tr_s, 100 * minus_s / tr_s
        total = plus_di + minus_di
        dx = 0.0 if total == 0 else 100 * abs(plus_di - minus_di) / total
        if adx_value is None:
            dx_values.append(dx)
            if len(dx_values) == period:
                adx_value = sum(dx_values) / period
                out[i] = adx_value
        else:
            adx_value = (adx_value * (period - 1) + dx) / period
            out[i] = adx_value
    return out


def _true_range(candles, k):
    c, p = candles[k], candles[k - 1]
    return max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))


def _dm(candles, k):
    c, p = candles[k], candles[k - 1]
    up, down = c.high - p.high, p.low - c.low
    return (up if up > down and up > 0 else 0.0, down if down > up and down > 0 else 0.0)


def regime(adx_value: float | None, vol_rank: float | None) -> str:
    """Plain-language regime from ADX and the volatility percentile."""
    if adx_value is None:
        return "unknown"
    trend = "trending" if adx_value >= 25 else ("ranging" if adx_value < 20 else "weak trend")
    if vol_rank is None:
        return trend
    vol = "wild" if vol_rank > 0.8 else ("calm" if vol_rank < 0.2 else "normal volatility")
    return f"{trend}, {vol}"
