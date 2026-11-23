"""
Multi-timeframe inputs for the learning engine on ANY timeframe (1h, 4h, 1d).

For each candle (known at its close):
  own chart     RSI, distance from EMA 20/50/200, MACD histogram, returns over
                6/24/72 candles (all scaled by the current volatility, so they
                mean the same in calm and wild markets), volatility versus its
                own recent average, ADX, market structure (trend, time since the
                last change of character), distance to the nearest support and
                resistance, position inside the last Fibonacci swing, chart
                patterns (open candidates and recent breakouts)
  higher charts for every higher timeframe (4h, 1d, 1w above the candle's
                own): its structure trend, ADX (trend strength), distance from
                its EMA 200 and EMA 50, RSI and MACD histogram, taken from the
                LAST COMPLETED higher candle only (a forming weekly candle is
                never used)

Values are squashed into about -1..1 with fixed rules (no percentile ranks:
those need the whole past for every candle, too slow on 115,000 hourly
candles). The daily chart keeps its richer research features (learner.build_inputs).
"""

import math
from bisect import bisect_right
from datetime import timedelta

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting.market import Market
from src.predictive_engine.levels import adx, fibonacci, support_resistance
from src.predictive_engine.outcomes import candle_volatility
from src.predictive_engine.patterns import detect_patterns, pattern_features, swings_known_over_time
from src.predictive_engine.structure import analyse


ORDER = ("1h", "4h", "1d", "1w")
TREND = {"up": 1.0, "down": -1.0, "none": 0.0}


def _squash(x: float | None, scale: float = 1.0) -> float:
    return 0.0 if x is None else math.tanh(x / scale)


def level_features(market: Market, structure=None, max_swings: int = 300) -> dict[str, list]:
    """Distance to the nearest support / resistance and Fibonacci position, from swings known at each close."""
    c = market.candles
    n = len(c)
    lookback = {"1h": 24 * 60, "4h": 6 * 180, "1d": 365, "1w": 104}[market.timeframe]
    support: list = [None] * n
    resistance: list = [None] * n
    fib_position: list = [None] * n
    for i, known, _ in swings_known_over_time(c, market.timeframe):
        recent = known[-max_swings:]
        price = c[i].close
        zones = support_resistance(recent, price, i, lookback=lookback)
        below = [z.high for z in zones if z.kind == "support"]
        above = [z.low for z in zones if z.kind == "resistance"]
        support[i] = price / max(below) - 1 if below else None
        resistance[i] = min(above) / price - 1 if above else None
        fib = fibonacci(recent, i)
        if fib and fib.end != fib.start:
            fib_position[i] = (price - fib.start) / (fib.end - fib.start)
    return {"support": support, "resistance": resistance, "fib": fib_position}


def _own(market: Market) -> tuple[dict[str, list], list, list]:
    c = market.candles
    n = len(c)
    vol = candle_volatility(market)
    rows = market.rows
    structure = analyse(c, market.timeframe)
    a = adx(c)
    levels = level_features(market, structure)
    out: dict[str, list] = {name: [0.0] * n for name in (
        "own.rsi", "own.ema20", "own.ema50", "own.ema200", "own.macd", "own.ret6", "own.ret24", "own.ret72",
        "own.vol_vs_avg", "own.adx", "own.trend", "own.choch_up", "own.choch_down",
        "own.support", "own.resistance", "own.fib")}
    vol_avg = None
    last_up = last_down = None
    choch = {e.index: e.direction for e in structure.events if e.kind == "CHoCH"}
    for i in range(n):
        v = vol[i]
        values = rows[i].values
        close = c[i].close
        if v:
            vol_avg = v if vol_avg is None else vol_avg + (v - vol_avg) / 500
        if values.get("rsi_14") is not None:
            out["own.rsi"][i] = (values["rsi_14"] - 50) / 50
        for name, key, span in (("own.ema20", "ema_20", 20), ("own.ema50", "ema_50", 50), ("own.ema200", "ema_200", 200)):
            ema = values.get(key)
            if ema and v:
                out[name][i] = _squash((close / ema - 1) / (v * math.sqrt(span)), 2)
        if values.get("macd_hist") is not None and v:
            out["own.macd"][i] = _squash(values["macd_hist"] / close / v, 1)
        for name, k in (("own.ret6", 6), ("own.ret24", 24), ("own.ret72", 72)):
            if i >= k and v and all(market.consecutive[i - k + 1:i + 1]):
                out[name][i] = _squash((close / c[i - k].close - 1) / (v * math.sqrt(k)), 2)
        if v and vol_avg:
            out["own.vol_vs_avg"][i] = _squash(v / vol_avg - 1, 1)
        if a[i] is not None:
            out["own.adx"][i] = a[i] / 50 - 0.5
        out["own.trend"][i] = TREND[structure.trend[i]]
        if choch.get(i) == "up":
            last_up = i
        if choch.get(i) == "down":
            last_down = i
        out["own.choch_up"][i] = 0.0 if last_up is None else math.exp(-(i - last_up) / 20)
        out["own.choch_down"][i] = 0.0 if last_down is None else math.exp(-(i - last_down) / 20)
        out["own.support"][i] = _squash(None if levels["support"][i] is None or not v else levels["support"][i] / (v * 5), 1)
        out["own.resistance"][i] = _squash(None if levels["resistance"][i] is None or not v else levels["resistance"][i] / (v * 5), 1)
        fib = levels["fib"][i]
        out["own.fib"][i] = 0.0 if fib is None else max(-1.0, min(2.0, fib)) / 2
    for name, values in pattern_features(detect_patterns(c, market.timeframe), n).items():
        out[name] = [min(x, 1.0) for x in values]
    return out, structure.trend, a


def _higher_context(lower: Market, higher: Market) -> dict[str, list]:
    """Values of the last COMPLETED higher-timeframe candle at each lower candle's close."""
    h = higher.candles
    tf = higher.timeframe
    structure = analyse(h, tf)
    a = adx(h)
    vol = candle_volatility(higher)
    period_h = timedelta(hours=TIMEFRAME_HOURS[tf])
    period_l = timedelta(hours=TIMEFRAME_HOURS[lower.timeframe])
    ends = [x.timestamp + period_h for x in h]
    prefix = f"{tf}."
    names = ("trend", "adx", "ema200", "ema50", "rsi", "macd")
    out = {prefix + k: [0.0] * len(lower.candles) for k in names}
    for i, c in enumerate(lower.candles):
        k = bisect_right(ends, c.timestamp + period_l) - 1  # completed by this close
        if k < 0:
            continue
        values = higher.rows[k].values
        close = h[k].close
        v = vol[k]
        out[prefix + "trend"][i] = TREND[structure.trend[k]]
        out[prefix + "adx"][i] = 0.0 if a[k] is None else a[k] / 50 - 0.5
        for key, ema_key, span in (("ema200", "ema_200", 200), ("ema50", "ema_50", 50)):
            ema = values.get(ema_key)
            out[prefix + key][i] = _squash((close / ema - 1) / (v * math.sqrt(span)), 2) if ema and v else 0.0
        out[prefix + "rsi"][i] = 0.0 if values.get("rsi_14") is None else (values["rsi_14"] - 50) / 50
        hist = values.get("macd_hist")
        out[prefix + "macd"][i] = _squash(hist / close / v, 1) if hist is not None and v else 0.0
    return out


def tf_inputs(markets: dict[str, Market], timeframe: str):
    """(names, rows, keys) for the learning engine on `timeframe`, with every higher timeframe's context."""
    market = markets[timeframe]
    features, own_trend, a = _own(market)
    higher = [tf for tf in ORDER[ORDER.index(timeframe) + 1:] if tf in markets]
    for tf in higher:
        features.update(_higher_context(market, markets[tf]))
    names = sorted(features)
    n = len(market.candles)
    rows = [[features[name][i] for name in names] for i in range(n)]
    first_higher = higher[0] if higher else None
    higher_trend = features[f"{first_higher}.trend"] if first_higher else [0.0] * n
    regime = ["trend" if v is not None and v >= 25 else ("range" if v is not None and v < 20 else "mixed") for v in a]
    keys = {
        "structure": list(zip(own_trend, higher_trend)),
        "regime": list(zip(regime, own_trend, higher_trend)),
    }
    return names, rows, keys
