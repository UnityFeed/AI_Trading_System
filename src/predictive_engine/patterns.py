"""
Classic chart patterns (predictive engine, phase 6), built ONLY from swing
points that were confirmed at the time, so a pattern never appears in hindsight.

Patterns (bull = expected breakout up, bear = down):
  double bottom (bull) / double top (bear)
      two lows (highs) within 3% of each other with a peak (dip) of at least
      4% between them; the neckline is that peak (dip)
  inverse head and shoulders (bull) / head and shoulders (bear)
      three lows (highs), the middle one the most extreme, the outer two
      within 6% of each other; the neckline runs through the two peaks (dips)
  ascending (bull) / descending (bear) / symmetrical (either) triangle
      two highs and two lows: flat top + rising lows, falling highs + flat
      bottom, or falling highs + rising lows

Life cycle (each step decided at a daily close):
  candidate  detected when its last swing is confirmed
  confirmed  a close breaks the neckline / triangle side in the pattern's
             direction (for a symmetrical triangle: either side)
  hit        after confirmation, a close reaches the measured target
             (breakout level +/- the pattern height)
  failed     a close breaks the invalidation level (before or after the
             breakout) before the target
  expired    no breakout, or no target, within the time allowed (3 x the
             pattern's length, at least 20 candles)
"""

from dataclasses import dataclass, field

from src.data_collection.market_data import MarketData
from src.predictive_engine.structure import Pivot, raw_pivots


@dataclass
class Pattern:
    kind: str
    direction: str  # "bull", "bear" or "either" (symmetrical triangle before its breakout)
    points: list[Pivot]
    detected_index: int
    neckline: tuple  # (index_a, price_a, index_b, price_b): line through two points (flat if equal prices)
    lower: tuple | None = None  # second line for triangles
    height: float = 0.0
    invalidation: float = 0.0
    status: str = "candidate"
    confirmed_index: int | None = None
    breakout_price: float | None = None
    target: float | None = None
    end_index: int | None = None
    history: list = field(default_factory=list)  # (index, status)

    def line_at(self, line, i: int) -> float:
        ia, pa, ib, pb = line
        return pa if ib == ia else pa + (pb - pa) * (i - ia) / (ib - ia)

    @property
    def width(self) -> int:
        return self.points[-1].index - self.points[0].index

    def deadline(self) -> int:
        return self.detected_index + max(20, 3 * self.width)


def swings_known_over_time(candles: list[MarketData], timeframe: str, left: int = 3, right: int = 3):
    """For each candle: the alternating swing list known at its close (as in structure.analyse)."""
    by_confirmation: dict[int, list[Pivot]] = {}
    for p in raw_pivots(candles, timeframe, left, right):
        by_confirmation.setdefault(p.confirmed_index, []).append(p)
    swings: list[Pivot] = []
    for i in range(len(candles)):
        changed = False
        for p in by_confirmation.get(i, []):
            if swings and swings[-1].kind == p.kind:
                better = p.price > swings[-1].price if p.kind == "high" else p.price < swings[-1].price
                if not better:
                    continue
                swings.pop()
            swings.append(p)
            changed = True
        yield i, swings, changed


def _close(a: float, b: float, pct: float) -> bool:
    return abs(a - b) / min(a, b) <= pct


def _detect(swings: list[Pivot], i: int) -> list[Pattern]:
    found = []
    s = swings
    if len(s) >= 3:
        a, b, c = s[-3], s[-2], s[-1]
        if c.kind == "low" and _close(a.price, c.price, 0.03) and b.price >= max(a.price, c.price) * 1.04:
            bottom = min(a.price, c.price)
            found.append(Pattern("double bottom", "bull", [a, b, c], i, (b.index, b.price, b.index, b.price),
                                 height=b.price - bottom, invalidation=bottom))
        if c.kind == "high" and _close(a.price, c.price, 0.03) and b.price <= min(a.price, c.price) * 0.96:
            top = max(a.price, c.price)
            found.append(Pattern("double top", "bear", [a, b, c], i, (b.index, b.price, b.index, b.price),
                                 height=top - b.price, invalidation=top))
    if len(s) >= 5:
        l1, n1, h, n2, l3 = s[-5:]
        if l3.kind == "low" and h.price < l1.price and h.price < l3.price and _close(l1.price, l3.price, 0.06):
            line = (n1.index, n1.price, n2.index, n2.price)
            neck_at_head = n1.price + (n2.price - n1.price) * (h.index - n1.index) / max(1, n2.index - n1.index)
            found.append(Pattern("inverse head and shoulders", "bull", [l1, n1, h, n2, l3], i, line,
                                 height=neck_at_head - h.price, invalidation=h.price))
        if l3.kind == "high" and h.price > l1.price and h.price > l3.price and _close(l1.price, l3.price, 0.06):
            line = (n1.index, n1.price, n2.index, n2.price)
            neck_at_head = n1.price + (n2.price - n1.price) * (h.index - n1.index) / max(1, n2.index - n1.index)
            found.append(Pattern("head and shoulders", "bear", [l1, n1, h, n2, l3], i, line,
                                 height=h.price - neck_at_head, invalidation=h.price))
    if len(s) >= 4:
        last4 = s[-4:]
        highs = [p for p in last4 if p.kind == "high"]
        lows = [p for p in last4 if p.kind == "low"]
        if len(highs) == 2 and len(lows) == 2:
            h1, h2 = highs
            l1, l2 = lows
            upper = (h1.index, h1.price, h2.index, h2.price)
            lower = (l1.index, l1.price, l2.index, l2.price)
            flat_top = _close(h1.price, h2.price, 0.015)
            flat_bottom = _close(l1.price, l2.price, 0.015)
            rising_lows = l2.price > l1.price * 1.01
            falling_highs = h2.price < h1.price * 0.99
            height = h1.price - l1.price
            kind = direction = None
            if flat_top and rising_lows:
                kind, direction, invalid = "ascending triangle", "bull", l2.price
            elif falling_highs and flat_bottom:
                kind, direction, invalid = "descending triangle", "bear", h2.price
            elif falling_highs and rising_lows:
                kind, direction, invalid = "symmetrical triangle", "either", None
            if kind and height > 0:
                found.append(Pattern(kind, direction, last4, i, upper, lower=lower, height=height,
                                     invalidation=invalid if invalid is not None else 0.0))
    return found


def detect_patterns(candles: list[MarketData], timeframe: str = "1d", left: int = 3, right: int = 3) -> list[Pattern]:
    """All patterns with their full life cycle, walking forward candle by candle."""
    patterns: list[Pattern] = []
    active: list[Pattern] = []
    seen = set()
    for i, swings, changed in swings_known_over_time(candles, timeframe, left, right):
        close = candles[i].close
        for p in list(active):
            if i <= p.detected_index:
                continue
            _step(p, i, close)
            if p.status in ("hit", "failed", "expired"):
                active.remove(p)
        if changed:
            for p in _detect(swings, i):
                key = (p.kind, tuple(q.index for q in p.points))
                if key in seen:
                    continue
                seen.add(key)
                if _outside(p, i, close):
                    continue  # the price already left the pattern before it could be known: not tradeable
                p.history.append((i, "candidate"))
                patterns.append(p)
                active.append(p)
    return patterns


def _outside(p: Pattern, i: int, close: float) -> bool:
    upper = p.line_at(p.neckline, i)
    lower = p.line_at(p.lower, i) if p.lower else None
    if p.kind.endswith("triangle"):
        # the lines must still be apart (the tip not reached) and the close between them
        return upper <= lower * 1.005 or close > upper or close < lower
    return close > upper if p.direction == "bull" else close < upper


def _step(p: Pattern, i: int, close: float) -> None:
    if p.status == "candidate":
        upper = p.line_at(p.neckline, i)
        lower = p.line_at(p.lower, i) if p.lower else None
        if p.direction in ("bull", "either") and close > upper:
            _confirm(p, i, close, "bull", upper)
        elif p.direction == "either" and lower is not None and close < lower:
            _confirm(p, i, close, "bear", lower)
        elif p.direction == "bear" and close < (lower if p.lower is not None and p.kind.endswith("triangle") else upper):
            _confirm(p, i, close, "bear", lower if p.kind.endswith("triangle") else upper)
        elif p.direction == "bull" and p.invalidation and close < p.invalidation:
            _end(p, i, "failed")
        elif p.direction == "bear" and p.invalidation and close > p.invalidation:
            _end(p, i, "failed")
        elif i > p.deadline():
            _end(p, i, "expired")
        return
    if p.status == "confirmed":
        if p.direction == "bull" and close >= p.target:
            _end(p, i, "hit")
        elif p.direction == "bear" and close <= p.target:
            _end(p, i, "hit")
        elif p.direction == "bull" and close < p.invalidation:
            _end(p, i, "failed")
        elif p.direction == "bear" and close > p.invalidation:
            _end(p, i, "failed")
        elif i > p.confirmed_index + max(20, 3 * p.width):
            _end(p, i, "expired")


def _confirm(p: Pattern, i: int, close: float, direction: str, level: float) -> None:
    p.direction = direction
    p.status = "confirmed"
    p.confirmed_index = i
    p.breakout_price = level
    p.target = level + p.height if direction == "bull" else level - p.height
    if p.kind == "symmetrical triangle":  # invalidation: back through the opposite side
        p.invalidation = p.line_at(p.lower, i) if direction == "bull" else p.line_at(p.neckline, i)
    p.history.append((i, "confirmed"))


def _end(p: Pattern, i: int, status: str) -> None:
    p.status = status
    p.end_index = i
    p.history.append((i, status))


def status_at(p: Pattern, i: int) -> str | None:
    """The pattern's status as it was known at candle i (None if not detected yet)."""
    current = None
    for index, status in p.history:
        if index <= i:
            current = status
    return current


def track_record(patterns: list[Pattern]) -> dict:
    """Per kind: detected, confirmed, hit, failed, expired, and hit rate after confirmation."""
    out: dict = {}
    for p in patterns:
        r = out.setdefault(p.kind, {"detected": 0, "confirmed": 0, "hit": 0, "failed": 0, "expired": 0, "open": 0})
        r["detected"] += 1
        statuses = [s for _, s in p.history]
        if "confirmed" in statuses:
            r["confirmed"] += 1
            if p.status in ("hit", "failed", "expired"):
                r[p.status] += 1
            else:
                r["open"] += 1
    for r in out.values():
        decided = r["hit"] + r["failed"] + r["expired"]
        r["hit_rate"] = round(r["hit"] / decided, 3) if decided else None
    return out


def pattern_features(patterns: list[Pattern], n: int, recent: int = 10) -> dict[str, list[float]]:
    """Per candle (known at its close): bullish / bearish candidates open, and breakouts in the last `recent` candles."""
    out = {name: [0.0] * n for name in ("pattern.bull_candidates", "pattern.bear_candidates",
                                        "pattern.bull_breakout_recent", "pattern.bear_breakout_recent")}
    for p in patterns:
        for i in range(p.detected_index, min(n, (p.end_index or n - 1) + 1)):
            status = status_at(p, i)
            if status == "candidate":
                if p.direction in ("bull", "either"):
                    out["pattern.bull_candidates"][i] += 1
                if p.direction in ("bear", "either"):
                    out["pattern.bear_candidates"][i] += 1
        if p.confirmed_index is not None:
            key = "pattern.bull_breakout_recent" if p.direction == "bull" else "pattern.bear_breakout_recent"
            for i in range(p.confirmed_index, min(n, p.confirmed_index + recent)):
                out[key][i] = 1.0
    return out
