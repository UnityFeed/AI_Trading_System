"""
Graded-exposure strategies (roadmap 9a/9c): instead of all-in or all-out,
a strategy decides at every close what SHARE of the account should be in
BTC (0% to 100%), and the account is moved to that share at the next
tradeable open, but only when the difference is at least `band` (to avoid
paying fees for small changes). Fees and slippage are paid on the traded
amount only.

Why (research report, section 3): BTC's gains come in a few big rebound
days. A strategy that is fully out often misses them. Holding a core, or
scaling in and out in steps, keeps part of those days.

The target share is built in layers, each optional:

  1. base     fixed_weight (e.g. 60% always), or
              core + (1 - core) x average of the "votes" (each vote 0 or 1)
  2. volatility cap:  x min(1, vol_target / current yearly volatility)
  3. MVRV cap:        at most 100% / 50% / 25% when MVRV-Z < 3 / 3-5 / >= 5
  4. hash-rate filter: while the 30-day average hash rate is below the
                       60-day average (miners under stress), the share may
                       not be raised

A target is None (no decision, nothing changes) while any input is not
warmed up. External data is used with a delay (MVRV 1 day, hash rate 2
days) on top of the day it describes, because it is published later and
can be revised.
"""

import math
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting import features
from src.backtesting.conditions import evaluate_all, strategy_signals
from src.backtesting.engine import BacktestResult, CostSettings, Rebalance
from src.backtesting.market import Market
from src.backtesting.search import StrategySpec


MVRV_LAG_DAYS = 1
HASH_RATE_LAG_DAYS = 2
MAX_EXTERNAL_AGE_DAYS = 7  # older than this (after the lag) counts as missing


class MissingExternalData(RuntimeError):
    pass


@dataclass(frozen=True)
class ExposureSpec:
    name: str  # short text of the rules (shown in the app and the ledger)
    votes: tuple[str, ...] = ()
    core: float = 0.0  # share always held
    fixed_weight: float | None = None  # constant target instead of votes
    vol_target_pct: float | None = None  # e.g. 60 = cap at 60% / volatility
    mvrv_cap: bool = False
    hash_filter: bool = False
    band: float = 0.125  # minimum change of the share that is traded

    @property
    def needs_external(self) -> tuple[str, ...]:
        needed = []
        if self.mvrv_cap:
            needed += ["mvrv", "market_cap_usd"]
        if self.hash_filter:
            needed.append("hash_rate")
        return tuple(needed)


# -- votes --------------------------------------------------------------------

Vote = list[float | None]


def _close_above(market: Market, line: list[float | None]) -> Vote:
    return [
        None if level is None else float(candle.close > level)
        for candle, level in zip(market.candles, line)
    ]


def _positive(values: list[float | None]) -> Vote:
    return [None if v is None else float(v > 0) for v in values]


def _donchian(market: Market, entry_n: int, exit_n: int) -> Vote:
    """1 after a close above the prior entry_n high, 0 after a close below the prior exit_n low."""
    highs = features.prior_high(market, entry_n)
    lows = features.prior_low(market, exit_n)
    out: Vote = []
    state = 0.0
    for candle, high, low in zip(market.candles, highs, lows):
        if high is None or low is None:
            out.append(None)
            state = 0.0
            continue
        if candle.close > high:
            state = 1.0
        elif candle.close < low:
            state = 0.0
        out.append(state)
    return out


def _rules_state(market: Market, spec: StrategySpec) -> Vote:
    """1 while an all-in/all-out rule strategy would hold BTC (its stop ignored)."""
    entry, exit_signal = strategy_signals(evaluate_all(market), spec)
    out: Vote = []
    state = 0.0
    for buy, sell in zip(entry, exit_signal):
        if state == 0.0 and buy:
            state = 1.0
        elif state == 1.0 and sell:
            state = 0.0
        out.append(state)
    return out


TREND_MACD = StrategySpec("ema50>ema200", "macd_cross_up", "none", "ema20_cross_down_ema50", None)

VOTES: dict[str, Callable[[Market], Vote]] = {
    "close>sma20": lambda m: _close_above(m, features.sma(m, 20)),
    "close>sma50": lambda m: _close_above(m, features.sma(m, 50)),
    "close>sma100": lambda m: _close_above(m, features.sma(m, 100)),
    "close>sma200": lambda m: _close_above(m, features.sma(m, 200)),
    "ret28>0": lambda m: _positive(features.ret(m, 28)),
    "ret56>0": lambda m: _positive(features.ret(m, 56)),
    "ret91>0": lambda m: _positive(features.ret(m, 91)),
    "ret182>0": lambda m: _positive(features.ret(m, 182)),
    "donchian50/20": lambda m: _donchian(m, 50, 20),
    "trend-macd": lambda m: _rules_state(m, TREND_MACD),
}

VOTE_TEXT = {
    "close>sma20": "close above its 20-day average",
    "close>sma50": "close above its 50-day average",
    "close>sma100": "close above its 100-day average",
    "close>sma200": "close above its 200-day average",
    "ret28>0": "price higher than 28 days ago",
    "ret56>0": "price higher than 56 days ago",
    "ret91>0": "price higher than 91 days ago",
    "ret182>0": "price higher than 182 days ago",
    "donchian50/20": "breakout: above the 50-day high, until below the 20-day low",
    "trend-macd": "Daily trend + MACD would be holding",
}


# -- external data --------------------------------------------------------------

def _known_on(market: Market, i: int, lag_days: int) -> date:
    """Latest day whose external value may be used at candle i's close."""
    close_time = market.candles[i].timestamp + timedelta(hours=TIMEFRAME_HOURS[market.timeframe])
    # The day before the close is complete at the close; then add the publication lag.
    return (close_time - timedelta(days=1 + lag_days)).date()


def _lookup(market: Market, series: dict[date, float], lag_days: int) -> list[float | None]:
    days = sorted(series)
    out: list[float | None] = []
    for i in range(len(market.candles)):
        known = _known_on(market, i, lag_days)
        k = bisect_right(days, known) - 1
        if k < 0 or (known - days[k]).days > MAX_EXTERNAL_AGE_DAYS:
            out.append(None)
        else:
            out.append(series[days[k]])
    return out


def mvrv_z_by_day(mvrv: dict[date, float], market_cap: dict[date, float]) -> dict[date, float]:
    """
    MVRV-Z = (market cap - realized cap) / standard deviation of the market
    cap over all days up to that day (expanding, so no future data).
    Realized cap = market cap / MVRV.
    """
    out = {}
    n, mean, m2 = 0, 0.0, 0.0
    for day in sorted(set(mvrv) & set(market_cap)):
        cap, ratio = market_cap[day], mvrv[day]
        n += 1
        delta = cap - mean
        mean += delta / n
        m2 += delta * (cap - mean)
        if n >= 30 and ratio > 0 and m2 > 0:
            out[day] = (cap - cap / ratio) / math.sqrt(m2 / n)
    return out


def hash_stress_by_day(hash_rate: dict[date, float]) -> dict[date, float]:
    """1.0 while the 30-day average hash rate is below the 60-day average, else 0.0."""
    days = sorted(hash_rate)
    out = {}
    for k in range(59, len(days)):
        if (days[k] - days[k - 59]).days != 59:
            continue  # a missing day: skip rather than average over a hole
        last60 = [hash_rate[d] for d in days[k - 59:k + 1]]
        out[days[k]] = float(sum(last60[-30:]) / 30 < sum(last60) / 60)
    return out


def mvrv_cap(z: float) -> float:
    if z < 3:
        return 1.0
    if z < 5:
        return 0.5
    return 0.25


# -- targets --------------------------------------------------------------------

@dataclass
class ExposurePlan:
    targets: list[float | None]
    # name -> values per candle, to show what the strategy saw
    components: dict[str, list] = field(default_factory=dict)


def plan(market: Market, spec: ExposureSpec) -> ExposurePlan:
    n = len(market.candles)
    components: dict[str, list] = {}

    if spec.fixed_weight is not None:
        targets: list[float | None] = [spec.fixed_weight] * n
    else:
        votes = []
        for name in spec.votes:
            votes.append(VOTES[name](market))
            components[name] = votes[-1]
        targets = []
        for i in range(n):
            values = [v[i] for v in votes]
            if any(v is None for v in values):
                targets.append(None)
            else:
                signal = sum(values) / len(values) if values else 1.0
                targets.append(spec.core + (1 - spec.core) * signal)

    if spec.vol_target_pct is not None:
        vol = features.ewma_vol(market)
        components["volatility"] = vol
        cap = spec.vol_target_pct / 100
        targets = [
            None if t is None or v is None else t * min(1.0, cap / v)
            for t, v in zip(targets, vol)
        ]

    for series in spec.needs_external:
        if not market.external.get(series):
            raise MissingExternalData(
                f"This strategy needs external data ({series}). "
                "Run: python -m scripts.update_external_data"
            )

    if spec.mvrv_cap:
        z = _lookup(market, mvrv_z_by_day(market.external["mvrv"], market.external["market_cap_usd"]),
                    MVRV_LAG_DAYS)
        components["mvrv_z"] = z
        targets = [None if t is None or v is None else min(t, mvrv_cap(v)) for t, v in zip(targets, z)]

    if spec.hash_filter:
        stress = _lookup(market, hash_stress_by_day(market.external["hash_rate"]), HASH_RATE_LAG_DAYS)
        components["hash_stress"] = stress
        previous = 0.0
        filtered: list[float | None] = []
        for t, s in zip(targets, stress):
            if t is None or s is None:
                filtered.append(None)
                continue
            if s == 1.0 and t > previous:
                t = previous
            filtered.append(t)
            previous = t
        targets = filtered

    return ExposurePlan([None if t is None else round(t, 6) for t in targets], components)


# -- backtest -------------------------------------------------------------------

def run_exposure_backtest(
    market: Market,
    window: range,
    targets: list[float | None],
    band: float = 0.125,
    costs: CostSettings = CostSettings(),
    record_equity: bool = False,
) -> BacktestResult:
    """
    Simulate a graded-exposure strategy. Same timing as run_backtest: the
    target is decided at the close of candle i and the account is moved to
    it at the next tradeable open; while an order waits, no new decision is
    made. At the end everything is sold at the last close (with costs) so
    results compare fairly.
    """
    if not window:
        raise ValueError("The backtest window contains no candles.")

    candles = market.candles
    fee = costs.fee_pct / 100
    slip = costs.slippage_pct / 100

    cash, btc = 1.0, 0.0
    pending: float | None = None
    peak, max_drawdown = 1.0, 0.0
    weight_sum = 0.0
    weight = 0.0
    rebalances: list[Rebalance] = []
    curve: list[tuple[datetime, float]] = []

    for i in window:
        candle = candles[i]

        if pending is not None and market.tradeable[i]:
            price = candle.open
            equity = cash + btc * price
            before = btc * price / equity if equity > 0 else 0.0
            delta = pending * equity - btc * price
            paid = 0.0
            if pending == 0.0 and btc > 0:
                delta = -btc * price
            if abs(delta) > 1e-12 * max(equity, 1e-12):  # else: already there
                if delta > 0:
                    spend = min(delta, cash)
                    fill = price * (1 + slip)
                    paid = spend * fee
                    btc += (spend - paid) / fill
                    cash -= spend
                    traded = spend
                else:
                    qty = min(-delta / price, btc)
                    fill = price * (1 - slip)
                    gross = qty * fill
                    paid = gross * fee
                    cash += gross - paid
                    btc -= qty
                    traded = qty * price
                after_equity = cash + btc * price
                rebalances.append(Rebalance(
                    time=candle.timestamp,
                    price=fill,
                    from_weight=before,
                    to_weight=btc * price / after_equity if after_equity > 0 else 0.0,
                    traded=traded / equity if equity > 0 else 0.0,
                    fee=paid,
                ))
            pending = None

        equity = cash + btc * candle.close
        weight = btc * candle.close / equity if equity > 0 else 0.0
        weight_sum += weight
        if record_equity:
            curve.append((candle.timestamp, equity))
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)

        target = targets[i]
        if pending is None and target is not None and equity > 0:
            if abs(target - weight) >= band - 1e-9 or (target == 0.0 and btc > 0):
                pending = target

    last = candles[window[-1]]
    final = cash + btc * last.close * (1 - slip) * (1 - fee)

    return BacktestResult(
        start=candles[window[0]].timestamp,
        end=last.timestamp,
        final_equity=final,
        max_drawdown_pct=max_drawdown * 100,
        exposure_pct=weight_sum / len(window) * 100,
        trades=[],
        equity_curve=curve,
        rebalances=rebalances,
        end_weight=weight,
        pending_target=pending,
    )


def fixed_mix(
    market: Market,
    window: range,
    weight: float,
    costs: CostSettings = CostSettings(),
    band: float = 0.10,
    record_equity: bool = False,
) -> BacktestResult:
    """
    Exposure-matched benchmark: always hold `weight` in BTC (rest cash),
    rebalanced when it drifts more than `band`. Compare a strategy with the
    mix that holds the same average amount of BTC: did the timing add
    anything, or did it just hold less BTC?
    """
    return run_exposure_backtest(
        market, window, [weight] * len(market.candles), band, costs, record_equity
    )
