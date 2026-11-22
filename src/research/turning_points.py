"""
Turning points: where were the real lows and highs, how late do our
strategies react, and what did the market look like just BEFORE a turn?

Swing lows/highs are found with hindsight (a "zigzag"): a low is confirmed
once the price has risen `threshold` (e.g. 20%) from it, a high once it has
fallen that much. These labels use the future, so they are only used to
STUDY the past, never as a signal. The features studied are all known at
each day's close.

1. lag_study: for each buy of a strategy, how many days after the last
   swing low did it buy, and how far above that low (in %)? For each sell,
   how long after the last swing high, and how far below it?
2. event_study: for each feature, its average percentile rank in the days
   before swing lows and before swing highs, compared with all days, plus
   the "lift": how much more often a swing low follows within N days when
   the feature is in its lowest (or highest) 10%, than on an average day.
"""

from dataclasses import dataclass
from datetime import datetime

from src.research.features import FeatureFrame


@dataclass(frozen=True)
class Turn:
    index: int
    time: datetime
    price: float
    kind: str  # "low" or "high"
    move_pct: float  # size of the move that confirmed it


def zigzag(closes: list[float], times: list[datetime], threshold: float = 0.20) -> list[Turn]:
    """Alternating swing lows and highs on closes; each confirmed by a move of `threshold`."""
    turns: list[Turn] = []
    if not closes:
        return turns
    hi_i = lo_i = 0
    direction = 0  # 1: in a rise (looking for its high), -1: in a fall, 0: not decided yet

    def low_at(k, i):
        turns.append(Turn(k, times[k], closes[k], "low", (closes[i] / closes[k] - 1) * 100))

    def high_at(k, i):
        turns.append(Turn(k, times[k], closes[k], "high", (closes[k] / closes[i] - 1) * 100))

    for i, x in enumerate(closes):
        if direction == 1:
            if x > closes[hi_i]:
                hi_i = i
            elif x <= closes[hi_i] * (1 - threshold):
                high_at(hi_i, i)
                direction, lo_i = -1, i
        elif direction == -1:
            if x < closes[lo_i]:
                lo_i = i
            elif x >= closes[lo_i] * (1 + threshold):
                low_at(lo_i, i)
                direction, hi_i = 1, i
        else:
            if x >= closes[lo_i] * (1 + threshold):
                low_at(lo_i, i)
                direction, hi_i = 1, i
            elif x <= closes[hi_i] * (1 - threshold):
                high_at(hi_i, i)
                direction, lo_i = -1, i
            else:
                hi_i = i if x > closes[hi_i] else hi_i
                lo_i = i if x < closes[lo_i] else lo_i
    return turns


@dataclass(frozen=True)
class LagRow:
    side: str  # "buy" / "sell"
    time: datetime
    price: float
    turn_time: datetime
    turn_price: float
    days_late: float
    pct_missed: float  # buy: % above the low; sell: % below the high


def lag_study(turns: list[Turn], actions: list[tuple[str, datetime, float]], max_days: float = 180) -> list[LagRow]:
    """actions: (side, time, price). Each is matched with the last turn of the right kind before it."""
    rows = []
    for side, when, px in actions:
        kind = "low" if side == "buy" else "high"
        before = [t for t in turns if t.kind == kind and t.time <= when]
        if not before:
            continue
        turn = before[-1]
        days = (when - turn.time).total_seconds() / 86400
        if days > max_days:
            continue
        missed = (px / turn.price - 1) * 100 if side == "buy" else (1 - px / turn.price) * 100
        rows.append(LagRow(side, when, px, turn.time, turn.price, round(days, 1), round(missed, 2)))
    return rows


@dataclass(frozen=True)
class FeatureEvidence:
    feature: str
    rank_before_lows: float | None  # average rank in the `window` days up to a low
    rank_before_highs: float | None
    rank_all_days: float | None
    low_lift_when_low: float | None  # P(low within horizon | rank < 0.1) / P(low within horizon)
    low_lift_when_high: float | None  # same, rank > 0.9
    high_lift_when_low: float | None
    high_lift_when_high: float | None
    days_low_extreme: int
    days_high_extreme: int


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def event_study(frame: FeatureFrame, turns: list[Turn], window: int = 10, horizon: int = 20) -> list[FeatureEvidence]:
    n = len(frame.market.candles)
    near_low = [False] * n  # a swing low happens within the next `horizon` days (or today)
    near_high = [False] * n
    before_low, before_high = set(), set()
    for t in turns:
        for k in range(max(0, t.index - horizon), t.index + 1):
            (near_low if t.kind == "low" else near_high)[k] = True
        for k in range(max(0, t.index - window), t.index + 1):
            (before_low if t.kind == "low" else before_high).add(k)
    out = []
    for name, ranks in sorted(frame.ranks.items()):
        valid = [i for i in range(n) if ranks[i] is not None]
        if not valid:
            continue
        base_low = sum(near_low[i] for i in valid) / len(valid)
        base_high = sum(near_high[i] for i in valid) / len(valid)
        lows = [i for i in valid if ranks[i] < 0.1]
        highs = [i for i in valid if ranks[i] > 0.9]

        def lift(days, target, base):
            if not days or base == 0:
                return None
            return round(sum(target[i] for i in days) / len(days) / base, 2)

        out.append(FeatureEvidence(
            name,
            _mean([ranks[i] for i in before_low]),
            _mean([ranks[i] for i in before_high]),
            _mean([ranks[i] for i in valid]),
            lift(lows, near_low, base_low), lift(highs, near_low, base_low),
            lift(lows, near_high, base_high), lift(highs, near_high, base_high),
            len(lows), len(highs),
        ))
    return out
