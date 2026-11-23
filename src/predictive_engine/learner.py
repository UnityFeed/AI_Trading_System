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

from src.analysis.timeframes import TIMEFRAME_HOURS
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
VERSION = "learner-v3"
PRIOR = 30.0
ETA = 0.1  # how fast Hedge weights react to an expert's log loss
FORGET = 0.999  # weight memory per learned outcome (old mistakes slowly forgiven)
SHARE = 0.05  # every expert keeps at least this share of the blend ("fixed share")
LEARNING_RATE = 0.01
L2 = 1e-3

# Horizons in candles per timeframe (about 1 day / 3 days / 1 week on 1h,
# 1 day / 1 week / 2 weeks on 4h, 1 / 2 weeks and 1 month on 1d)
TF_HORIZONS = {"1h": (24, 72, 168), "4h": (6, 42, 84), "1d": HORIZONS}


@dataclass(frozen=True)
class Config:
    """One version of the learning engine's settings."""
    name: str = "default"
    learning_rate: float = LEARNING_RATE
    l2: float = L2
    eta: float = ETA
    forget: float = FORGET
    share: float = SHARE
    restudy_days: int = 0  # days between deep re-studies of the known outcomes (0 = never)
    restudy_epochs: int = 2  # passes over the study set per re-study
    max_study: int = 3000  # examples per re-study: the most recent half + a random older half
    calibrate: bool = False  # self-correction learned from its own decided forecasts
    cal_bins: int = 10
    cal_prior: float = 50.0


# The 10 versions the training session compares; each year it uses the one
# that scored best on the EARLIER years only (nested walk-forward).
CONFIGS = (
    Config("default"),
    Config("calibrated", calibrate=True),
    Config("restudy", restudy_days=30),
    Config("restudy+calibrated", restudy_days=30, calibrate=True),
    Config("slow learner", learning_rate=0.003, l2=3e-3),
    Config("fast learner", learning_rate=0.03, l2=3e-4),
    Config("fast blend", eta=0.3, forget=0.995),
    Config("slow blend", eta=0.03, forget=0.9995),
    Config("restudy weekly, deep", restudy_days=7, restudy_epochs=3, calibrate=True),
    Config("fast learner, restudy, calibrated", learning_rate=0.03, l2=3e-4, restudy_days=30, calibrate=True),
)


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
    forecasts: list  # per candle: dict kind -> probability (after self-correction), or None
    experts: list  # per candle: {expert: probabilities} or None
    weights: list  # per candle: {expert: weight} or None
    outcomes: list  # Outcome | None per candle
    learning_curve: list = field(default_factory=list)  # (year, scored, brier, base brier)
    raw: list = field(default_factory=list)  # per candle: the blend BEFORE self-correction
    config: Config = field(default_factory=Config)
    state: dict = field(default_factory=dict)  # learned model at the end (for a memorised extra pass)


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


class Calibrator:
    """
    Self-correction: for each outcome, in bins of the probability it gave,
    how often that outcome then really happened. Learns only from forecasts
    whose outcome is known; pulled toward "no correction" while a bin is thin.
    """

    def __init__(self, bins: int = 10, prior: float = 50.0):
        self.bins, self.prior = bins, prior
        self.count = {k: [0] * bins for k in KINDS}
        self.hits = {k: [0] * bins for k in KINDS}
        self.sum_p = {k: [0.0] * bins for k in KINDS}

    def _bin(self, p: float) -> int:
        return min(self.bins - 1, int(p * self.bins))

    def learn(self, p: dict, kind: str) -> None:
        for k in KINDS:
            b = self._bin(p[k])
            self.count[k][b] += 1
            self.hits[k][b] += k == kind
            self.sum_p[k][b] += p[k]

    def apply(self, p: dict) -> dict:
        out = {}
        for k in KINDS:
            b = self._bin(p[k])
            n = self.count[k][b]
            # observed rate in this bin, shifted to this forecast's own probability
            shift = (self.hits[k][b] - self.sum_p[k][b]) / (n + self.prior)
            out[k] = min(0.99, max(0.01, p[k] + shift))
        total = sum(out.values())
        return {k: v / total for k, v in out.items()}


def replay(market: Market, horizon: int, names, rows, keys, seed: int = 7, config: Config | None = None,
           outcome_list: list | None = None, start_state: dict | None = None) -> Replay:
    """
    Walk forward candle by candle: learn from what became known, then predict.

    `start_state` (a previous replay's `state`) starts the learned model with
    everything it learned on an earlier pass over the SAME chart: that pass's
    scores are memorised, not honest (see `passes`).
    """
    config = config or Config()
    n = len(market.candles)
    out = outcome_list if outcome_list is not None else outcomes(market, horizon, k=1.0)
    decided_on: dict[int, list[int]] = {}
    for i, o in enumerate(out):
        if o is not None:
            decided_on.setdefault(o.decided_index, []).append(i)

    d = len(names)
    w = [list(row) for row in start_state["w"]] if start_state else [[0.0] * (d + 1) for _ in KINDS]
    earlier_seen = start_state["seen"] if start_state else 0
    counts_all = {k: 0 for k in KINDS}
    counts_by = {name: {} for name in keys}
    loss = {e: 0.0 for e in EXPERTS}
    learned_examples: list[int] = []
    rng = random.Random(seed)
    calibrator = Calibrator(config.cal_bins, config.cal_prior) if config.calibrate else None
    forecasts: list = [None] * n
    raw_out: list = [None] * n
    experts_out: list = [None] * n
    weights_out: list = [None] * n
    lr, l2 = config.learning_rate, config.l2

    def learned_probs(x):
        return dict(zip(KINDS, _softmax([wk[d] + sum(a * b for a, b in zip(wk, x)) for wk in w])))

    def sgd(i):
        x, y = rows[i], out[i].kind
        p = learned_probs(x)
        for c_index, kind in enumerate(KINDS):
            g = p[kind] - (kind == y)
            wk = w[c_index]
            for j in range(d):
                wk[j] -= lr * (g * x[j] + l2 * wk[j])
            wk[d] -= lr * g

    def restudy():
        """Go over the known outcomes again: the most recent half and a random older half, several times."""
        known = learned_examples
        half = config.max_study // 2
        study = known[-half:]
        older = known[:-half]
        if older:
            study = study + rng.sample(older, min(len(older), config.max_study - len(study)))
        for _ in range(config.restudy_epochs):
            rng.shuffle(study)
            for j in study:
                sgd(j)

    last_restudy = 0
    restudy_every = round(config.restudy_days * 24 / TIMEFRAME_HOURS[market.timeframe])
    for i in range(n):
        # 1. learn from outcomes that became known at this close
        for j in decided_on.get(i, []):
            o = out[j]
            if experts_out[j] is not None:  # score the experts on what they said back then
                for e in EXPERTS:
                    loss[e] = loss[e] * config.forget + _log_loss(experts_out[j][e], o.kind)
            if calibrator is not None and raw_out[j] is not None:
                calibrator.learn(raw_out[j], o.kind)
            counts_all[o.kind] += 1
            for name, key in keys.items():
                counts_by[name].setdefault(key[j], {k: 0 for k in KINDS})[o.kind] += 1
            sgd(j)
            learned_examples.append(j)
            if len(learned_examples) > 1:  # rehearse one older example as well
                sgd(learned_examples[rng.randrange(len(learned_examples) - 1)])
        if restudy_every and learned_examples and i - last_restudy >= restudy_every:
            restudy()
            last_restudy = i
        # 2. predict at this close
        if sum(counts_all.values()) < 60:
            continue
        base = _counts_rates(counts_all, None)
        structure = _counts_rates(counts_by["structure"].get(keys["structure"][i], {k: 0 for k in KINDS}), base)
        regime = _counts_rates(counts_by["regime"].get(keys["regime"][i], {k: 0 for k in KINDS}), structure)
        learned = learned_probs(rows[i])
        # the learned model is pulled toward the base rate while it has seen few outcomes
        seen = len(learned_examples) + earlier_seen
        trust = seen / (seen + 500.0)
        learned = {k: trust * learned[k] + (1 - trust) * base[k] for k in KINDS}
        experts = {"base": base, "structure": structure, "regime": regime, "learned": learned}
        low = min(loss.values())
        raw = {e: math.exp(-config.eta * (loss[e] - low)) for e in EXPERTS}
        total = sum(raw.values())
        weights = {e: config.share / len(EXPERTS) + (1 - config.share) * raw[e] / total for e in EXPERTS}
        blend = {k: sum(weights[e] * experts[e][k] for e in EXPERTS) for k in KINDS}
        raw_out[i] = blend
        forecasts[i] = calibrator.apply(blend) if calibrator is not None else blend
        experts_out[i], weights_out[i] = experts, weights

    result = Replay(horizon, forecasts, experts_out, weights_out, out, raw=raw_out, config=config,
                    state={"w": w, "seen": len(learned_examples) + earlier_seen})
    result.learning_curve = learning_curve(result, market)
    return result


def passes(market: Market, horizon: int, names, rows, keys, config: Config | None = None,
           count: int = 2, outcome_list: list | None = None) -> list[Replay]:
    """
    The honest pass plus `count - 1` MEMORISED passes over the same chart:
    each extra pass starts with the model the previous pass ended with, so it
    has already seen every outcome it is now asked about. Its score shows how
    much memory inflates the result; it is never used for the chart or the log.
    """
    out = outcome_list if outcome_list is not None else outcomes(market, horizon, k=1.0)
    result = [replay(market, horizon, names, rows, keys, config=config, outcome_list=out)]
    for _ in range(count - 1):
        result.append(replay(market, horizon, names, rows, keys, config=config, outcome_list=out,
                             start_state=result[-1].state))
    return result


def yearly_brier(r: Replay, market: Market) -> dict[int, tuple[int, float, float]]:
    """year -> (scored, sum of Brier, sum of base Brier)."""
    years: dict = {}
    for i, (p, o) in enumerate(zip(r.forecasts, r.outcomes)):
        if p is None or o is None:
            continue
        acc = years.setdefault(market.candles[i].timestamp.year, [0, 0.0, 0.0])
        acc[0] += 1
        acc[1] += brier(p, o.kind)
        acc[2] += brier(r.experts[i]["base"], o.kind)
    return {y: tuple(a) for y, a in years.items()}


def choose_by_year(per_year: list[dict], names: list[str]) -> tuple[dict, list[dict]]:
    """
    Honest choice between setting versions (nested walk-forward): for every
    year, the version with the best Brier skill over the EARLIER years only
    (the first scored year uses the first version). `per_year[k]` is
    `yearly_brier` of version k. Returns {year: version index} and a table.
    """
    years = sorted(set().union(*per_year)) if per_year else []
    chosen: dict[int, int] = {}
    table = []
    for y in years:
        best, best_skill = 0, None
        for k, yb in enumerate(per_year):
            before = [v for yy, v in yb.items() if yy < y]
            if not before or not sum(v[2] for v in before):
                continue
            s_ = 1 - sum(v[1] for v in before) / sum(v[2] for v in before)
            if best_skill is None or s_ > best_skill:
                best, best_skill = k, s_
        chosen[y] = best
        this = per_year[best].get(y)
        table.append({"year": y, "config": names[best],
                      "skill_before": None if best_skill is None else round(best_skill, 4),
                      "skill_this_year": None if not this or not this[2] else round(1 - this[1] / this[2], 4)})
    return chosen, table


def chain(replays: dict[int, Replay], chosen: dict[int, int], market: Market) -> Replay:
    """One replay made of, for each year, the forecasts of the version chosen for that year."""
    n = len(market.candles)
    first = next(iter(replays.values()))
    out = Replay(first.horizon, [None] * n, [None] * n, [None] * n, first.outcomes, raw=[None] * n,
                 config=Config("nested choice"))
    for i in range(n):
        r = replays.get(chosen.get(market.candles[i].timestamp.year, 0), first)
        out.forecasts[i], out.experts[i], out.weights[i] = r.forecasts[i], r.experts[i], r.weights[i]
        out.raw[i] = r.raw[i] if r.raw else None
    out.learning_curve = learning_curve(out, market)
    return out


def nested_selection(replays: list[Replay], market: Market) -> tuple[Replay, list[dict]]:
    chosen, table = choose_by_year([yearly_brier(r, market) for r in replays], [r.config.name for r in replays])
    return chain(dict(enumerate(replays)), chosen, market), table


def skill(r: Replay, market: Market, from_year: int = 0) -> dict:
    """Brier skill vs the base rate, log loss skill and top-scenario hit rate over decided forecasts."""
    n = b = bb = ll = llb = hits = 0.0
    for i, (p, o) in enumerate(zip(r.forecasts, r.outcomes)):
        if p is None or o is None or market.candles[i].timestamp.year < from_year:
            continue
        base = r.experts[i]["base"]
        n += 1
        b += brier(p, o.kind)
        bb += brier(base, o.kind)
        ll += _log_loss(p, o.kind)
        llb += _log_loss(base, o.kind)
        hits += max(p, key=p.get) == o.kind
    if not n:
        return {"scored": 0}
    return {"scored": int(n), "brier_skill": 1 - b / bb, "logloss_skill": 1 - ll / llb, "top_hit_rate": hits / n}


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
