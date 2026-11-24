"""
Training session for the learning engine on every timeframe (1h, 4h, 1d).

For each timeframe and horizon:
  1. the 10 setting versions (`learner.CONFIGS`) each replay the whole chart
     honestly, candle by candle;
  2. for every year, the version with the best score on the EARLIER years is
     used (nested walk-forward); chained together this is the honest result
     the app shows and logs;
  3. MEMORISED passes: the version used now goes over the same chart again,
     starting with everything it learned on the first pass. Their scores show
     how much memory inflates a result; they are reported only.

The result is saved to `data/predictive/engine_cache.pkl` (gitignored), so
the app starts with the trained forecasts, plus one CSV per timeframe and
horizon with every forecast as it was made ("remembered readings").
"""

import csv
import math
import os
import pickle
from array import array
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting.market import Market, build_market
from src.predictive_engine import learner, ml_experts, mtf
from src.predictive_engine.outcomes import outcomes


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "predictive"
CACHE_FILE = CACHE_DIR / "engine_cache.pkl"
TIMEFRAMES = ("1d", "4h", "1h")
NAN = float("nan")


def load_markets(history, tables=None, external=None) -> dict[str, Market]:
    tables = tables or {}
    return {tf: build_market(history, tf, table=tables.get(tf), external=external if tf == "1d" else None)
            for tf in ("1h", "4h", "1d", "1w")}


def load_coin_markets(repository=None) -> dict:
    """{coin: {tf: Market}} of the stored training coins (database/training_coins.db)."""
    from src.data_collection.training_coins import coin_histories
    return {coin: load_markets(history) for coin, history in coin_histories(repository).items()}


def inputs_for(markets: dict[str, Market], timeframe: str):
    """The daily chart uses the rich research features; 1h/4h use the multi-timeframe inputs."""
    if timeframe == "1d":
        return learner.build_inputs(markets["1d"])
    return mtf.tf_inputs(markets, timeframe)


# -- compact storage ---------------------------------------------------------------

class Column:
    """Per-candle dicts stored as a flat float array (None = NaN row)."""

    def __init__(self, data: array, keys: tuple, groups: tuple | None = None):
        self.data, self.keys, self.groups = data, keys, groups
        self.width = len(keys) * (len(groups) if groups else 1)

    def __len__(self):
        return len(self.data) // self.width

    def __getitem__(self, i):
        if i < 0:
            i += len(self)
        if not 0 <= i < len(self):
            raise IndexError(i)
        row = self.data[i * self.width:(i + 1) * self.width]
        if math.isnan(row[0]):
            return None
        if not self.groups:
            return dict(zip(self.keys, row))
        k = len(self.keys)
        return {g: dict(zip(self.keys, row[j * k:(j + 1) * k])) for j, g in enumerate(self.groups)}

    @staticmethod
    def pack(values: list, keys: tuple, groups: tuple | None = None) -> "Column":
        width = len(keys) * (len(groups) if groups else 1)
        data = array("d")
        for v in values:
            if v is None:
                data.extend([NAN] * width)
            elif groups:
                data.extend(v[g][k] for g in groups for k in keys)
            else:
                data.extend(v[k] for k in keys)
        return Column(data, keys, groups)


def pack(r: learner.Replay) -> learner.Replay:
    """The same replay with its per-candle dicts stored compactly (outcomes are dropped: recomputed on load)."""
    experts = tuple(next((e for e in r.experts if e is not None), {e: None for e in learner.EXPERTS}))
    return learner.Replay(
        r.horizon,
        Column.pack(r.forecasts, learner.KINDS),
        Column.pack(r.experts, learner.KINDS, experts),
        Column.pack(r.weights, experts),
        None,
        r.learning_curve,
        Column.pack(r.raw, learner.KINDS) if r.raw else [],
        r.config,
        {},
    )


# -- the session -------------------------------------------------------------------

_WORKER: dict = {}


def _init_worker(markets, timeframe, inputs, extras):
    _WORKER.clear()
    _WORKER["markets"] = markets
    _WORKER["inputs"] = inputs
    _WORKER["extras"] = extras
    _WORKER["timeframe"] = timeframe
    _WORKER["outcomes"] = {}


def pattern_inputs(markets: dict[str, Market], timeframe: str, inputs=None):
    """
    Inputs of the pattern experts: the multi-timeframe set (`mtf.tf_inputs`) on
    every timeframe, because the training coins have exactly the same ones
    (the daily chart's research features include BTC-only data).
    """
    if timeframe != "1d" and inputs is not None:
        return inputs
    return mtf.tf_inputs(markets, timeframe)


def coin_rows(coin_markets: dict, timeframe: str, names: list[str]) -> list:
    """(coin, market, rows aligned to `names`) for every training coin on this timeframe."""
    out = []
    for coin, cm in sorted(coin_markets.items()):
        if timeframe not in cm or len(cm[timeframe].candles) < 300:
            continue
        c_names, c_rows, _ = mtf.tf_inputs(cm, timeframe)
        index = {name: k for k, name in enumerate(c_names)}
        columns = [index.get(name) for name in names]
        X = np.zeros((len(c_rows), len(names)))
        for j, k in enumerate(columns):
            if k is not None:
                X[:, j] = [row[k] for row in c_rows]
        out.append((coin, cm[timeframe], X))
    return out


def _close_times(market: Market) -> np.ndarray:
    period = TIMEFRAME_HOURS[market.timeframe] * 3600
    return np.array([c.timestamp.timestamp() + period for c in market.candles])


def pattern_experts(rows, outcome_list, timeframe: str, market: Market | None = None, coins=(), n_jobs: int = 1,
                    horizon: int | None = None) -> dict:
    """
    The walk-forward trees + analog experts (nothing if the libraries are not
    installed). `coins`: `coin_rows(...)` of the training coins, whose outcomes
    for the same horizon are added as extra examples, time-aligned with BTC.
    """
    if not ml_experts.available():
        return {}
    if not coins or market is None:
        return ml_experts.walk_forward_experts(rows, outcome_list, timeframe, n_jobs=n_jobs)
    pools = []
    for coin, cm, X in coins:
        c_out = outcomes(cm, horizon, k=1.0)
        times = _close_times(cm)
        y = np.array([-1 if o is None else learner.KINDS.index(o.kind) for o in c_out])
        t = np.array([np.inf if o is None else times[o.decided_index] for o in c_out])
        pools.append((X, y, t))
    return ml_experts.walk_forward_experts(rows, outcome_list, timeframe, close_times=_close_times(market),
                                           pools=pools, n_jobs=n_jobs)


def _outcomes(horizon):
    cache = _WORKER["outcomes"]
    if horizon not in cache:
        cache[horizon] = outcomes(_WORKER["markets"][_WORKER["timeframe"]], horizon, k=1.0)
    return cache[horizon]


def _task(job):
    """One job inside a worker: ("score", h, k), ("full", h, k) or ("memorised", h, k, count)."""
    kind, horizon, k = job[:3]
    market = _WORKER["markets"][_WORKER["timeframe"]]
    names, rows, keys = _WORKER["inputs"]
    out = _outcomes(horizon)
    config = learner.CONFIGS[k]
    extra = (_WORKER["extras"] or {}).get(horizon)
    if kind == "memorised":
        result = learner.passes(market, horizon, names, rows, keys, config=config, count=job[3], outcome_list=out,
                                extra_experts=extra)
        return job, [learner.skill(r, market) for r in result]
    r = learner.replay(market, horizon, names, rows, keys, config=config, outcome_list=out, extra_experts=extra)
    if kind == "score":
        return job, (learner.yearly_brier(r, market), learner.skill(r, market))
    return job, pack(r)


def _run(jobs, markets, timeframe, workers, inputs, extras=None):
    if workers <= 1:
        _init_worker(markets, timeframe, inputs, extras)
        return dict(_task(j) for j in jobs)
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), initializer=_init_worker,
                             initargs=(markets, timeframe, inputs, extras)) as pool:
        return dict(pool.map(_task, jobs))


def train_timeframe(markets: dict[str, Market], timeframe: str, horizons=None, configs: int | None = None,
                    memorised: int = 2, workers: int = 1, log=print, patterns: bool = True,
                    coin_markets: dict | None = None) -> dict:
    """
    Everything for one timeframe: per-version scores, nested choice, chained
    replay, memorised passes. `coin_markets` {coin: {tf: Market}}: the training
    coins, extra examples for the pattern experts.
    """
    market = markets[timeframe]
    horizons = horizons or learner.TF_HORIZONS[timeframe]
    count = configs or len(learner.CONFIGS)
    names = [c.name for c in learner.CONFIGS[:count]]
    inputs = inputs_for(markets, timeframe)
    extras = None
    if patterns and ml_experts.available():  # trees + analog, walk-forward, once per horizon (all cores)
        p_names, p_rows, _ = pattern_inputs(markets, timeframe, inputs)
        coins = coin_rows(coin_markets or {}, timeframe, p_names)
        extras = {h: pattern_experts(p_rows, outcomes(market, h, k=1.0), timeframe, market, coins, n_jobs=workers,
                                     horizon=h) for h in horizons}
    scored = _run([("score", h, k) for h in horizons for k in range(count)], markets, timeframe, workers, inputs, extras)
    result = {"end": market.candles[-1].timestamp.isoformat(), "n": len(market.candles),
              "first": market.candles[0].timestamp.isoformat(), "horizons": {}}
    plans = {}
    for h in horizons:
        per_year = [scored[("score", h, k)][0] for k in range(count)]
        chosen, table = learner.choose_by_year(per_year, names)
        current = chosen[max(chosen)] if chosen else 0
        plans[h] = (chosen, table, current)
    full_jobs = sorted({("full", h, k) for h, (chosen, _, current) in plans.items() for k in set(chosen.values()) | {current}})
    # honest pass + `memorised` extra passes over the same chart
    mem_jobs = [("memorised", h, plans[h][2], memorised + 1) for h in horizons] if memorised > 0 else []
    done = _run(full_jobs + mem_jobs, markets, timeframe, workers, inputs, extras)
    for h in horizons:
        chosen, table, current = plans[h]
        replays = {k: done[("full", h, k)] for (kind, hh, k) in full_jobs if hh == h}
        out = outcomes(market, h, k=1.0)
        for r in replays.values():
            r.outcomes = out
        chained = learner.chain(replays, chosen, market)
        result["horizons"][h] = {
            "replay": pack(chained),
            "table": table,
            "current_config": names[current],
            "configs": [{"name": names[k], **scored[("score", h, k)][1]} for k in range(count)],
            "nested": learner.skill(chained, market),
            "memorised": done[("memorised", h, current, memorised + 1)][1:] if mem_jobs else [],
            "experts": list(extras[h]) if extras else [],
            "coins": [c for c, _, _ in coins] if extras else [],
        }
        log(f"  {timeframe} h={h}: honest (nested) {result['horizons'][h]['nested'].get('brier_skill', 0):+.2%}")
    return result


def save(cache: dict, path: Path = CACHE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def load(path: Path = CACHE_FILE) -> dict | None:
    """The saved training session, or None if missing, unreadable or from another engine version."""
    try:
        with open(path, "rb") as f:
            cache = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
        return None
    return cache if isinstance(cache, dict) and cache.get("version") == learner.VERSION else None


def new_cache() -> dict:
    return {"version": learner.VERSION, "made": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "timeframes": {}}


def write_forecast_csv(market: Market, timeframe: str, horizon: int, r: learner.Replay, folder: Path = CACHE_DIR) -> Path:
    """Every forecast of the honest replay as it was made, with its outcome once decided."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"forecasts_{timeframe}_h{horizon}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["candle_time", "close", "p_bull", "p_bear", "p_range", "base_bull", "base_bear", "base_range",
                    "outcome", "candles_to_decide"])
        for i, c in enumerate(market.candles):
            p = r.forecasts[i]
            if p is None:
                continue
            base = r.experts[i]["base"]
            o = r.outcomes[i] if r.outcomes else None
            w.writerow([c.timestamp.isoformat(), c.close, *(round(p[k], 4) for k in learner.KINDS),
                        *(round(base[k], 4) for k in learner.KINDS),
                        "" if o is None else o.kind, "" if o is None else o.days])
    return path
