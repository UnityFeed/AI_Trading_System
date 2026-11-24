"""
Pattern-learning experts for the learning engine (needs numpy, scikit-learn
and LightGBM; owner approved libraries 24 Nov 2026).

  trees   gradient-boosted decision trees (LightGBM): learn COMBINATIONS of
          conditions ("RSI low AND weekly trend up AND near support"), which
          the online linear "learned" expert cannot.
  analog  the most similar past situations (k nearest neighbours on the same
          features): what happened next in the 200 closest cases.

Both are kept deliberately cautious (shallow trees, many cases per leaf,
many neighbours): a first, freer version (15 leaves, 50 neighbours) was
overconfident and scored far below the plain base rate on its own.

Both are walk-forward: every `retrain_days` the model is rebuilt from the
outcomes KNOWN at that candle's close (decided by then), and used for the
following candles until the next rebuild. Nothing from later is ever used.
The result is one probability dict per candle (None before enough outcomes
are known), handed to `learner.replay` as extra experts; the blend learns how
much to trust them, like any other expert.
"""

import numpy as np

from src.analysis.timeframes import TIMEFRAME_HOURS

KINDS = ("bull", "bear", "range")
NAMES = ("trees", "analog")


def available() -> bool:
    try:
        import lightgbm  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError:
        return False
    return True


def _labels(outcome_list) -> np.ndarray:
    return np.array([-1 if o is None else KINDS.index(o.kind) for o in outcome_list], dtype=np.int64)


TREES = {"n_estimators": 80, "learning_rate": 0.03, "num_leaves": 4, "min_child_samples": 300}
NEIGHBOURS = 200


def walk_forward_experts(rows, outcome_list, timeframe: str, retrain_days: int = 30, min_examples: int = 300,
                         names=NAMES, max_train: int = 60000, seed: int = 7, trees: dict | None = None,
                         neighbours: int | None = None) -> dict[str, list]:
    """Per candle {expert: probabilities or None}, each from a model trained only on outcomes known by then."""
    from lightgbm import LGBMClassifier
    from sklearn.neighbors import KNeighborsClassifier

    X = np.asarray(rows, dtype=np.float64)
    y = _labels(outcome_list)
    n = len(y)
    decided = np.array([np.inf if o is None else o.decided_index for o in outcome_list])
    every = max(1, round(retrain_days * 24 / TIMEFRAME_HOURS[timeframe]))
    out = {name: [None] * n for name in names}
    rng = np.random.default_rng(seed)
    for start in range(0, n, every):
        known = np.flatnonzero(decided <= start)  # outcomes known at this close
        if len(known) < min_examples or len(set(y[known])) < 3:
            continue
        if len(known) > max_train:  # all recent ones + a random sample of older ones
            half = max_train // 2
            older = rng.choice(known[:-half], max_train - half, replace=False)
            known = np.sort(np.concatenate([older, known[-half:]]))
        end = min(n, start + every)
        Xq = X[start:end]
        if "trees" in names:
            settings = dict(TREES, **(trees or {}))
            settings["min_child_samples"] = min(settings["min_child_samples"], max(20, len(known) // 10))
            model = LGBMClassifier(**settings, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                                   random_state=seed, deterministic=True, n_jobs=1, verbose=-1)
            model.fit(X[known], y[known])
            p = _ordered(model.predict_proba(Xq), model.classes_)
            for i, row in zip(range(start, end), p):
                out["trees"][i] = dict(zip(KINDS, map(float, row)))
        if "analog" in names:
            k = min(neighbours or NEIGHBOURS, len(known))
            knn = KNeighborsClassifier(n_neighbors=k, weights="distance", algorithm="auto")
            knn.fit(X[known], y[known])
            p = _ordered(knn.predict_proba(Xq), knn.classes_)
            p = (p * k + 1.0) / (k + 3.0)  # a little smoothing: never exactly 0 or 1
            for i, row in zip(range(start, end), p):
                out["analog"][i] = dict(zip(KINDS, map(float, row)))
    return out


def _ordered(p: np.ndarray, classes) -> np.ndarray:
    full = np.zeros((len(p), 3))
    for col, c in enumerate(classes):
        full[:, int(c)] = p[:, col]
    return full
