"""
The learning engine ("the AI"): it walks through the history one day at a
time, as if it were living it.

Every day, at the daily close:
  1. it LEARNS from every outcome that became known that day (a forecast's
     target or stop was reached, or its horizon passed): it updates its own
     model, and it scores each of its experts on the forecasts they made back
     then;
  2. it PREDICTS bull / bear / range for each horizon (7, 14, 30 days), using
     only what was known at that close (nothing from later days exists for it).

Experts (each gives three probabilities):
  base       how often each outcome happened so far
  structure  the same, for days with the same daily + weekly market structure
  regime     the same, for days with the same ADX regime (trending / ranging)
             and structure
  learned    an online softmax (multinomial logistic) model over every chart
             feature: indicators, weekly chart, cycle, on-chain, market
             structure, support/resistance distance, Fibonacci position, ADX
             and the chart patterns, updated by gradient descent each time an
             outcome becomes known

The final forecast blends the experts. Their weights are LEARNED with the
"Hedge" rule: an expert's weight shrinks with every forecast it got wrong
(its log loss), with slow forgetting so the blend adapts when the market
changes character. This is how it learns "the best combination".

A replay from the first day gives every day's forecast as it was made then,
and a learning curve: how its score developed over the years.
"""

import math
import random
from dataclasses import dataclass, field

from src.backtesting.market import Market
from src.predictive_engine.levels import adx, fibonacci, support_resistance
from src.predictive_engine.outcomes import outcomes
from src.predictive_engine.patterns import detect_patterns, pattern_features, swings_known_over_time
from src.predictive_engine.scenarios import weekly_trend_on_days
from src.predictive_engine.structure import analyse
from src.research.features import FeatureFrame, build_frame, expanding_rank, weekly_from_daily


KINDS = ("bull", "bear", "range")
HORIZONS = (7, 14, 30)
EXPERTS = ("base", "structure", "regime", "learned")
VERSION = "learner-v2"
PRIOR = 30.0
ETA = 0.1  # how fast Hedge weights react to an expert's log loss
FORGET = 0.999  # weight memory per learned outcome (old mistakes slowly forgiven)
SHARE = 0.05  # every expert keeps at least this share of the blend ("fixed share")
LEARNING_RATE = 0.01
L2 = 1e-3


def chart_features(market: Market, structure=None, patterns=None) -> dict[str, list]:
    """Chart tools as daily features known at each close: ADX, support/resistance distance, Fibonacci, patterns."""
    c = market.candles
    n = len(c)
    structure = structure or analyse(c, "1d")
    a = adx(c)
    near_support: list = [None] * n
    near_resistance: list = [None] * n
    fib_position: list = [None] * n
    # the swing list exactly as it was known at each close (a swing can later be
    # replaced by a more extreme one; the final list would leak that)
    for i, known, _ in swings_known_over_time(c, "1d"):
        price = c[i].close
        zones = support_resistance(known, price, i, lookback=365)
        below = [z.high for z in zones if z.kind == "support"]
        above = [z.low for z in zones if z.kind == "resistance"]
        near_support[i] = price / max(below) - 1 if below else None
        near_resistance[i] = min(above) / price - 1 if above else None
        fib = fibonacci(known, i)
        if fib and fib.end != fib.start:
            fib_position[i] = (price - fib.start) / (fib.end - fib.start)
    out = {
        "chart.adx": a,
        "chart.dist_support": near_support,
        "chart.dist_resistance": near_resistance,
        "chart.fib_position": fib_position,
    }
    for name, values in pattern_features(patterns if patterns is not None else detect_patterns(c, "1d"), n).items():
        out[name] = [min(v, 1.0) for v in values]
    return out


@dataclass
class Replay:
    horizon: int
    forecasts: list  # per day: dict kind -> probability, or None
    experts: list  # per day: {expert: probabilities} or None
    weights: list  # per day: {expert: weight} or None
    outcomes: list  # Outcome | None per day
    learning_curve: list = field(default_factory=list)  # (year, days scored, brier, base brier)


def _softmax(z):
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v / s for v in e]


def _log_loss(p: dict, kind: str) -> float:
    return -math.log(max(p[kind], 1e-6))


def _counts_rates(counts: dict, prior: dict | None) -> dict:
    total = sum(counts.values())
    if prior is None:
        return {k: counts[k] / total if total else 1 / 3 for k in KINDS}
    return {k: (counts[k] + PRIOR * prior[k]) / (total + PRIOR) for k in KINDS}


def build_inputs(market: Market, frame: FeatureFrame | None = None):
    """Feature rows (ranks - 0.5) and the context keys used by the experts."""
    frame = frame or build_frame(market)
    c = market.candles
    structure = analyse(c, "1d")
    weekly_candles = weekly_from_daily(c)
    weekly = weekly_trend_on_days(c, weekly_candles, analyse(weekly_candles, "1w").trend)
    extra = chart_features(market, structure)
    ranks = dict(frame.ranks)
    for name, values in extra.items():
        ranks[name] = values if name.startswith("pattern.") else expanding_rank(values)
    names = sorted(ranks)
    rows = []
    for i in range(len(c)):
        row = []
        for name in names:
            v = ranks[name][i]
            row.append(0.0 if v is None else (v - 0.5 if not name.startswith("pattern.") else v))
        rows.append(row)
    a = extra["chart.adx"]
    regime = ["trend" if v is not None and v >= 25 else ("range" if v is not None and v < 20 else "mixed") for v in a]
    keys = {
        "structure": list(zip(structure.trend, weekly)),
        "regime": list(zip(regime, structure.trend, weekly)),
    }
    return names, rows, keys


def replay(market: Market, horizon: int, names, rows, keys, seed: int = 7) -> Replay:
    """Walk forward day by day: learn from what became known, then predict."""
    n = len(market.candles)
    out = outcomes(market, horizon, k=1.0)
    decided_on: dict[int, list[int]] = {}
    for i, o in enumerate(out):
        if o is not None:
            decided_on.setdefault(o.decided_index, []).append(i)

    d = len(names)
    w = [[0.0] * (d + 1) for _ in KINDS]  # softmax weights (+ bias) per outcome
    counts_all = {k: 0 for k in KINDS}
    counts_by = {name: {} for name in keys}
    loss = {e: 0.0 for e in EXPERTS}
    learned_examples: list[int] = []
    rng = random.Random(seed)
    forecasts: list = [None] * n
    experts_out: list = [None] * n
    weights_out: list = [None] * n

    def learned_probs(x):
        return dict(zip(KINDS, _softmax([wk[d] + sum(a * b for a, b in zip(wk, x)) for wk in w])))

    def sgd(i):
        x, y = rows[i], out[i].kind
        p = learned_probs(x)
        for c_index, kind in enumerate(KINDS):
            g = p[kind] - (kind == y)
            wk = w[c_index]
            for j in range(d):
                wk[j] -= LEARNING_RATE * (g * x[j] + L2 * wk[j])
            wk[d] -= LEARNING_RATE * g

    for i in range(n):
        # 1. learn from outcomes that became known at this close
        for j in decided_on.get(i, []):
            o = out[j]
            if experts_out[j] is not None:  # score the experts on what they said back then
                for e in EXPERTS:
                    loss[e] = loss[e] * FORGET + _log_loss(experts_out[j][e], o.kind)
            counts_all[o.kind] += 1
            for name, key in keys.items():
                counts_by[name].setdefault(key[j], {k: 0 for k in KINDS})[o.kind] += 1
            sgd(j)
            learned_examples.append(j)
            if len(learned_examples) > 1:  # rehearse one older example as well
                sgd(learned_examples[rng.randrange(len(learned_examples) - 1)])
        # 2. predict at this close
        if sum(counts_all.values()) < 60:
            continue
        base = _counts_rates(counts_all, None)
        structure = _counts_rates(counts_by["structure"].get(keys["structure"][i], {k: 0 for k in KINDS}), base)
        regime = _counts_rates(counts_by["regime"].get(keys["regime"][i], {k: 0 for k in KINDS}), structure)
        learned = learned_probs(rows[i])
        # the learned model is pulled toward the base rate while it has seen few outcomes
        seen = len(learned_examples)
        trust = seen / (seen + 500.0)
        learned = {k: trust * learned[k] + (1 - trust) * base[k] for k in KINDS}
        experts = {"base": base, "structure": structure, "regime": regime, "learned": learned}
        low = min(loss.values())
        raw = {e: math.exp(-ETA * (loss[e] - low)) for e in EXPERTS}
        total = sum(raw.values())
        weights = {e: SHARE / len(EXPERTS) + (1 - SHARE) * raw[e] / total for e in EXPERTS}
        final = {k: sum(weights[e] * experts[e][k] for e in EXPERTS) for k in KINDS}
        forecasts[i], experts_out[i], weights_out[i] = final, experts, weights

    result = Replay(horizon, forecasts, experts_out, weights_out, out)
    result.learning_curve = learning_curve(result, market)
    return result


def brier(p: dict, kind: str) -> float:
    return sum((p[k] - (k == kind)) ** 2 for k in KINDS)


def learning_curve(r: Replay, market: Market) -> list[tuple]:
    """Per year: days scored, the engine's Brier score and the base expert's (lower is better)."""
    years: dict = {}
    for i, (p, o) in enumerate(zip(r.forecasts, r.outcomes)):
        if p is None or o is None:
            continue
        y = market.candles[i].timestamp.year
        acc = years.setdefault(y, [0, 0.0, 0.0])
        acc[0] += 1
        acc[1] += brier(p, o.kind)
        acc[2] += brier(r.experts[i]["base"], o.kind)
    return [(y, a[0], a[1] / a[0], a[2] / a[0]) for y, a in sorted(years.items())]
