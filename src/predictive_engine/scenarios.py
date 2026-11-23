"""
Scenario probabilities (predictive engine, phase 3).

For each daily close: the chances of the three outcomes of outcomes.py over
the next H days (bull = +move reached first, bear = -move first, range =
neither), with the number of past cases behind them.

Models (all learn only from outcomes that were DECIDED before the day they
predict, so nothing from the future leaks in):
  base       how often each outcome happened on all earlier days (the
             yardstick every other model must beat)
  structure  the same, but only earlier days with the same daily and weekly
             market structure (trend up/down/none), pulled toward the base
             rate when there are few such days
  analog     the 100 earlier days whose situation looked most like today
             (all research features, as percentile ranks), pulled toward the
             structure rates; also gives the typical number of days the
             winning outcomes took

Walk-forward: for test year Y, every model is built from outcomes decided
before 1 January of Y and predicts every day of Y. Scores: multi-class
Brier score and log loss, compared with the base model ("skill": 1 =
perfect, 0 = no better than the base rate, below 0 = worse).
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.predictive_engine.outcomes import Outcome
from src.research.features import FeatureFrame


KINDS = ("bull", "bear", "range")
PRIOR = 30.0  # strength of the pull toward the broader rate (in "cases")
ANALOG_K = 100


@dataclass(frozen=True)
class Forecast:
    index: int
    probabilities: dict  # kind -> probability
    cases: int  # past cases the forecast rests on
    median_days: dict  # kind -> typical days until decided (from the cases), or None


@dataclass
class Context:
    """Everything a model needs, computed once."""
    frame: FeatureFrame
    outcomes: list  # Outcome | None per daily candle
    daily_trend: list[str]
    weekly_trend: list
    rows: list[list[float]] = field(default_factory=list)  # feature ranks - 0.5 per day
    usable: list[bool] = field(default_factory=list)


def build_context(frame: FeatureFrame, outcome_list, daily_trend, weekly_trend) -> Context:
    names = sorted(frame.ranks)
    n = len(frame.market.candles)
    rows = [[(frame.ranks[k][i] if frame.ranks[k][i] is not None else 0.5) - 0.5 for k in names] for i in range(n)]
    usable = [sum(frame.ranks[k][i] is not None for k in names) >= 0.6 * len(names) for i in range(n)]
    return Context(frame, outcome_list, daily_trend, weekly_trend, rows, usable)


def _rates(items: list[Outcome], prior: dict | None = None, strength: float = 0.0) -> dict:
    counts = {k: sum(o.kind == k for o in items) for k in KINDS}
    total = len(items)
    if prior is None:
        return {k: counts[k] / total if total else 1 / 3 for k in KINDS}
    return {k: (counts[k] + strength * prior[k]) / (total + strength) for k in KINDS}


def _median_days(items: list[Outcome]) -> dict:
    out = {}
    for k in KINDS:
        d = sorted(o.days for o in items if o.kind == k)
        out[k] = d[len(d) // 2] if d else None
    return out


def known_before(ctx: Context, cutoff: int) -> list[int]:
    """Days whose outcome was decided before candle `cutoff` (usable for learning at that time)."""
    return [i for i, o in enumerate(ctx.outcomes) if o is not None and o.decided_index < cutoff]


def predict(ctx: Context, i: int, train: list[int], model: str) -> Forecast:
    items = [ctx.outcomes[j] for j in train]
    base = _rates(items)
    if model == "base":
        return Forecast(i, base, len(items), _median_days(items))
    key = (ctx.daily_trend[i], ctx.weekly_trend[i])
    same = [ctx.outcomes[j] for j in train if (ctx.daily_trend[j], ctx.weekly_trend[j]) == key]
    structure = _rates(same, base, PRIOR)
    if model == "structure":
        return Forecast(i, structure, len(same), _median_days(same or items))
    x = ctx.rows[i]
    pool = [j for j in train if ctx.usable[j]]
    nearest = sorted(pool, key=lambda j: sum((a - b) ** 2 for a, b in zip(ctx.rows[j], x)))[:ANALOG_K]
    near = [ctx.outcomes[j] for j in nearest]
    return Forecast(i, _rates(near, structure, PRIOR), len(near), _median_days(near))


def _year_job(args):
    ctx, model, year = args
    times = [c.timestamp for c in ctx.frame.market.candles]
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    first = next((i for i, t in enumerate(times) if t >= start), len(times))
    train = known_before(ctx, first)
    if len(train) < 365:
        return []
    days = [i for i in range(first, len(times)) if times[i] < end and ctx.usable[i]]
    if model == "analog":
        train = train[::2]  # neighbours are similar day to day; halves the work
    return [predict(ctx, i, train, model) for i in days]


def walk_forward(ctx: Context, model: str, first_year: int = 2017, pool=None) -> list[Forecast]:
    last = ctx.frame.market.candles[-1].timestamp.year
    jobs = [(ctx, model, y) for y in range(first_year, last + 1)]
    results = pool.map(_year_job, jobs) if pool else map(_year_job, jobs)
    return [f for chunk in results for f in chunk]


@dataclass(frozen=True)
class Score:
    n: int
    brier: float
    log_loss: float
    calibration: dict  # kind -> [(mean predicted, observed share, days)]


def score(ctx: Context, forecasts: list[Forecast]) -> Score | None:
    known = [f for f in forecasts if ctx.outcomes[f.index] is not None]
    if not known:
        return None
    brier = ll = 0.0
    calibration = {}
    for f in known:
        actual = ctx.outcomes[f.index].kind
        brier += sum((f.probabilities[k] - (k == actual)) ** 2 for k in KINDS)
        ll -= math.log(max(f.probabilities[actual], 1e-6))
    for k in KINDS:
        buckets: dict = {}
        for f in known:
            buckets.setdefault(min(int(f.probabilities[k] * 10), 9), []).append(f)
        calibration[k] = [
            (sum(f.probabilities[k] for f in b) / len(b),
             sum(ctx.outcomes[f.index].kind == k for f in b) / len(b), len(b))
            for _, b in sorted(buckets.items())
        ]
    return Score(len(known), brier / len(known), ll / len(known), calibration)


def current_forecast(ctx: Context, model: str) -> Forecast:
    """Forecast for the latest close, learning from every outcome decided so far."""
    i = len(ctx.frame.market.candles) - 1
    train = known_before(ctx, i + 1)
    return predict(ctx, i, train, model)


def weekly_trend_on_days(candles, weekly_candles, weekly_trend) -> list:
    """Weekly structure trend known at each daily close (completed weeks only)."""
    out, k = [], -1
    for c in candles:
        close = c.timestamp + timedelta(days=1)
        while k + 1 < len(weekly_candles) and weekly_candles[k + 1].timestamp + timedelta(days=7) <= close:
            k += 1
        out.append(weekly_trend[k] if k >= 0 else None)
    return out
