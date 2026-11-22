"""
Machine-learning models for the research (standard library only).

Two questions, each answered with a probability per day:
  "up30":  will the price be higher 30 days from this close?
  "low20": will a swing low (found with hindsight, zigzag) happen within the
           next 20 days?  (the owner's question: can we see a low coming?)

Inputs: the percentile ranks of every research feature (known at the
close; missing = 0.5, the middle).

Models:
  logistic   logistic regression with L2 regularisation (the classic,
             readable model: one weight per feature)
  analog     nearest-neighbour "analog" forecast: find the 75 past days whose
             feature ranks looked most like today, and use how often the
             answer was yes after those days (less standard: no formula,
             history itself is the model)

Honest testing: walk-forward by year. For test year Y the model learns only
from days whose answer was already known before 1 January of Y (a purge gap
of the horizon), then predicts every day of Y. Every prediction is kept
with its date (CLAUDE.md: predictions are stored, never rewritten) and
scored with the Brier score and log loss against the simple base rate, and
a calibration table.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from src.research.features import FeatureFrame


@dataclass(frozen=True)
class Prediction:
    index: int
    time: datetime
    probability: float
    outcome: int | None  # None: not known yet (the latest days)


def labels_up(frame: FeatureFrame, horizon: int = 30) -> list[int | None]:
    c = frame.market.candles
    out: list[int | None] = []
    for i in range(len(c)):
        j = i + horizon
        if j < len(c) and (c[j].timestamp - c[i].timestamp).days == horizon:
            out.append(int(c[j].close > c[i].close))
        else:
            out.append(None)
    return out


def labels_low(frame: FeatureFrame, turns, horizon: int = 20) -> list[int | None]:
    n = len(frame.market.candles)
    out: list[int | None] = [0] * n
    for t in turns:
        if t.kind == "low":
            for k in range(max(0, t.index - horizon), t.index + 1):
                out[k] = 1
    # the last days cannot be judged yet: a low there may still be confirmed later
    for k in range(max(0, n - horizon - 60), n):
        out[k] = None
    return out


def feature_matrix(frame: FeatureFrame) -> tuple[list[str], list[list[float]]]:
    names = sorted(frame.ranks)
    n = len(frame.market.candles)
    rows = [[(frame.ranks[name][i] if frame.ranks[name][i] is not None else 0.5) - 0.5 for name in names]
            for i in range(n)]
    return names, rows


def usable(frame: FeatureFrame, min_known: float = 0.6) -> list[bool]:
    """Days with at least `min_known` of the features ranked (not imputed)."""
    names = list(frame.ranks)
    n = len(frame.market.candles)
    return [sum(frame.ranks[k][i] is not None for k in names) >= min_known * len(names) for i in range(n)]


def fit_logistic(rows: list[list[float]], ys: list[int], l2: float = 1.0, iterations: int = 150,
                 rate: float = 0.5) -> list[float]:
    """Weights (bias last) by full-batch gradient descent."""
    d = len(rows[0])
    w = [0.0] * (d + 1)
    n = len(rows)
    for _ in range(iterations):
        grad = [0.0] * (d + 1)
        for x, y in zip(rows, ys):
            z = w[d] + sum(wi * xi for wi, xi in zip(w, x))
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
            e = p - y
            for k in range(d):
                grad[k] += e * x[k]
            grad[d] += e
        for k in range(d):
            w[k] -= rate * (grad[k] / n + l2 * w[k] / n)
        w[d] -= rate * grad[d] / n
    return w


def predict_logistic(w: list[float], x: list[float]) -> float:
    z = w[-1] + sum(wi * xi for wi, xi in zip(w, x))
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def predict_analog(train_rows, train_ys, x, k: int = 75) -> float:
    distances = sorted(
        (sum((a - b) ** 2 for a, b in zip(row, x)), y) for row, y in zip(train_rows, train_ys)
    )[:k]
    # shrink toward the base rate a little (k small = noisy)
    base = sum(train_ys) / len(train_ys)
    return (sum(y for _, y in distances) + 5 * base) / (len(distances) + 5)


def labels_low_known_before(frame: FeatureFrame, cutoff: int, threshold: float = 0.20,
                            horizon: int = 20) -> list[int | None]:
    """
    "A swing low within `horizon` days", using only the lows that were
    CONFIRMED by candle `cutoff` (a low needs a later rise to be known).
    Days whose answer could still change after the cutoff are None.
    """
    from src.research.turning_points import zigzag

    c = frame.market.candles[:cutoff]
    turns = zigzag([x.close for x in c], [x.timestamp for x in c], threshold)
    out: list[int | None] = [0] * len(frame.market.candles)
    for t in turns:
        if t.kind == "low":
            for k in range(max(0, t.index - horizon), t.index + 1):
                out[k] = 1
    # after the last confirmed turn nothing is settled yet
    last_settled = turns[-1].index if turns else 0
    for k in range(last_settled + 1, len(out)):
        out[k] = None
    return out


def _year_job(args):
    model, rows, labels, ok, times, year, horizon = args
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    if callable(labels):  # labels that depend on what was known at the start of the year
        labels = labels(next((i for i, t in enumerate(times) if t >= start), len(times)))
    train = [i for i in range(len(rows))
             if ok[i] and labels[i] is not None and i + horizon < len(times) and times[i + horizon] < start]
    test = [i for i in range(len(rows)) if ok[i] and start <= times[i] < end]
    if len(train) < 500 or not test:
        return []
    xs = [rows[i] for i in train]
    ys = [labels[i] for i in train]
    if model == "logistic":
        w = fit_logistic(xs, ys)
        return [(i, predict_logistic(w, rows[i])) for i in test]
    # analog: thin the training set for speed (every 2nd day; neighbours are similar anyway)
    xs2, ys2 = xs[::2], ys[::2]
    return [(i, predict_analog(xs2, ys2, rows[i])) for i in test]


def walk_forward_predictions(frame: FeatureFrame, labels, model: str, horizon: int,
                             first_year: int = 2017, pool=None, outcomes: list[int | None] | None = None
                             ) -> list[Prediction]:
    """`labels`: a list, or a function(cutoff index) -> list for point-in-time labels.
    `outcomes`: the final answers used for scoring (default: `labels`)."""
    _, rows = feature_matrix(frame)
    ok = usable(frame)
    times = [c.timestamp for c in frame.market.candles]
    last_year = times[-1].year
    jobs = [(model, rows, labels, ok, times, y, horizon) for y in range(first_year, last_year + 1)]
    results = pool.map(_year_job, jobs) if pool else map(_year_job, jobs)
    final = outcomes if outcomes is not None else labels
    out = []
    for chunk in results:
        for i, p in chunk:
            out.append(Prediction(i, times[i], p, final[i]))
    return out


@dataclass(frozen=True)
class Score:
    n: int
    base_rate: float
    brier: float
    brier_base: float  # always predicting the training base rate
    log_loss: float
    log_loss_base: float
    calibration: list[tuple[float, float, int]]  # (mean predicted, observed share, days) per bucket

    @property
    def skill(self) -> float:
        """Brier skill score: 1 = perfect, 0 = no better than the base rate, < 0 = worse."""
        return 1 - self.brier / self.brier_base if self.brier_base > 0 else 0.0


def score(predictions: list[Prediction], base_rate: float) -> Score | None:
    known = [p for p in predictions if p.outcome is not None]
    if not known:
        return None
    eps = 1e-6

    def ll(p, y):
        p = min(max(p, eps), 1 - eps)
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))

    brier = sum((p.probability - p.outcome) ** 2 for p in known) / len(known)
    brier_base = sum((base_rate - p.outcome) ** 2 for p in known) / len(known)
    log_loss = sum(ll(p.probability, p.outcome) for p in known) / len(known)
    log_loss_base = sum(ll(base_rate, p.outcome) for p in known) / len(known)
    buckets: dict[int, list[Prediction]] = {}
    for p in known:
        buckets.setdefault(min(int(p.probability * 10), 9), []).append(p)
    calibration = [
        (sum(p.probability for p in b) / len(b), sum(p.outcome for p in b) / len(b), len(b))
        for _, b in sorted(buckets.items())
    ]
    return Score(len(known), base_rate, brier, brier_base, log_loss, log_loss_base, calibration)


def exposure_from_probability(predictions: list[Prediction], n: int, low: float, high: float,
                              core: float = 0.0) -> list[float | None]:
    """Hold (core..100%) with hysteresis: buy above `high`, sell below `low`, otherwise keep."""
    by_index = {p.index: p.probability for p in predictions}
    out: list[float | None] = []
    holding = False
    for i in range(n):
        p = by_index.get(i)
        if p is None:
            out.append(None)
            continue
        if p >= high:
            holding = True
        elif p <= low:
            holding = False
        out.append(core + (1 - core) * (1.0 if holding else 0.0))
    return out
