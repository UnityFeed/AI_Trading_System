"""
The predictive engine as the app uses it: everything computed once per data
load, then served for "now" or for any past day AS IT WAS KNOWN THEN (replay).

  scenarios(horizon, day)  the learning engine's bull/bear/range forecast made
                           at that day's close, its experts and their weights,
                           targets, typical days, and (if decided) the outcome
  tools(timeframe, until)  support/resistance zones, Fibonacci levels, chart
                           patterns with their status, ADX regime and the
                           volume profile, using only swings confirmed by then
  curve(horizon)           the learning curve per year
"""

import bisect
import math
from datetime import datetime, timedelta, timezone

from src.backtesting.market import Market
from src.data_collection.market_data import MarketData
from src.predictive_engine import learner
from src.predictive_engine.levels import adx, fibonacci, regime, support_resistance
from src.predictive_engine.outcomes import daily_volatility
from src.predictive_engine.patterns import detect_patterns, status_at, swings_known_over_time, track_record
from src.predictive_engine.structure import analyse
from src.predictive_engine.volume_profile import volume_profile


K = 1.0
MIN_MOVE = 0.03


def _t(dt: datetime) -> int:
    return int(dt.timestamp())


class EngineService:

    def __init__(self, daily: Market, hourly: list[MarketData]):
        self.market = daily
        self.hourly = hourly
        self.hour_times = [h.timestamp for h in hourly]
        self.times = [c.timestamp for c in daily.candles]
        names, rows, keys = learner.build_inputs(daily)
        self.replays = {h: learner.replay(daily, h, names, rows, keys) for h in learner.HORIZONS}
        self.vol = daily_volatility(daily)
        self.tool_cache: dict = {}

    # -- scenarios ------------------------------------------------------------

    def day_index(self, day: datetime | None) -> int:
        if day is None:
            return len(self.times) - 1
        k = bisect.bisect_right(self.times, day) - 1
        return max(0, k)

    def typical_days(self, horizon: int, i: int) -> dict:
        """Median days each outcome took, over outcomes known at day i."""
        r = self.replays[horizon]
        days = {k: [] for k in learner.KINDS}
        for o in r.outcomes[:i + 1]:
            if o is not None and o.decided_index <= i:
                days[o.kind].append(o.days)
        return {k: (sorted(v)[len(v) // 2] if v else horizon) for k, v in days.items()}

    def scenarios(self, horizon: int, day: datetime | None = None) -> dict:
        r = self.replays[horizon]
        i = self.day_index(day)
        while i > 0 and r.forecasts[i] is None:
            i -= 1
        c = self.market.candles[i]
        p = r.forecasts[i]
        if p is None:
            return {"error": "no forecast this early in the history"}
        move = max(MIN_MOVE, K * (self.vol[i] or 0.0) * math.sqrt(horizon))
        target, stop = c.close * (1 + move), c.close * (1 - move)
        decided_at = c.timestamp + timedelta(days=1)
        typical = self.typical_days(horizon, i)
        paths = []
        for kind in sorted(learner.KINDS, key=lambda k: -p[k]):
            days = horizon if kind == "range" else typical[kind]
            paths.append({
                "kind": kind, "probability": round(p[kind], 4),
                "level": round({"bull": target, "bear": stop, "range": c.close}[kind], 2),
                "typical_days": days, "by": (decided_at + timedelta(days=days)).isoformat(),
                "meaning": {
                    "bull": f"a daily close at or above {target:,.0f} (+{move * 100:.1f}%) comes first",
                    "bear": f"a daily close at or below {stop:,.0f} (-{move * 100:.1f}%) comes first",
                    "range": f"neither within {horizon} days: closes stay between {stop:,.0f} and {target:,.0f}",
                }[kind],
                "proven_wrong_by": {"bull": f"a close at or below {stop:,.0f}",
                                    "bear": f"a close at or above {target:,.0f}",
                                    "range": f"a close outside {stop:,.0f}-{target:,.0f}"}[kind],
            })
        o = r.outcomes[i]
        known_outcome = o if o is not None else None
        return {
            "candle_time": c.timestamp.isoformat(), "time": _t(c.timestamp), "close": c.close,
            "horizon_days": horizon, "move_pct": round(move * 100, 2),
            "target": round(target, 2), "stop": round(stop, 2),
            "scenarios": paths,
            "experts": {e: {k: round(v, 4) for k, v in probs.items()} for e, probs in r.experts[i].items()},
            "weights": {e: round(v, 3) for e, v in r.weights[i].items()},
            "outcome": None if known_outcome is None else {
                "kind": known_outcome.kind, "days": known_outcome.days,
                "decided_time": _t(self.times[known_outcome.decided_index]),
            },
            "score_so_far": self.score_until(horizon, i),
            "model_version": f"{learner.VERSION}-h{horizon}",
            "cases": sum(1 for x in r.outcomes[:i + 1] if x is not None and x.decided_index <= i),
        }

    def score_until(self, horizon: int, i: int) -> dict:
        """The engine's Brier skill vs the base rate over forecasts decided by day i."""
        r = self.replays[horizon]
        n = b = bb = hits = 0.0
        for j in range(i + 1):
            o, p = r.outcomes[j], r.forecasts[j]
            if o is None or p is None or o.decided_index > i:
                continue
            n += 1
            b += learner.brier(p, o.kind)
            bb += learner.brier(r.experts[j]["base"], o.kind)
            hits += max(p, key=p.get) == o.kind
        if not n:
            return {"scored": 0}
        return {"scored": int(n), "brier_skill": round(1 - b / bb, 4), "top_hit_rate": round(hits / n, 3)}

    def curve(self, horizon: int) -> list:
        return [{"year": y, "days": n, "skill": round(1 - b / bb, 4)} for y, n, b, bb in self.replays[horizon].learning_curve]

    # -- chart tools -------------------------------------------------------------

    def tools(self, timeframe: str, candles: list[MarketData], until: datetime | None = None) -> dict:
        key = (timeframe, id(candles))
        if key not in self.tool_cache:
            self.tool_cache[key] = (analyse(candles, timeframe), detect_patterns(candles, timeframe), adx(candles))
        structure, patterns, adx_values = self.tool_cache[key]
        times = [c.timestamp for c in candles]
        i = len(candles) - 1 if until is None else max(0, bisect.bisect_right(times, until) - 1)
        price = candles[i].close
        known = []
        for k, swings, _ in swings_known_over_time(candles, timeframe):  # the swings as known at candle i
            if k == i:
                known = list(swings)
                break
        zones = support_resistance(known, price, i, lookback={"1h": 24 * 60, "4h": 6 * 180}.get(timeframe, 365))
        below = sorted([z for z in zones if z.kind == "support"], key=lambda z: -z.high)[:3]
        above = sorted([z for z in zones if z.kind == "resistance"], key=lambda z: z.low)[:3]
        fib = fibonacci(known, i)
        shown = []
        for p in patterns:
            status = status_at(p, i)
            if status is None or (p.end_index is not None and p.end_index < i - 20):  # finished ones fade after 20 candles
                continue
            end = i if p.end_index is None or p.end_index > i else p.end_index
            shown.append({
                "kind": p.kind, "direction": p.direction if status != "candidate" or p.direction != "either" else "either",
                "status": status,
                "points": [{"time": _t(times[q.index]), "price": q.price} for q in p.points],
                "neckline": [{"time": _t(times[p.neckline[0]]), "price": p.line_at(p.neckline, p.neckline[0])},
                             {"time": _t(times[end]), "price": p.line_at(p.neckline, end)}],
                "lower": None if p.lower is None else [
                    {"time": _t(times[p.lower[0]]), "price": p.line_at(p.lower, p.lower[0])},
                    {"time": _t(times[end]), "price": p.line_at(p.lower, end)}],
                "target": p.target if status != "candidate" else None,
                "invalidation": p.invalidation or None,
                "label_time": _t(times[p.points[-1].index]),
            })
        a = adx_values[i]
        vol_rank = None
        if timeframe == "1d" and self.vol[i] is not None:
            past = sorted(v for v in self.vol[:i + 1] if v is not None)
            vol_rank = bisect.bisect_left(past, self.vol[i]) / len(past)
        end_time = times[i] + timedelta(hours={"1h": 1, "4h": 4, "1d": 24, "1w": 168}[timeframe])
        k_end = bisect.bisect_left(self.hour_times, end_time)
        window_hours = {"1h": 24 * 7, "4h": 24 * 30, "1d": 24 * 90, "1w": 24 * 365}[timeframe]
        profile = volume_profile(self.hourly[max(0, k_end - window_hours):k_end], bins=40)
        return {
            "timeframe": timeframe, "time": _t(times[i]), "price": price,
            "zones": [{"low": z.low, "high": z.high, "touches": z.touches, "kind": z.kind} for z in below + above],
            "fibonacci": None if fib is None else {
                "direction": fib.direction, "start": fib.start, "end": fib.end,
                "levels": [{"name": name, "price": level} for name, level in fib.all_levels()],
            },
            "patterns": shown[-12:],
            "pattern_track_record": track_record(patterns),
            "adx": None if a is None else round(a, 1),
            "regime": regime(a, vol_rank),
            "volume_profile": None if profile is None else {
                "poc": profile.poc, "vah": profile.vah, "val": profile.val, "days": window_hours // 24,
                "approximate": True,
            },
        }
