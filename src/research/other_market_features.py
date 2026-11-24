"""
Features from the other markets (S&P 500, Nasdaq 100, Dow 30, gold, silver)
for the AI (owner, 24 Nov 2026).

Per market, on its own trading days:
  ret1, ret5, ret20   log return over the last 1 / 5 / 20 trading days
  trend200            close / 200-day average - 1 (above or below its long trend)
  vol20               volatility of the last 20 daily returns (yearly scale)

They reach BTC's candles through `exposure._lookup` with no extra lag: a
value of trading date D is used from the close of BTC's daily candle D (00:00
UTC on D+1) on, and by 1h/4h candles closing at least a day after D started
(US markets close around 21:00-22:00 UTC). Weekends and holidays reuse the
last completed trading day (up to 7 days old, then missing).
"""

import math
from datetime import date

from src.backtesting.exposure import _lookup
from src.backtesting.market import Market

PREFIX = "mkt."
FEATURES = ("ret1", "ret5", "ret20", "trend200", "vol20")


def daily_features(closes: dict[date, float]) -> dict[str, dict[date, float]]:
    days = sorted(closes)
    c = [closes[d] for d in days]
    out = {name: {} for name in FEATURES}
    logs = [None] + [math.log(c[k] / c[k - 1]) for k in range(1, len(c))]
    running = 0.0
    for k, d in enumerate(days):
        running += c[k]
        if k >= 200:
            running -= c[k - 200]
        for n, name in ((1, "ret1"), (5, "ret5"), (20, "ret20")):
            if k >= n:
                out[name][d] = math.log(c[k] / c[k - n])
        if k >= 199:
            out["trend200"][d] = c[k] / (running / 200) - 1
        if k >= 20:
            window = logs[k - 19:k + 1]
            mean = sum(window) / 20
            out["vol20"][d] = math.sqrt(sum((x - mean) ** 2 for x in window) / 19 * 252)
    return out


# How the AI uses them: "off", "compact" (US stocks averaged into one, plus
# gold: 6 inputs) or "full" (every market separately: 25 inputs). Honest test
# on the test DB, 24 Nov 2026 (training session, nested choice): BOTH made the
# forecasts worse than without them (4h 14 days +3.20% -> +1.74% full /
# +2.70% compact; 1d 30 days +1.16% -> +0.16% compact), so the default is
# "off". The data is still collected; `train_engine --markets` compares again.
AI_MODE = "off"
MODES = ("off", "compact", "full")
EQUITIES = ("spx", "ndx", "dji")


def compact_series(external: dict) -> dict[str, dict[date, float]]:
    """US stocks averaged (S&P 500, Nasdaq 100, Dow 30) + gold: 6 daily series."""
    per = {m: daily_features(external[f"{PREFIX}{m}"]) for m in EQUITIES + ("gold",)
           if len(external.get(f"{PREFIX}{m}", {})) >= 30}
    out = {}
    stocks = [per[m] for m in EQUITIES if m in per]
    for name in ("ret5", "ret20", "trend200", "vol20"):
        days = set().union(*(f[name] for f in stocks)) if stocks else set()
        out[f"{PREFIX}stocks.{name}"] = {
            d: sum(f[name][d] for f in stocks if d in f[name]) / sum(d in f[name] for f in stocks) for d in days}
    if "gold" in per:
        out[f"{PREFIX}gold.ret20"] = per["gold"]["ret20"]
        out[f"{PREFIX}gold.trend200"] = per["gold"]["trend200"]
    return {k: v for k, v in out.items() if v}


def other_market_features(market: Market, external: dict | None = None, mode: str | None = None) -> dict[str, list]:
    """name -> value per candle of `market` (raw, unscaled), from the "mkt.<name>" series present."""
    external = market.external if external is None else external
    mode = mode or AI_MODE
    if mode == "off":
        return {}
    if mode == "compact":
        return {name: _lookup(market, series, 0) for name, series in sorted(compact_series(external).items())}
    out = {}
    for key, closes in sorted(external.items()):
        if not key.startswith(PREFIX) or len(closes) < 30:
            continue
        for name, series in daily_features(closes).items():
            out[f"{key}.{name}"] = _lookup(market, series, 0)
    return out
