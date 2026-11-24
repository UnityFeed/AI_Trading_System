"""
The research feature library: for every DAILY candle, a wide set of
measurements known at that candle's close (no look-ahead), from the price
itself, the indicators, the weekly chart, on-chain data and the difference
between exchanges.

Every feature is also turned into an expanding PERCENTILE RANK (0..1): how
the value compares with all earlier values of the same feature, using only
the past. A rank of 0.05 means "lower than 95% of everything seen before".
This makes very different measurements comparable (RSI, distance from an
average, MVRV...) and lets one rule ("very low", "very high") apply to all
of them without picking thresholds by hand on the full history.

Groups (name prefix):
  trend     distance of the close from its 20/50/100/200-day and 200-week
            averages, EMA 50 slope, EMA 50 vs 200
  mom       returns over 7..365 days, RSI, MACD histogram (as % of price)
  cycle     drop from the all-time high, days since it, rise from the
            lowest low of the last 91 / 365 days, position in the 50-day range
  vol       ATR %, Bollinger width, 30-day volatility, 10/60-day volatility
            ratio (squeeze / expansion), Bollinger width rank change
  volume    relative volume, 10/60-day volume trend
  candle    lower and upper wick share of the day's range (capitulation /
            rejection), 5-day average close position in the range
  weekly    from the LAST COMPLETED week only: close vs weekly EMA 10/20,
            EMA 10 vs 30, MACD histogram, RSI, 4-week return
  chain     MVRV-Z (1-day delay), hash-rate 30/90-day growth and miner
            stress (2-day delay)
  flow      Coinbase price premium over the primary exchange (daily mean,
            and its 7-day average): US buying pressure
"""

import math
from bisect import bisect_left, insort
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.research.other_market_features import other_market_features
from src.analysis.technical_indicators import calculate_indicators
from src.backtesting import features as price
from src.backtesting.exposure import (
    HASH_RATE_LAG_DAYS, MVRV_LAG_DAYS, _lookup, hash_stress_by_day, mvrv_z_by_day,
)
from src.backtesting.market import Market
from src.data_collection.market_data import MarketData


MIN_HISTORY_FOR_RANK = 365  # earlier values have no rank (not enough past to compare with)

Series = list[float | None]


@dataclass
class FeatureFrame:
    market: Market
    values: dict[str, Series] = field(default_factory=dict)
    ranks: dict[str, Series] = field(default_factory=dict)

    def names(self) -> list[str]:
        return sorted(self.values)


def expanding_rank(values: Series, min_history: int = MIN_HISTORY_FOR_RANK) -> Series:
    """Share of the earlier (non-missing) values that are below the current one."""
    seen: list[float] = []
    out: Series = []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
            continue
        if len(seen) >= min_history:
            low = bisect_left(seen, v)
            out.append(low / len(seen))
        else:
            out.append(None)
        insort(seen, v)
    return out


def _ratio(a: Series, b: Series, minus_one: bool = True) -> Series:
    return [None if x is None or y in (None, 0) else (x / y - (1 if minus_one else 0)) for x, y in zip(a, b)]


def _row(market: Market, name: str) -> Series:
    return [row.values.get(name) for row in market.rows]


def _rolling(values: Series, n: int, fn, consecutive: list[bool]) -> Series:
    out: Series = [None] * len(values)
    window: list[float] = []
    for i, v in enumerate(values):
        if not consecutive[i]:
            window = []
        if v is None:
            window = []
            continue
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            out[i] = fn(window)
    return out


def _std(xs: list[float]) -> float:
    mean = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def weekly_from_daily(candles: list[MarketData]) -> list[MarketData]:
    """Complete Monday-Sunday weeks from daily candles (a week with a missing day is skipped)."""
    weeks: dict = {}
    for c in candles:
        start = c.timestamp - timedelta(days=c.timestamp.weekday())
        weeks.setdefault(start, []).append(c)
    out = []
    for start, days in sorted(weeks.items()):
        if len(days) != 7:
            continue
        out.append(MarketData(
            symbol=days[0].symbol, market=days[0].market, timestamp=start,
            open=days[0].open, high=max(d.high for d in days), low=min(d.low for d in days),
            close=days[-1].close, volume=sum(d.volume for d in days), exchange=days[0].exchange,
        ))
    return out


def _weekly_features(market: Market) -> dict[str, Series]:
    """Weekly values mapped onto each day: only weeks that ended at or before the day's close."""
    weekly = weekly_from_daily(market.candles)
    if not weekly:
        return {}
    rows = calculate_indicators(weekly, "1w")
    closes = [w.close for w in weekly]
    by_week = []
    consecutive = [False] + [b.timestamp - a.timestamp == timedelta(days=7) for a, b in zip(weekly, weekly[1:])]
    ema10 = price_ema([w.close for w in weekly], 10, consecutive)
    ema30 = price_ema([w.close for w in weekly], 30, consecutive)
    for k, (w, row) in enumerate(zip(weekly, rows)):
        v = row.values
        ret4 = None
        if k >= 4 and all(consecutive[k - 3:k + 1]):
            ret4 = closes[k] / closes[k - 4] - 1
        by_week.append({
            "weekly.close_vs_ema10": None if ema10[k] is None else w.close / ema10[k] - 1,
            "weekly.close_vs_ema20": None if v.get("ema_20") is None else w.close / v["ema_20"] - 1,
            "weekly.ema10_vs_ema30": None if ema10[k] is None or ema30[k] is None else ema10[k] / ema30[k] - 1,
            "weekly.macd_hist_pct": None if v.get("macd_hist") is None else v["macd_hist"] / w.close,
            "weekly.rsi": v.get("rsi_14"),
            "weekly.ret_4w": ret4,
        })
    names = list(by_week[0])
    out = {name: [None] * len(market.candles) for name in names}
    k = -1
    for i, c in enumerate(market.candles):
        day_close = c.timestamp + timedelta(days=1)
        while k + 1 < len(weekly) and weekly[k + 1].timestamp + timedelta(days=7) <= day_close:
            k += 1
        if k >= 0 and day_close - (weekly[k].timestamp + timedelta(days=7)) < timedelta(days=7):
            for name in names:
                out[name][i] = by_week[k][name]
    return out


def _structure_features(market: Market) -> dict[str, Series]:
    from src.predictive_engine.structure import analyse

    c = market.candles
    n = len(c)
    s = analyse(c, "1d")
    trend_value = {"up": 1.0, "down": -1.0, "none": 0.0}
    out: dict[str, Series] = {
        "structure.trend": [trend_value[t] for t in s.trend],
        "structure.dist_swing_high": [None if h is None else x.close / h - 1 for x, h in zip(c, s.swing_high)],
        "structure.dist_swing_low": [None if l is None else x.close / l - 1 for x, l in zip(c, s.swing_low)],
    }
    for direction in ("up", "down"):
        since: Series = [None] * n
        last = None
        events = {e.index for e in s.events if e.kind == "CHoCH" and e.direction == direction}
        for i in range(n):
            if i in events:
                last = i
            since[i] = None if last is None else float(i - last)
        out[f"structure.days_since_choch_{direction}"] = since

    weekly = weekly_from_daily(c)
    if weekly:
        ws = analyse(weekly, "1w")
        trend: Series = [None] * n
        k = -1
        for i, x in enumerate(c):
            day_close = x.timestamp + timedelta(days=1)
            while k + 1 < len(weekly) and weekly[k + 1].timestamp + timedelta(days=7) <= day_close:
                k += 1
            if k >= 0:
                trend[i] = trend_value[ws.trend[k]]
        out["structure.weekly_trend"] = trend
    return out


def price_ema(values: list[float], n: int, consecutive: list[bool]) -> Series:
    """EMA seeded with the SMA of the first n values of each run."""
    out: Series = [None] * len(values)
    k = 2 / (n + 1)
    run: list[float] = []
    ema = None
    for i, v in enumerate(values):
        if not consecutive[i]:
            run, ema = [], None
        run.append(v)
        if ema is None:
            if len(run) == n:
                ema = sum(run) / n
                out[i] = ema
        else:
            ema += k * (v - ema)
            out[i] = ema
    return out


def build_frame(market: Market, premium: dict[date, float] | None = None) -> FeatureFrame:
    """All features and their expanding ranks for a DAILY market."""
    if market.timeframe != "1d":
        raise ValueError("The research features are built on daily candles.")
    c = market.candles
    n = len(c)
    close = [x.close for x in c]
    cons = market.consecutive
    v: dict[str, Series] = {}

    # trend
    for days in (20, 50, 100, 200):
        v[f"trend.dist_sma{days}"] = _ratio(close, price.sma(market, days))
    v["trend.dist_sma1400"] = _ratio(close, price.sma(market, 1400))  # the 200-week average
    ema50, ema200 = _row(market, "ema_50"), _row(market, "ema_200")
    v["trend.ema50_vs_ema200"] = _ratio(ema50, ema200)
    v["trend.ema50_slope_10d"] = [
        None if i < 10 or ema50[i] is None or ema50[i - 10] is None or not all(cons[i - 9:i + 1])
        else ema50[i] / ema50[i - 10] - 1 for i in range(n)
    ]

    # momentum
    for days in (7, 28, 91, 182, 365):
        v[f"mom.ret_{days}d"] = price.ret(market, days)
    v["mom.rsi"] = _row(market, "rsi_14")
    hist = _row(market, "macd_hist")
    v["mom.macd_hist_pct"] = [None if h is None else h / x for h, x in zip(hist, close)]

    # cycle position
    ath, since, peak = [], [], None
    days_since = 0
    for x in close:
        if peak is None or x >= peak:
            peak, days_since = x, 0
        else:
            days_since += 1
        ath.append(x / peak - 1)
        since.append(float(days_since))
    v["cycle.drop_from_ath"] = ath
    v["cycle.days_since_ath"] = since
    for days in (91, 365):
        lows = price.prior_low(market, days)
        v[f"cycle.rise_from_low_{days}d"] = _ratio(close, lows)
    hi50, lo50 = price.prior_high(market, 50), price.prior_low(market, 50)
    v["cycle.range_position_50d"] = [
        None if h is None or l is None or h == l else (x - l) / (h - l) for x, h, l in zip(close, hi50, lo50)
    ]

    # volatility
    atr = _row(market, "atr_14")
    v["vol.atr_pct"] = [None if a is None else a / x for a, x in zip(atr, close)]
    v["vol.bb_width"] = _row(market, "bb_width")
    logret: Series = [None] + [
        math.log(c[i].close / c[i - 1].close) if cons[i] else None for i in range(1, n)
    ]
    vol10 = _rolling(logret, 10, _std, cons)
    vol30 = _rolling(logret, 30, _std, cons)
    vol60 = _rolling(logret, 60, _std, cons)
    v["vol.realized_30d"] = [None if s is None else s * math.sqrt(365) for s in vol30]
    v["vol.ratio_10_60"] = _ratio(vol10, vol60, minus_one=False)

    # volume
    v["volume.relative_20"] = _row(market, "relative_volume_20")
    vols = [x.volume for x in c]
    v["volume.trend_10_60"] = _ratio(
        _rolling(vols, 10, lambda w: sum(w) / len(w), cons),
        _rolling(vols, 60, lambda w: sum(w) / len(w), cons),
    )

    # candle shape
    def wick(x, lower):
        span = x.high - x.low
        if span <= 0:
            return 0.0
        return ((min(x.open, x.close) - x.low) if lower else (x.high - max(x.open, x.close))) / span
    v["candle.lower_wick"] = [wick(x, True) for x in c]
    v["candle.upper_wick"] = [wick(x, False) for x in c]
    position = [None if x.high == x.low else (x.close - x.low) / (x.high - x.low) for x in c]
    v["candle.close_position_5d"] = _rolling(position, 5, lambda w: sum(w) / len(w), cons)

    # weekly chart (last completed week)
    v.update(_weekly_features(market))

    # market structure (predictive engine, phase 1): daily, and weekly from completed weeks
    v.update(_structure_features(market))

    # on-chain (with publication delays)
    ext = market.external
    if ext.get("mvrv") and ext.get("market_cap_usd"):
        v["chain.mvrv_z"] = _lookup(market, mvrv_z_by_day(ext["mvrv"], ext["market_cap_usd"]), MVRV_LAG_DAYS)
    if ext.get("hash_rate"):
        hr = ext["hash_rate"]
        days = sorted(hr)
        growth = {}
        for k in range(89, len(days)):
            if (days[k] - days[k - 89]).days == 89:
                last90 = [hr[d] for d in days[k - 89:k + 1]]
                growth[days[k]] = (sum(last90[-30:]) / 30) / (sum(last90) / 90) - 1
        v["chain.hash_growth_30_90"] = _lookup(market, growth, HASH_RATE_LAG_DAYS)
        v["chain.hash_stress"] = _lookup(market, hash_stress_by_day(hr), HASH_RATE_LAG_DAYS)

    # other markets (S&P 500, Nasdaq 100, Dow 30, gold, silver), when loaded into market.external
    v.update(other_market_features(market))

    # exchange flow
    if premium:
        daily = [premium.get(x.timestamp.date()) for x in c]
        v["flow.coinbase_premium"] = daily
        v["flow.coinbase_premium_7d"] = _rolling(daily, 7, lambda w: sum(w) / len(w), [True] * n)

    ranks = {name: expanding_rank(series) for name, series in v.items()}
    return FeatureFrame(market, v, ranks)


def coinbase_premium(history_candles: list[MarketData], coinbase: list[MarketData]) -> dict[date, float]:
    """
    Daily mean of (Coinbase close / primary close - 1) over the hours both have.
    Hours where the primary series itself came from Coinbase (filled outages)
    should be removed by the caller.
    """
    primary = {x.timestamp: x.close for x in history_candles}
    sums: dict[date, list[float]] = {}
    for x in coinbase:
        p = primary.get(x.timestamp)
        if p:
            sums.setdefault(x.timestamp.date(), []).append(x.close / p - 1)
    return {d: sum(xs) / len(xs) for d, xs in sums.items() if len(xs) >= 12}
