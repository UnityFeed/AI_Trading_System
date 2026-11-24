"""
Price targets for the AI forecast (owner, 24 Nov 2026: "I see directions with
the highest chance, but no real targets").

Targets are REAL chart levels known at the forecast candle's close:
  - support / resistance zones (confirmed swings that turned the price before)
  - the last confirmed swing high and swing low (market structure)
  - Fibonacci levels of the last swing (retracements and extensions)
  - the measured target of a confirmed chart pattern
  - the AI's own bull / bear targets (one typical move away), so each side
    has a target even at an all-time high or low
Levels within 0.4% of each other are merged (their reasons are combined);
the 3 nearest above and the 3 nearest below the price are kept.

Chance of each target = how often the price TOUCHED a level that far away
(candle high above / low below) within the forecast horizon, in past
situations where the AI's chance for that direction was about the same as
now. Distances are measured in "typical moves" (volatility x sqrt(horizon)),
so calm and wild markets compare fairly. Only past forecasts whose window had
fully ended by the forecast candle are used (no look-ahead); the number of
past cases is shown with every chance. When too few similar cases exist, the
match is widened step by step up to all past cases.
"""

import math
from bisect import bisect_right
from dataclasses import dataclass

import numpy as np

MERGE_PCT = 0.004
PER_SIDE = 3
MIN_CASES = 150
WIDTHS = (0.05, 0.10, 0.20, 1.0)  # how close the AI's past chance must be to today's


@dataclass(frozen=True)
class Excursions:
    """Per candle: the largest rise (to a high) and fall (to a low) within the horizon, in typical moves."""
    up: np.ndarray
    down: np.ndarray
    known_at: np.ndarray  # candle index whose close completes the window (inf = not yet)


def excursions(candles, consecutive, vol, horizon: int) -> Excursions:
    n = len(candles)
    up = np.full(n, np.nan)
    down = np.full(n, np.nan)
    known = np.full(n, np.inf)
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    for i in range(n):
        v = vol[i]
        if not v or i + horizon >= n or not all(consecutive[i + 1:i + horizon + 1]):
            continue
        close = candles[i].close
        scale = v * math.sqrt(horizon)
        up[i] = (highs[i + 1:i + horizon + 1].max() / close - 1) / scale
        down[i] = (1 - lows[i + 1:i + horizon + 1].min() / close) / scale
        known[i] = i + horizon
    return Excursions(up, down, known)


def candidate_levels(price: float, tools: dict, swing_high: float | None, swing_low: float | None,
                     extra: tuple = ()) -> list[dict]:
    """Real chart levels around the price, merged, 3 nearest per side. `extra`: (price, reason) always offered."""
    raw = list(extra)
    for z in tools.get("zones") or []:
        level = z["low"] if z["low"] > price else z["high"]
        raw.append((level, f"{'resistance' if level > price else 'support'} zone ({z['touches']} turns)"))
    if swing_high:
        raw.append((swing_high, "last swing high"))
    if swing_low:
        raw.append((swing_low, "last swing low"))
    fib = tools.get("fibonacci")
    if fib:
        for f in fib["levels"]:
            raw.append((f["price"], f"Fibonacci {f['name']}"))
    for p in tools.get("patterns") or []:
        if p.get("target") and p["status"] in ("confirmed", "candidate"):
            raw.append((p["target"], f"{p['kind']} target"))
    raw = sorted((lvl, why) for lvl, why in raw if lvl and lvl > 0 and abs(lvl / price - 1) > 0.001)
    merged: list[list] = []
    for level, why in raw:
        if merged and level <= merged[-1][0] * (1 + MERGE_PCT):
            if why not in merged[-1][1]:
                merged[-1][1].append(why)
            continue
        merged.append([level, [why]])
    above = [m for m in merged if m[0] > price][:PER_SIDE]
    below = [m for m in merged if m[0] < price][::-1][:PER_SIDE]
    out = []
    for side, group in (("up", above), ("down", below)):
        for k, (level, why) in enumerate(group, start=1):
            out.append({"side": side, "name": f"{'T' if side == 'up' else 'S'}{k}", "price": round(level, 2),
                        "distance_pct": round((level / price - 1) * 100, 2), "why": why})
    return out


def touch_chance(i: int, distance_units: float, side: str, exc: Excursions, ai_chance: np.ndarray) -> tuple[float, int]:
    """(chance to touch within the horizon, number of past cases) for a level `distance_units` away."""
    values = exc.up if side == "up" else exc.down
    known = np.flatnonzero((exc.known_at <= i) & ~np.isnan(values))
    if len(known) == 0:
        return float("nan"), 0
    today = ai_chance[i]
    chosen = known  # no AI view today: every past case
    if not math.isnan(today):
        with_ai = known[~np.isnan(ai_chance[known])]
        for width in WIDTHS:
            chosen = with_ai[np.abs(ai_chance[with_ai] - today) <= width]
            if len(chosen) >= MIN_CASES:
                break
        if len(chosen) < MIN_CASES:
            chosen = known
    if len(chosen) == 0:
        return float("nan"), 0
    return float((values[chosen] >= distance_units).mean()), int(len(chosen))


def chances_array(forecasts, kind: str) -> np.ndarray:
    return np.array([np.nan if p is None else p[kind] for p in forecasts])


def index_at(times, t) -> int:
    return max(0, bisect_right(times, t) - 1)
