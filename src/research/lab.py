"""
The strategy lab: a large, systematic search over combinations of
building blocks, run with every CPU core, judged the honest way.

A lab strategy is a small state machine on DAILY candles:

  BUY   when the market FILTER is true and the TRIGGER fires
  SELL  when the EXIT fires, or the price falls `trail` below its highest
        close since the buy (trailing stop), or (exit "filter_off") the
        filter turns false
  share in BTC = core + (1 - core) x (1 while holding, 0 otherwise)

so core 0 is all-in/all-out and core 0.5 always keeps half in BTC. It runs
on the same engine as every registered strategy (run_exposure_backtest:
next-open fills, no fills on substituted hours, fees on the traded amount).

Building blocks come from three places: the classic indicator rules of
src/backtesting/conditions.py, the weekly chart (last completed week
only), and the research features (src/research/features.py) through their
expanding percentile ranks ("in its lowest 10% so far"), which also covers
less standard ideas: distance from the all-time high, the 200-week average,
volatility squeezes, capitulation wicks, MVRV, hash rate, the Coinbase
premium.

How a result is judged (the owner's goal: end with more BTC than holding):
  yearly excess = ln(1 + strategy return in the year) - ln(1 + holding's)
  summed over a period = ln(BTC compared with holding) for that period.
Choosing only ever uses 2013-2021 (score = the WEAKER of the 2013-16 and
2017-21 eras); 2022-now is only reported. The walk-forward chains, year by
year, what a pick made on the earlier years did in the next year, for
three ways of picking (single best, best family, average of the top 10).
"""

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product

from src.backtesting.conditions import evaluate_all
from src.backtesting.engine import CostSettings, buy_and_hold
from src.backtesting.exposure import run_exposure_backtest
from src.backtesting.market import Market
from src.research.features import FeatureFrame


ERA_1 = range(2013, 2017)
ERA_2 = range(2017, 2022)
TEST_FROM = 2022
FIRST_WALK_FORWARD_YEAR = 2017
MIN_TRADES_SELECTION = 6  # buys in 2013-2021
TRAILS = (None, 0.20, 0.30)
CORES = (0.0, 0.33, 0.5)


# -- building blocks ------------------------------------------------------------

Flags = list[bool]


def _rank(frame: FeatureFrame, name: str, below: float | None = None, above: float | None = None) -> Flags:
    ranks = frame.ranks.get(name)
    if ranks is None:
        return [False] * len(frame.market.candles)
    if below is not None:
        return [r is not None and r < below for r in ranks]
    return [r is not None and r > above for r in ranks]


def _value(frame: FeatureFrame, name: str, above: float | None = None, below: float | None = None) -> Flags:
    values = frame.values.get(name)
    if values is None:
        return [False] * len(frame.market.candles)
    if above is not None:
        return [v is not None and v > above for v in values]
    return [v is not None and v < below for v in values]


def _up_cross(flags: Flags, consecutive: list[bool]) -> Flags:
    """True on the day a condition becomes true (after a day it was false)."""
    return [i > 0 and consecutive[i] and flags[i] and not flags[i - 1] for i in range(len(flags))]


def _both(a: Flags, b: Flags) -> Flags:
    return [x and y for x, y in zip(a, b)]


def building_blocks(frame: FeatureFrame) -> tuple[dict[str, Flags], dict[str, Flags], dict[str, Flags]]:
    """(filters, triggers, exits): name -> one flag per daily candle."""
    m = frame.market
    n = len(m.candles)
    classic = evaluate_all(m)
    cons = m.consecutive
    f = frame

    filters = {
        "none": [True] * n,
        "ema50>ema200": classic["trend"]["ema50>ema200"],
        "close>ema200": classic["trend"]["close>ema200"],
        "close>sma200": _value(f, "trend.dist_sma200", above=0),
        "close>200w_avg": _value(f, "trend.dist_sma1400", above=0),
        "weekly close>ema20": _value(f, "weekly.close_vs_ema20", above=0),
        "weekly close>ema10": _value(f, "weekly.close_vs_ema10", above=0),
        "weekly ema10>ema30": _value(f, "weekly.ema10_vs_ema30", above=0),
        "weekly macd>signal": _value(f, "weekly.macd_hist_pct", above=0),
        "weekly rsi>50": _value(f, "weekly.rsi", above=50),
        "deep below ATH (rank<0.25)": _rank(f, "cycle.drop_from_ath", below=0.25),
        "mvrv cheap (rank<0.35)": _rank(f, "chain.mvrv_z", below=0.35),
        "mvrv not expensive (rank<0.85)": _rank(f, "chain.mvrv_z", below=0.85),
        "miners ok": _value(f, "chain.hash_stress", below=0.5),
        "calm volatility (rank<0.5)": _rank(f, "vol.realized_30d", below=0.5),
        "coinbase premium>0 (7d)": _value(f, "flow.coinbase_premium_7d", above=0),
        "daily structure up": _value(f, "structure.trend", above=0.5),
        "weekly structure up": _value(f, "structure.weekly_trend", above=0.5),
        "weekly structure not down": _value(f, "structure.weekly_trend", above=-0.5),
    }
    # Two-filter combinations: a trend view AND a context view.
    trend_views = ["ema50>ema200", "close>ema200", "close>sma200", "close>200w_avg", "weekly close>ema20",
                   "weekly close>ema10", "weekly ema10>ema30", "weekly macd>signal", "weekly rsi>50"]
    context_views = ["deep below ATH (rank<0.25)", "mvrv cheap (rank<0.35)", "mvrv not expensive (rank<0.85)",
                     "miners ok", "calm volatility (rank<0.5)", "coinbase premium>0 (7d)"]
    for t in trend_views:
        for c in context_views:
            filters[f"{t} + {c}"] = _both(filters[t], filters[c])

    triggers = {
        "at once": [True] * n,
        "macd cross up": classic["trigger"]["macd_cross_up"],
        "ema20 cross up ema50": classic["trigger"]["ema20_cross_up_ema50"],
        "rsi<30": classic["trigger"]["rsi<30"],
        "rsi<40": classic["trigger"]["rsi<40"],
        "close<bb lower": classic["trigger"]["close<bb_lower"],
        "close crosses above sma20": _up_cross(_value(f, "trend.dist_sma20", above=0), cons),
        "close crosses above sma50": _up_cross(_value(f, "trend.dist_sma50", above=0), cons),
        "breakout above 50d high": _value(f, "cycle.range_position_50d", above=1.0),
        "weekly turns up (close>ema10)": _up_cross(_value(f, "weekly.close_vs_ema10", above=0), cons),
        "rsi very low (rank<0.1)": _rank(f, "mom.rsi", below=0.1),
        "7d drop extreme (rank<0.1)": _rank(f, "mom.ret_7d", below=0.1),
        "28d drop extreme (rank<0.1)": _rank(f, "mom.ret_28d", below=0.1),
        "far below sma50 (rank<0.1)": _rank(f, "trend.dist_sma50", below=0.1),
        "bottom of 50d range (rank<0.1)": _rank(f, "cycle.range_position_50d", below=0.1),
        "weak closes 5d (rank<0.1)": _rank(f, "candle.close_position_5d", below=0.1),
        "weekly rsi low (rank<0.15)": _rank(f, "weekly.rsi", below=0.15),
        "capitulation wick+volume": _both(_rank(f, "candle.lower_wick", above=0.9),
                                          _rank(f, "volume.relative_20", above=0.9)),
        "volatility squeeze (rank<0.1)": _rank(f, "vol.ratio_10_60", below=0.1),
        "squeeze + close>sma20": _both(_rank(f, "vol.bb_width", below=0.15), _value(f, "trend.dist_sma20", above=0)),
        "momentum 28d strong (rank>0.8)": _rank(f, "mom.ret_28d", above=0.8),
        "hash growth recovers": _up_cross(_value(f, "chain.hash_growth_30_90", above=0), cons),
        "rebound 10% from 91d low": _up_cross(_value(f, "cycle.rise_from_low_91d", above=0.10), cons),
        "coinbase premium turns positive": _up_cross(_value(f, "flow.coinbase_premium_7d", above=0), cons),
        "daily CHoCH up": _value(f, "structure.days_since_choch_up", below=0.5),
        "daily structure turns up": _up_cross(_value(f, "structure.trend", above=0.5), cons),
    }
    exits = {
        "filter_off": None,  # handled in simulate(): sell when the filter turns false
        "ema20 cross down ema50": classic["exit"]["ema20_cross_down_ema50"],
        "macd cross down": classic["exit"]["macd_cross_down"],
        "rsi>70": classic["exit"]["rsi>70"],
        "close>bb upper": classic["exit"]["close>bb_upper"],
        "close crosses below sma50": _up_cross(_value(f, "trend.dist_sma50", below=0), cons),
        "close crosses below sma200": _up_cross(_value(f, "trend.dist_sma200", below=0), cons),
        "weekly close<ema10": _value(f, "weekly.close_vs_ema10", below=0),
        "weekly close<ema20": _value(f, "weekly.close_vs_ema20", below=0),
        "weekly macd<signal": _value(f, "weekly.macd_hist_pct", below=0),
        "overextended above sma50 (rank>0.95)": _rank(f, "trend.dist_sma50", above=0.95),
        "rsi very high (rank>0.95)": _rank(f, "mom.rsi", above=0.95),
        "weekly rsi very high (rank>0.9)": _rank(f, "weekly.rsi", above=0.9),
        "mvrv expensive (rank>0.9)": _rank(f, "chain.mvrv_z", above=0.9),
        "blow-off: 28d gain rank>0.95": _rank(f, "mom.ret_28d", above=0.95),
        "never (only trail/filter)": [False] * n,
        "daily CHoCH down": _value(f, "structure.days_since_choch_down", below=0.5),
        "weekly structure turns down": _up_cross(_value(f, "structure.weekly_trend", below=-0.5), cons),
    }
    return filters, triggers, exits


# -- one strategy -----------------------------------------------------------------

@dataclass(frozen=True)
class LabSpec:
    filter: str
    trigger: str
    exit: str
    trail: float | None
    core: float

    @property
    def family(self) -> tuple[str, str]:
        return self.filter, self.trigger

    @property
    def name(self) -> str:
        parts = [f"BUY {self.trigger}" + ("" if self.filter == "none" else f" while {self.filter}"),
                 f"SELL {self.exit}"]
        if self.trail:
            parts.append(f"trail {self.trail:.0%}")
        if self.core:
            parts.append(f"core {self.core:.0%}")
        return " | ".join(parts)


def holding_state(spec: LabSpec, closes: list[float], filters, triggers, exits) -> list[float]:
    """1.0 on days the strategy holds (decided at that day's close), else 0.0."""
    flt, trg = filters[spec.filter], triggers[spec.trigger]
    ex = exits[spec.exit]
    state = []
    holding = False
    peak = 0.0
    for i, close in enumerate(closes):
        if holding:
            peak = max(peak, close)
            if (spec.exit == "filter_off" and not flt[i]) or (ex is not None and ex[i]) \
                    or (spec.trail and close < peak * (1 - spec.trail)):
                holding = False
        elif flt[i] and trg[i]:
            holding, peak = True, close
        state.append(1.0 if holding else 0.0)
    return state


def targets_for(spec: LabSpec, state: list[float]) -> list[float]:
    return [spec.core + (1 - spec.core) * s for s in state]


# -- evaluation -------------------------------------------------------------------

@dataclass
class LabResult:
    spec: LabSpec
    years: dict[int, float]  # yearly excess log return vs holding
    returns: dict[int, float]  # yearly simple return of the strategy
    buys_selection: int
    buys_total: int
    max_drawdown_pct: float
    exposure_pct: float
    excess_sharpe: float  # daily (strategy - holding) mean / std, full history

    def excess(self, years) -> float:
        return sum(self.years.get(y, 0.0) for y in years)

    @property
    def selection_score(self) -> float:
        return min(self.excess(ERA_1), self.excess(ERA_2))

    @property
    def test_excess(self) -> float:
        return sum(v for y, v in self.years.items() if y >= TEST_FROM)


def year_values(curve) -> dict[int, tuple[float, float]]:
    """year -> (value at the start of the year, value at its end)."""
    out = {}
    previous = 1.0
    for when, value in curve:
        y = when.year
        if y not in out:
            out[y] = [previous, value]
        out[y][1] = value
        previous = value
    return {y: (a, b) for y, (a, b) in out.items()}


_STATE: dict = {}


def _init(market: Market, blocks, hold_years, hold_daily, costs: CostSettings):
    _STATE.update(market=market, blocks=blocks, hold_years=hold_years, hold_daily=hold_daily, costs=costs,
                  closes=[c.close for c in market.candles])


def evaluate(spec: LabSpec) -> LabResult | None:
    s = _STATE
    market: Market = s["market"]
    filters, triggers, exits = s["blocks"]
    state = holding_state(spec, s["closes"], filters, triggers, exits)
    buys = [i for i in range(1, len(state)) if state[i] > state[i - 1]] + ([0] if state and state[0] else [])
    if not buys:
        return None
    result = run_exposure_backtest(market, range(len(market.candles)), targets_for(spec, state),
                                   band=0.05, costs=s["costs"], record_equity=True)
    years = {}
    returns = {}
    for y, (a, b) in year_values(result.equity_curve).items():
        if a <= 0 or b <= 0 or y not in s["hold_years"]:
            continue
        ha, hb = s["hold_years"][y]
        returns[y] = b / a - 1
        years[y] = math.log(b / a) - math.log(hb / ha)
    # daily excess returns for the Sharpe of "beating holding"
    daily = {}
    for when, value in result.equity_curve:
        daily[when.date()] = value
    days = sorted(daily)
    diffs = []
    for d0, d1 in zip(days, days[1:]):
        h = s["hold_daily"].get(d1)
        if h is not None and daily[d0] > 0:
            diffs.append(daily[d1] / daily[d0] - 1 - h)
    mean = sum(diffs) / len(diffs) if diffs else 0.0
    std = math.sqrt(sum((x - mean) ** 2 for x in diffs) / len(diffs)) if diffs else 0.0
    selection_end = datetime(2022, 1, 1, tzinfo=timezone.utc)
    return LabResult(
        spec=spec, years=years, returns=returns,
        buys_selection=sum(market.candles[i].timestamp < selection_end for i in buys),
        buys_total=len(buys),
        max_drawdown_pct=result.max_drawdown_pct,
        exposure_pct=result.exposure_pct,
        excess_sharpe=mean / std if std > 0 else 0.0,
    )


def all_specs(blocks) -> list[LabSpec]:
    filters, triggers, exits = blocks
    specs = []
    for flt, trg, ex, trail, core in product(filters, triggers, exits, TRAILS, CORES):
        if ex == "filter_off" and flt == "none":
            continue
        if ex == "never (only trail/filter)" and trail is None:
            continue
        if not any(filters[flt]) or not any(triggers[trg]):
            continue  # needs data this history does not have
        specs.append(LabSpec(flt, trg, ex, trail, core))
    return specs


@dataclass
class HoldBenchmark:
    years: dict[int, tuple[float, float]]
    daily: dict  # date -> simple return


def hold_benchmark(market: Market, costs: CostSettings) -> HoldBenchmark:
    held = buy_and_hold(market, range(len(market.candles)), costs, record_equity=True)
    daily_values = {}
    for when, value in held.equity_curve:
        daily_values[when.date()] = value
    days = sorted(daily_values)
    daily = {d1: daily_values[d1] / daily_values[d0] - 1 for d0, d1 in zip(days, days[1:]) if daily_values[d0] > 0}
    return HoldBenchmark(year_values(held.equity_curve), daily)


def run_search(market: Market, frame: FeatureFrame, costs: CostSettings, workers: int | None = None,
               progress=None) -> tuple[list[LabResult], HoldBenchmark]:
    blocks = building_blocks(frame)
    specs = all_specs(blocks)
    hold = hold_benchmark(market, costs)
    workers = workers or os.cpu_count() or 1
    results = []
    chunk = max(1, len(specs) // (workers * 20))
    with ProcessPoolExecutor(workers, initializer=_init,
                             initargs=(market, blocks, hold.years, hold.daily, costs)) as pool:
        for k, r in enumerate(pool.map(evaluate, specs, chunksize=chunk)):
            if r is not None:
                results.append(r)
            if progress and (k + 1) % 5000 == 0:
                progress(k + 1, len(specs))
    return results, hold


# -- choosing -----------------------------------------------------------------------

def eligible(results: list[LabResult]) -> list[LabResult]:
    return [r for r in results if r.buys_selection >= MIN_TRADES_SELECTION]


def ranked(results: list[LabResult]) -> list[LabResult]:
    return sorted(eligible(results), key=lambda r: r.selection_score, reverse=True)


@dataclass
class WalkForwardYear:
    year: int
    picks: list[str]
    excess: float  # ln(BTC vs holding) in that year


def _score_before(r: LabResult, year: int) -> float:
    """Weakest of the two halves of everything before `year` (same idea as the selection score)."""
    past = [y for y in sorted(r.years) if y < year]
    if len(past) < 4:
        return -1e9
    half = len(past) // 2
    return min(sum(r.years[y] for y in past[:half]), sum(r.years[y] for y in past[half:]))


def walk_forward(results: list[LabResult], method: str, first_year: int = FIRST_WALK_FORWARD_YEAR,
                 last_year: int | None = None) -> list[WalkForwardYear]:
    """
    method "single": the best strategy on the years before; "family": the best
    filter+trigger family by its MEDIAN variant, then its best member; "top10":
    ten equal sub-accounts in the ten best.
    """
    pool = [r for r in results if r.buys_total >= 3]
    years = sorted({y for r in pool for y in r.years})
    last_year = last_year or (years[-1] if years else first_year)
    out = []
    for year in range(first_year, last_year + 1):
        scored = sorted(((_score_before(r, year), r) for r in pool if year in r.years),
                        key=lambda x: x[0], reverse=True)
        if not scored:
            continue
        if method == "single":
            chosen = [scored[0][1]]
        elif method == "top10":
            chosen = [r for _, r in scored[:10]]
        else:
            families: dict = {}
            for score, r in scored:
                families.setdefault(r.spec.family, []).append((score, r))
            best = max(families.values(), key=lambda m: sorted(s for s, _ in m)[len(m) // 2])
            chosen = [max(best, key=lambda x: x[0])[1]]
        growth = sum(math.exp(r.years[year]) for r in chosen) / len(chosen)
        out.append(WalkForwardYear(year, [r.spec.name for r in chosen], math.log(growth)))
    return out


# -- lab strategies in the registry ------------------------------------------------

_FRAMES: dict[int, tuple] = {}


def parse_vote(name: str) -> LabSpec:
    """'lab:FILTER|TRIGGER|EXIT|TRAIL' (TRAIL empty for none) -> LabSpec with core 0."""
    filter_name, trigger, exit_name, trail = name[len("lab:"):].split("|")
    return LabSpec(filter_name, trigger, exit_name, float(trail) if trail else None, 0.0)


def lab_vote(market: Market, name: str) -> list[float | None]:
    """1.0 while the lab state machine holds, 0.0 otherwise (used by graded strategies)."""
    from src.research.features import build_frame

    key = id(market)
    if key not in _FRAMES or _FRAMES[key][0] is not market:
        if len(_FRAMES) >= 4:
            _FRAMES.pop(next(iter(_FRAMES)))
        _FRAMES[key] = (market, building_blocks(build_frame(market)))
    blocks = _FRAMES[key][1]
    spec = parse_vote(name)
    return holding_state(spec, [c.close for c in market.candles], *blocks)


def vote_details(market: Market, name: str, i: int) -> list[dict]:
    """The parts of a lab vote at candle i, for the strategy's rule checklist."""
    lab_vote(market, name)  # builds and caches the blocks
    filters, triggers, exits = _FRAMES[id(market)][1]
    spec = parse_vote(name)
    rows = [
        {"role": "Filter", "rule": spec.filter, "met": bool(filters[spec.filter][i])},
        {"role": "Buy trigger", "rule": spec.trigger, "met": bool(triggers[spec.trigger][i])},
    ]
    if exits.get(spec.exit) is not None:
        rows.append({"role": "Sell rule", "rule": spec.exit, "met": bool(exits[spec.exit][i])})
    if spec.trail:
        rows.append({"role": "Trailing stop", "rule": f"{spec.trail:.0%} below the highest close", "met": None})
    return rows
